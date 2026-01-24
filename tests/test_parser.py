"""Tests for the Tree-sitter parser."""

from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from vibe_ragnar.parser import TreeSitterParser, Function, Class, File


class TestTreeSitterParser:
    """Tests for TreeSitterParser class."""

    def test_parse_python_function(self):
        """Test parsing a simple Python function."""
        code = '''
def hello(name: str) -> str:
    """Say hello to someone."""
    return f"Hello, {name}!"
'''
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()

            parser = TreeSitterParser("test-repo")
            entities = parser.parse_file(Path(f.name))

        # Should have function + file
        functions = [e for e in entities if isinstance(e, Function)]
        files = [e for e in entities if isinstance(e, File)]

        assert len(functions) == 1
        assert len(files) == 1

        func = functions[0]
        assert func.name == "hello"
        assert "name: str" in func.signature
        assert func.class_name is None
        assert func.content_hash is not None

    def test_parse_python_class_with_methods(self):
        """Test parsing a Python class with methods."""
        code = '''
class Greeter:
    """A greeter class."""

    def __init__(self, prefix: str = "Hi"):
        self.prefix = prefix

    def greet(self, name: str) -> str:
        return f"{self.prefix}, {name}!"
'''
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()

            parser = TreeSitterParser("test-repo")
            entities = parser.parse_file(Path(f.name))

        classes = [e for e in entities if isinstance(e, Class)]
        functions = [e for e in entities if isinstance(e, Function)]

        assert len(classes) == 1
        assert len(functions) == 2  # __init__ and greet

        cls = classes[0]
        assert cls.name == "Greeter"
        assert "__init__" in cls.methods
        assert "greet" in cls.methods

        # Check methods have class_name set
        for func in functions:
            assert func.class_name == "Greeter"

    def test_parse_function_calls(self):
        """Test extraction of function calls."""
        code = '''
def process():
    result = validate()
    data = transform(result)
    return save(data)
'''
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()

            parser = TreeSitterParser("test-repo")
            entities = parser.parse_file(Path(f.name))

        functions = [e for e in entities if isinstance(e, Function)]
        assert len(functions) == 1

        func = functions[0]
        assert "validate" in func.calls
        assert "transform" in func.calls
        assert "save" in func.calls

    def test_entity_id_format(self):
        """Test entity ID format."""
        code = '''
def standalone():
    pass

class MyClass:
    def method(self):
        pass
'''
        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()

            parser = TreeSitterParser("my-repo")
            entities = parser.parse_file(Path(f.name))

        functions = [e for e in entities if isinstance(e, Function)]

        standalone = next(f for f in functions if f.name == "standalone")
        method = next(f for f in functions if f.name == "method")

        # Standalone function: repo:path:name
        assert standalone.id.startswith("my-repo:")
        assert standalone.id.endswith(":standalone")

        # Method: repo:path:Class.method
        assert method.id.startswith("my-repo:")
        assert method.id.endswith(":MyClass.method")

    def test_supports_file(self):
        """Test file extension detection."""
        parser = TreeSitterParser("test")

        assert parser.supports_file("test.py")
        assert parser.supports_file("test.ts")
        assert parser.supports_file("test.js")
        assert parser.supports_file("test.go")
        assert parser.supports_file("test.rs")
        assert parser.supports_file("test.java")
        assert parser.supports_file("test.c")
        assert parser.supports_file("test.cpp")

        assert not parser.supports_file("test.txt")
        assert not parser.supports_file("test.md")
        assert not parser.supports_file("test.json")

    def test_content_hash_changes(self):
        """Test that content hash changes when code changes."""
        code1 = "def foo(): pass"
        code2 = "def foo(): return 1"

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code1)
            f.flush()

            parser = TreeSitterParser("test")
            entities1 = parser.parse_file(Path(f.name))

        with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code2)
            f.flush()

            entities2 = parser.parse_file(Path(f.name))

        func1 = [e for e in entities1 if isinstance(e, Function)][0]
        func2 = [e for e in entities2 if isinstance(e, Function)][0]

        assert func1.content_hash != func2.content_hash
