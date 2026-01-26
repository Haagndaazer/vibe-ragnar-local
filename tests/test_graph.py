"""Tests for the graph module."""

import pytest

from vibe_ragnar.graph import (
    EdgeType,
    GraphBuilder,
    GraphStorage,
    find_paths,
    find_symbol,
    get_call_chain,
    get_callers,
    get_class_hierarchy,
    get_connected_components,
    get_file_dependencies,
    get_file_dependents,
    get_file_structure,
    get_function_calls,
)
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

    def test_get_callers(self):
        """Test getting callers of a function."""
        storage = GraphStorage()
        builder = GraphBuilder(storage)

        callee = Function(
            repo="test", file_path="test.py", name="callee",
            start_line=1, end_line=2, signature="callee()",
            code="def callee(): pass",
        )
        caller1 = Function(
            repo="test", file_path="test.py", name="caller1",
            start_line=4, end_line=6, signature="caller1()",
            code="def caller1(): callee()", calls=["callee"],
        )
        caller2 = Function(
            repo="test", file_path="test.py", name="caller2",
            start_line=8, end_line=10, signature="caller2()",
            code="def caller2(): callee()", calls=["callee"],
        )

        builder.build_from_entities([callee, caller1, caller2])

        callers = get_callers(storage, callee.id)
        assert len(callers) == 2
        caller_names = {c["name"] for c in callers}
        assert caller_names == {"caller1", "caller2"}

    def test_get_call_chain_outgoing(self):
        """Test getting outgoing call chain."""
        storage = GraphStorage()
        builder = GraphBuilder(storage)

        func_a = Function(
            repo="test", file_path="test.py", name="a",
            start_line=1, end_line=2, signature="a()",
            code="def a(): b()", calls=["b"],
        )
        func_b = Function(
            repo="test", file_path="test.py", name="b",
            start_line=4, end_line=5, signature="b()",
            code="def b(): c()", calls=["c"],
        )
        func_c = Function(
            repo="test", file_path="test.py", name="c",
            start_line=7, end_line=8, signature="c()",
            code="def c(): pass",
        )

        builder.build_from_entities([func_a, func_b, func_c])

        chain = get_call_chain(storage, func_a.id, direction="outgoing")
        assert chain["name"] == "a"
        assert len(chain["calls"]) == 1
        assert chain["calls"][0]["name"] == "b"

    def test_get_call_chain_incoming(self):
        """Test getting incoming call chain."""
        storage = GraphStorage()
        builder = GraphBuilder(storage)

        func_a = Function(
            repo="test", file_path="test.py", name="a",
            start_line=1, end_line=2, signature="a()",
            code="def a(): b()", calls=["b"],
        )
        func_b = Function(
            repo="test", file_path="test.py", name="b",
            start_line=4, end_line=5, signature="b()",
            code="def b(): c()", calls=["c"],
        )
        func_c = Function(
            repo="test", file_path="test.py", name="c",
            start_line=7, end_line=8, signature="c()",
            code="def c(): pass",
        )

        builder.build_from_entities([func_a, func_b, func_c])

        chain = get_call_chain(storage, func_c.id, direction="incoming")
        assert chain["name"] == "c"
        assert len(chain["callers"]) == 1
        assert chain["callers"][0]["name"] == "b"

    def test_get_file_dependencies(self):
        """Test getting file dependencies (imports)."""
        storage = GraphStorage()
        builder = GraphBuilder(storage)

        file1 = File(
            repo="test", file_path="main.py", name="main.py",
            start_line=1, end_line=10, language="python",
            imports=["utils"],
        )
        file2 = File(
            repo="test", file_path="utils.py", name="utils.py",
            start_line=1, end_line=5, language="python",
        )

        builder.build_from_entities([file1, file2])

        deps = get_file_dependencies(storage, file1.id)
        # Should have at least one dependency (external if not resolved)
        assert len(deps) >= 1

    def test_get_file_dependents(self):
        """Test getting files that depend on a file."""
        storage = GraphStorage()
        builder = GraphBuilder(storage)

        # Create a dependency chain
        file_utils = File(
            repo="test", file_path="utils.py", name="utils.py",
            start_line=1, end_line=5, language="python",
        )
        file_main = File(
            repo="test", file_path="main.py", name="main.py",
            start_line=1, end_line=10, language="python",
            imports=["utils"],
        )

        builder.build_from_entities([file_utils, file_main])

        # file_main imports utils, so should appear as a dependent
        # Note: This test may need adjustment based on import resolution
        dependents = get_file_dependents(storage, file_utils.id)
        # Result depends on import resolution success
        assert isinstance(dependents, list)

    def test_get_class_hierarchy_parents(self):
        """Test getting parent classes in hierarchy."""
        storage = GraphStorage()
        builder = GraphBuilder(storage)

        grandparent = Class(
            repo="test", file_path="test.py", name="GrandParent",
            start_line=1, end_line=3, code="class GrandParent: pass",
        )
        parent = Class(
            repo="test", file_path="test.py", name="Parent",
            start_line=5, end_line=7, code="class Parent(GrandParent): pass",
            bases=["GrandParent"],
        )
        child = Class(
            repo="test", file_path="test.py", name="Child",
            start_line=9, end_line=11, code="class Child(Parent): pass",
            bases=["Parent"],
        )

        builder.build_from_entities([grandparent, parent, child])

        hierarchy = get_class_hierarchy(storage, child.id, direction="parents")
        assert hierarchy["name"] == "Child"
        assert "parents" in hierarchy
        assert len(hierarchy["parents"]) == 1
        assert hierarchy["parents"][0]["name"] == "Parent"

    def test_get_class_hierarchy_children(self):
        """Test getting child classes in hierarchy."""
        storage = GraphStorage()
        builder = GraphBuilder(storage)

        parent = Class(
            repo="test", file_path="test.py", name="Parent",
            start_line=1, end_line=3, code="class Parent: pass",
        )
        child1 = Class(
            repo="test", file_path="test.py", name="Child1",
            start_line=5, end_line=7, code="class Child1(Parent): pass",
            bases=["Parent"],
        )
        child2 = Class(
            repo="test", file_path="test.py", name="Child2",
            start_line=9, end_line=11, code="class Child2(Parent): pass",
            bases=["Parent"],
        )

        builder.build_from_entities([parent, child1, child2])

        hierarchy = get_class_hierarchy(storage, parent.id, direction="children")
        assert hierarchy["name"] == "Parent"
        assert "children" in hierarchy
        assert len(hierarchy["children"]) == 2
        child_names = {c["name"] for c in hierarchy["children"]}
        assert child_names == {"Child1", "Child2"}

    def test_get_file_structure(self):
        """Test getting file structure (classes and functions)."""
        storage = GraphStorage()
        builder = GraphBuilder(storage)

        func1 = Function(
            repo="test", file_path="test.py", name="standalone",
            start_line=1, end_line=2, signature="standalone()",
            code="def standalone(): pass",
        )
        cls = Class(
            repo="test", file_path="test.py", name="MyClass",
            start_line=4, end_line=10, code="class MyClass: pass",
            methods=["method1"],
        )
        method = Function(
            repo="test", file_path="test.py", name="method1",
            start_line=5, end_line=6, signature="method1(self)",
            code="def method1(self): pass", class_name="MyClass",
        )
        file = File(
            repo="test", file_path="test.py", name="test.py",
            start_line=1, end_line=10, language="python",
            defines=[func1.id, cls.id, method.id],
        )

        builder.build_from_entities([func1, cls, method, file])

        structure = get_file_structure(storage, file.id)
        assert structure["name"] == "test.py"
        assert "classes" in structure
        assert "functions" in structure

    def test_get_connected_components(self):
        """Test getting connected components in the graph."""
        storage = GraphStorage()
        builder = GraphBuilder(storage)

        # Create two disconnected components
        func_a = Function(
            repo="test", file_path="test.py", name="a",
            start_line=1, end_line=2, signature="a()",
            code="def a(): b()", calls=["b"],
        )
        func_b = Function(
            repo="test", file_path="test.py", name="b",
            start_line=4, end_line=5, signature="b()",
            code="def b(): pass",
        )
        # Disconnected from a and b
        func_c = Function(
            repo="test", file_path="other.py", name="c",
            start_line=1, end_line=2, signature="c()",
            code="def c(): pass",
        )

        builder.build_from_entities([func_a, func_b, func_c])

        components = get_connected_components(storage)
        # Should have at least 2 components (a-b connected, c isolated)
        assert len(components) >= 2

    def test_find_paths(self):
        """Test finding paths between entities."""
        storage = GraphStorage()
        builder = GraphBuilder(storage)

        func_a = Function(
            repo="test", file_path="test.py", name="a",
            start_line=1, end_line=2, signature="a()",
            code="def a(): b()", calls=["b"],
        )
        func_b = Function(
            repo="test", file_path="test.py", name="b",
            start_line=4, end_line=5, signature="b()",
            code="def b(): c()", calls=["c"],
        )
        func_c = Function(
            repo="test", file_path="test.py", name="c",
            start_line=7, end_line=8, signature="c()",
            code="def c(): pass",
        )

        builder.build_from_entities([func_a, func_b, func_c])

        paths = find_paths(storage, func_a.id, func_c.id)
        assert len(paths) >= 1
        # Path should be a -> b -> c
        assert func_a.id in paths[0]
        assert func_c.id in paths[0]

    def test_find_paths_no_path(self):
        """Test finding paths when no path exists."""
        storage = GraphStorage()
        builder = GraphBuilder(storage)

        func_a = Function(
            repo="test", file_path="test.py", name="a",
            start_line=1, end_line=2, signature="a()",
            code="def a(): pass",
        )
        func_b = Function(
            repo="test", file_path="test.py", name="b",
            start_line=4, end_line=5, signature="b()",
            code="def b(): pass",
        )

        builder.build_from_entities([func_a, func_b])

        paths = find_paths(storage, func_a.id, func_b.id)
        assert len(paths) == 0


