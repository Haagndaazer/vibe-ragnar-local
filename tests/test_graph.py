"""Tests for the graph module."""

import pytest

from vibe_ragnar.graph import EdgeType, GraphBuilder, GraphStorage, get_function_calls, find_symbol
from vibe_ragnar.parser import Function, Class, File


class TestGraphStorage:
    """Tests for GraphStorage class."""

    def test_add_and_get_entity(self):
        """Test adding and retrieving entities."""
        storage = GraphStorage()

        func = Function(
            repo="test",
            file_path="test.py",
            name="hello",
            start_line=1,
            end_line=3,
            signature="hello(name: str)",
            code="def hello(name: str): pass",
        )

        storage.add_entity(func)

        retrieved = storage.get_entity(func.id)
        assert retrieved is not None
        assert retrieved["name"] == "hello"
        assert retrieved["type"] == "function"

    def test_add_edge(self):
        """Test adding edges between entities."""
        storage = GraphStorage()

        func1 = Function(
            repo="test", file_path="test.py", name="caller",
            start_line=1, end_line=3, signature="caller()",
            code="def caller(): callee()",
        )
        func2 = Function(
            repo="test", file_path="test.py", name="callee",
            start_line=5, end_line=7, signature="callee()",
            code="def callee(): pass",
        )

        storage.add_entity(func1)
        storage.add_entity(func2)
        storage.add_edge(func1.id, func2.id, EdgeType.CALLS)

        successors = storage.get_successors(func1.id, EdgeType.CALLS)
        assert len(successors) == 1
        assert successors[0][0] == func2.id

    def test_get_predecessors(self):
        """Test getting predecessor entities."""
        storage = GraphStorage()

        func1 = Function(
            repo="test", file_path="test.py", name="caller",
            start_line=1, end_line=3, signature="caller()",
            code="def caller(): pass",
        )
        func2 = Function(
            repo="test", file_path="test.py", name="callee",
            start_line=5, end_line=7, signature="callee()",
            code="def callee(): pass",
        )

        storage.add_entity(func1)
        storage.add_entity(func2)
        storage.add_edge(func1.id, func2.id, EdgeType.CALLS)

        predecessors = storage.get_predecessors(func2.id, EdgeType.CALLS)
        assert len(predecessors) == 1
        assert predecessors[0][0] == func1.id

    def test_get_statistics(self):
        """Test graph statistics."""
        storage = GraphStorage()

        func = Function(
            repo="test", file_path="test.py", name="foo",
            start_line=1, end_line=2, signature="foo()",
            code="def foo(): pass",
        )
        cls = Class(
            repo="test", file_path="test.py", name="Bar",
            start_line=4, end_line=10, code="class Bar: pass",
        )
        file = File(
            repo="test", file_path="test.py", name="test.py",
            start_line=1, end_line=10, language="python",
        )

        storage.add_entity(func)
        storage.add_entity(cls)
        storage.add_entity(file)

        stats = storage.get_statistics()
        assert stats["nodes"] == 3
        assert stats["functions"] == 1
        assert stats["classes"] == 1
        assert stats["files"] == 1

    def test_remove_file(self):
        """Test removing all entities from a file."""
        storage = GraphStorage()

        func = Function(
            repo="test", file_path="test.py", name="foo",
            start_line=1, end_line=2, signature="foo()",
            code="def foo(): pass",
        )
        file = File(
            repo="test", file_path="test.py", name="test.py",
            start_line=1, end_line=2, language="python",
        )

        storage.add_entity(func)
        storage.add_entity(file)

        removed = storage.remove_file("test.py")
        assert len(removed) == 2
        assert storage.get_statistics()["nodes"] == 0


class TestGraphBuilder:
    """Tests for GraphBuilder class."""

    def test_build_call_edges(self):
        """Test building CALLS edges from function calls."""
        storage = GraphStorage()
        builder = GraphBuilder(storage)

        caller = Function(
            repo="test", file_path="test.py", name="caller",
            start_line=1, end_line=3, signature="caller()",
            code="def caller(): callee()", calls=["callee"],
        )
        callee = Function(
            repo="test", file_path="test.py", name="callee",
            start_line=5, end_line=7, signature="callee()",
            code="def callee(): pass",
        )

        builder.build_from_entities([caller, callee])

        calls = get_function_calls(storage, caller.id)
        assert len(calls) == 1
        assert calls[0]["name"] == "callee"

    def test_build_inheritance_edges(self):
        """Test building INHERITS edges from class bases."""
        storage = GraphStorage()
        builder = GraphBuilder(storage)

        parent = Class(
            repo="test", file_path="test.py", name="Parent",
            start_line=1, end_line=3, code="class Parent: pass",
        )
        child = Class(
            repo="test", file_path="test.py", name="Child",
            start_line=5, end_line=7, code="class Child(Parent): pass",
            bases=["Parent"],
        )

        builder.build_from_entities([parent, child])

        # Child should have INHERITS edge to Parent
        successors = storage.get_successors(child.id, EdgeType.INHERITS)
        assert len(successors) == 1
        assert successors[0][0] == parent.id


class TestGraphQueries:
    """Tests for graph query functions."""

    def test_find_symbol(self):
        """Test finding symbols by name."""
        storage = GraphStorage()
        builder = GraphBuilder(storage)

        func1 = Function(
            repo="test", file_path="a.py", name="process",
            start_line=1, end_line=2, signature="process()",
            code="def process(): pass",
        )
        func2 = Function(
            repo="test", file_path="b.py", name="process",
            start_line=1, end_line=2, signature="process()",
            code="def process(): pass",
        )
        func3 = Function(
            repo="test", file_path="a.py", name="other",
            start_line=4, end_line=5, signature="other()",
            code="def other(): pass",
        )

        builder.build_from_entities([func1, func2, func3])

        results = find_symbol(storage, "process")
        assert len(results) == 2
        assert all(r["name"] == "process" for r in results)

        # With file context, should prioritize local file
        results = find_symbol(storage, "process", file_context="a.py")
        assert results[0]["file_path"] == "a.py"