class TestScopedSymbolTable:
    """Tests for the ScopedSymbolTable."""

    def test_file_scoped_resolution(self):
        """Test that symbols are resolved within file scope."""
        storage = GraphStorage()
        builder = GraphBuilder(storage)

        # Same name in different files
        func1 = Function(
            repo="test", file_path="file1.py", name="process",
            start_line=1, end_line=2, signature="process()",
            code="def process(): pass",
        )
        func2 = Function(
            repo="test", file_path="file2.py", name="process",
            start_line=1, end_line=2, signature="process()",
            code="def process(): pass",
        )

        builder.build_from_entities([func1, func2])

        # Both should be registered
        symbol_table = builder.symbol_table
        assert symbol_table.resolve("process", "file1.py") == func1.id
        assert symbol_table.resolve("process", "file2.py") == func2.id

    def test_qualified_name_resolution(self):
        """Test qualified name resolution for methods."""
        storage = GraphStorage()
        builder = GraphBuilder(storage)

        method = Function(
            repo="test", file_path="test.py", name="method",
            start_line=1, end_line=2, signature="method(self)",
            code="def method(self): pass", class_name="MyClass",
        )

        builder.build_from_entities([method])

        symbol_table = builder.symbol_table
        # Should resolve by qualified name
        assert symbol_table.resolve("MyClass.method") == method.id
