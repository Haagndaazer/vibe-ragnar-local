"""Tree-sitter parser for extracting code entities from source files."""

import logging
import re
from pathlib import Path

from tree_sitter import Language, Node, Parser, Query, QueryCursor

from .entities import (
    AccessModifier,
    AnyEntity,
    CallInfo,
    CallType,
    Class,
    File,
    Function,
    TypeDefinition,
    TypeParameter,
)
from .languages import (
    LANGUAGE_CONFIGS,
    LanguageConfig,
    get_language_config,
    get_language_for_file,
    is_supported_file,
    should_ignore_path,
)

logger = logging.getLogger(__name__)


class TreeSitterParser:
    """Parser for extracting code entities using Tree-sitter."""

    def __init__(self, repo_name: str):
        """Initialize the parser.

        Args:
            repo_name: Name of the repository (used in entity IDs)
        """
        self.repo_name = repo_name
        self._parsers: dict[str, Parser] = {}
        self._queries: dict[str, dict[str, Query]] = {}
        self._languages: dict[str, Language] = {}
        self._init_parsers()

    def _init_parsers(self) -> None:
        """Initialize Tree-sitter parsers and queries for all languages."""
        for lang_name, config in LANGUAGE_CONFIGS.items():
            parser = Parser(config.language)
            self._parsers[lang_name] = parser
            self._languages[lang_name] = config.language

            # Pre-compile queries
            self._queries[lang_name] = {
                "function": Query(config.language, config.function_query),
                "class": Query(config.language, config.class_query),
                "import": Query(config.language, config.import_query),
                "call": Query(config.language, config.call_query),
            }
            if config.type_query:
                self._queries[lang_name]["type"] = Query(config.language, config.type_query)

    def _run_query(self, query: Query, node: Node) -> dict[str, list[Node]]:
        """Run a query and return captures as a dictionary.

        Args:
            query: The compiled query
            node: The root node to search

        Returns:
            Dictionary mapping capture names to lists of matching nodes
        """
        cursor = QueryCursor(query)
        return cursor.captures(node)

    def supports_file(self, file_path: Path | str) -> bool:
        """Check if a file is supported for parsing.

        Args:
            file_path: Path to the file

        Returns:
            True if the file can be parsed
        """
        return is_supported_file(file_path)

    def parse_file(self, file_path: Path | str, repo_root: Path | None = None) -> list[AnyEntity]:
        """Parse a source file and extract all code entities.

        Args:
            file_path: Path to the file to parse
            repo_root: Root directory of the repository (for relative paths)

        Returns:
            List of extracted code entities
        """
        file_path = Path(file_path)
        if not file_path.exists():
            logger.warning(f"File does not exist: {file_path}")
            return []

        language = get_language_for_file(file_path)
        if not language:
            logger.debug(f"Unsupported file type: {file_path}")
            return []

        config = get_language_config(language)
        if not config:
            return []

        try:
            source = file_path.read_bytes()
        except OSError as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            return []

        # Calculate relative path
        if repo_root:
            try:
                relative_path = str(file_path.relative_to(repo_root))
            except ValueError:
                relative_path = str(file_path)
        else:
            relative_path = str(file_path)

        # Parse the file
        parser = self._parsers[language]
        tree = parser.parse(source)

        entities: list[AnyEntity] = []

        # Extract functions
        functions = self._extract_functions(tree.root_node, source, relative_path, language, config)
        entities.extend(functions)

        # Extract classes
        classes = self._extract_classes(tree.root_node, source, relative_path, language, config)
        entities.extend(classes)

        # Extract type definitions (TypeScript, Go, Rust)
        if language in {"typescript", "go", "rust"}:
            types = self._extract_types(tree.root_node, source, relative_path, language, config)
            entities.extend(types)

        # Create file entity
        imports = self._extract_imports(tree.root_node, source, language)
        file_entity = File(
            repo=self.repo_name,
            file_path=relative_path,
            name=file_path.name,
            start_line=1,
            end_line=source.count(b"\n") + 1,
            language=language,
            imports=imports,
            defines=[e.id for e in entities],
        )
        entities.append(file_entity)

        return entities

    def _extract_functions(
        self,
        root: Node,
        source: bytes,
        file_path: str,
        language: str,
        config: LanguageConfig,
    ) -> list[Function]:
        """Extract function definitions from the AST."""
        functions: list[Function] = []
        query = self._queries[language]["function"]
        call_query = self._queries[language]["call"]

        captures = self._run_query(query, root)

        # Get function definitions
        func_defs = captures.get("function.def", [])
        func_names = captures.get("function.name", [])

        # Match names to definitions by position
        name_to_node: dict[tuple[int, int], Node] = {}
        for name_node in func_names:
            name_to_node[(name_node.start_byte, name_node.end_byte)] = name_node

        for def_node in func_defs:
            # Find the name node within this definition
            func_name = None
            name_node = None
            for child in self._walk_children(def_node):
                key = (child.start_byte, child.end_byte)
                if key in name_to_node:
                    name_node = name_to_node[key]
                    func_name = self._node_text(name_node, source)
                    break

            if not func_name:
                # Fallback: look for identifier/property_identifier directly
                func_name = self._find_function_name(def_node, source, language)
                if not func_name:
                    continue

            func_code = self._node_text(def_node, source)

            # Find parameters
            params_text = self._find_params(def_node, source, language)
            signature = f"{func_name}{params_text}"

            # Extract docstring
            docstring = self._extract_docstring(def_node, source, language)

            # Check if it's a method (inside a class)
            class_name = self._get_containing_class(def_node, source)

            # Check if async
            is_async = self._is_async_function(def_node, source, language)

            # Extract decorators
            decorators = self._extract_decorators(def_node, source, language)

            # Extract function calls from body
            calls: list[str] = []
            call_details: list[CallInfo] = []
            body_node = self._find_body(def_node, language)
            if body_node:
                calls, call_details = self._extract_calls(body_node, source, language)

            # Check if this is a constructor
            is_constructor = self._is_constructor(func_name, class_name, language)

            # Extract access modifier and static/abstract flags
            access_modifier = self._extract_access_modifier(def_node, source, language)
            is_static = self._is_static(def_node, source, language)
            is_abstract = self._is_abstract(def_node, source, language)

            # Extract type parameters (generics)
            type_parameters = self._extract_type_parameters(def_node, source, language)

            # Extract return type
            return_type = self._extract_return_type(def_node, source, language)

            func = Function(
                repo=self.repo_name,
                file_path=file_path,
                name=func_name,
                start_line=def_node.start_point[0] + 1,
                end_line=def_node.end_point[0] + 1,
                signature=signature,
                docstring=docstring,
                code=func_code,
                class_name=class_name,
                decorators=decorators,
                calls=calls,
                call_details=call_details,
                is_async=is_async,
                is_constructor=is_constructor,
                access_modifier=access_modifier,
                is_static=is_static,
                is_abstract=is_abstract,
                type_parameters=type_parameters,
                return_type=return_type,
            )
            functions.append(func)

        return functions

    def _extract_classes(
        self,
        root: Node,
        source: bytes,
        file_path: str,
        language: str,
        config: LanguageConfig,
    ) -> list[Class]:
        """Extract class definitions from the AST."""
        classes: list[Class] = []
        query = self._queries[language]["class"]

        captures = self._run_query(query, root)

        class_defs = captures.get("class.def", [])

        for def_node in class_defs:
            # Find class name
            class_name = self._find_class_name(def_node, source, language)
            if not class_name:
                continue

            class_code = self._node_text(def_node, source)

            # Extract docstring
            docstring = self._extract_docstring(def_node, source, language)

            # Extract base classes
            bases = self._extract_bases(def_node, source, language)

            # Extract decorators
            decorators = self._extract_decorators(def_node, source, language)

            # Extract method names
            methods = self._extract_method_names(def_node, source, language)

            # Extract access modifier and abstract flag
            access_modifier = self._extract_access_modifier(def_node, source, language)
            is_abstract = self._is_abstract(def_node, source, language)

            # Check if this is an interface
            is_interface = def_node.type in {"interface_declaration", "interface_type"}

            # Extract type parameters (generics)
            type_parameters = self._extract_type_parameters(def_node, source, language)

            # Extract implements list (Java)
            implements = self._extract_implements(def_node, source, language)

            cls = Class(
                repo=self.repo_name,
                file_path=file_path,
                name=class_name,
                start_line=def_node.start_point[0] + 1,
                end_line=def_node.end_point[0] + 1,
                docstring=docstring,
                code=class_code,
                bases=bases,
                decorators=decorators,
                methods=methods,
                access_modifier=access_modifier,
                is_abstract=is_abstract,
                is_interface=is_interface,
                type_parameters=type_parameters,
                implements=implements,
            )
            classes.append(cls)

        return classes

    def _extract_types(
        self,
        root: Node,
        source: bytes,
        file_path: str,
        language: str,
        config: LanguageConfig,
    ) -> list[TypeDefinition]:
        """Extract type/interface definitions (TypeScript, Go, Rust)."""
        types: list[TypeDefinition] = []

        if "type" not in self._queries[language]:
            return types

        query = self._queries[language]["type"]
        captures = self._run_query(query, root)

        type_defs = captures.get("type.def", [])

        for def_node in type_defs:
            # Find type name
            type_name = self._find_type_name(def_node, source, language)
            if not type_name:
                continue

            definition = self._node_text(def_node, source)

            # Determine kind
            kind = self._determine_type_kind(def_node, language)

            # Extract docstring
            docstring = self._extract_docstring(def_node, source, language)

            type_def = TypeDefinition(
                repo=self.repo_name,
                file_path=file_path,
                name=type_name,
                start_line=def_node.start_point[0] + 1,
                end_line=def_node.end_point[0] + 1,
                definition=definition,
                docstring=docstring,
                kind=kind,
            )
            types.append(type_def)

        return types

    def _extract_imports(self, root: Node, source: bytes, language: str) -> list[str]:
        """Extract import statements from the AST."""
        imports: list[str] = []
        query = self._queries[language]["import"]

        captures = self._run_query(query, root)

        for key in ["import.name", "import.module", "import.path", "import.source"]:
            for node in captures.get(key, []):
                import_text = self._node_text(node, source)
                # Clean up the import text
                import_text = import_text.strip("'\"")
                if import_text:
                    imports.append(import_text)

        return list(set(imports))  # Deduplicate

    def _walk_children(self, node: Node):
        """Recursively yield all children of a node."""
        yield node
        for child in node.children:
            yield from self._walk_children(child)

    def _node_text(self, node: Node | None, source: bytes) -> str:
        """Get the text content of a node."""
        if node is None:
            return ""
        return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    def _find_function_name(self, node: Node, source: bytes, language: str) -> str | None:
        """Find the function name from a function definition node."""
        name_types = {"identifier", "property_identifier", "field_identifier"}
        for child in node.children:
            if child.type in name_types:
                return self._node_text(child, source)
            # Check for nested declarators (C/C++)
            if child.type in {"function_declarator", "declarator"}:
                for subchild in child.children:
                    if subchild.type in name_types:
                        return self._node_text(subchild, source)
                    if subchild.type == "qualified_identifier":
                        for sub2 in subchild.children:
                            if sub2.type == "identifier":
                                return self._node_text(sub2, source)
        return None

    def _find_class_name(self, node: Node, source: bytes, language: str) -> str | None:
        """Find the class name from a class definition node."""
        name_types = {"identifier", "type_identifier"}
        for child in node.children:
            if child.type in name_types:
                return self._node_text(child, source)
            # TypeScript: type_spec contains the name
            if child.type == "type_spec":
                for subchild in child.children:
                    if subchild.type in name_types:
                        return self._node_text(subchild, source)
        return None

    def _find_type_name(self, node: Node, source: bytes, language: str) -> str | None:
        """Find the type name from a type definition node."""
        name_types = {"identifier", "type_identifier"}
        for child in node.children:
            if child.type in name_types:
                return self._node_text(child, source)
            if child.type == "type_spec":
                for subchild in child.children:
                    if subchild.type in name_types:
                        return self._node_text(subchild, source)
        return None

    def _find_params(self, node: Node, source: bytes, language: str) -> str:
        """Find the parameters string from a function definition."""
        params_types = {"parameters", "formal_parameters", "parameter_list"}
        for child in node.children:
            if child.type in params_types:
                return self._node_text(child, source)
            if child.type in {"function_declarator", "declarator"}:
                for subchild in child.children:
                    if subchild.type in params_types:
                        return self._node_text(subchild, source)
        return "()"

    def _find_body(self, node: Node, language: str) -> Node | None:
        """Find the body node of a function definition."""
        body_types = {"block", "statement_block", "compound_statement"}
        for child in node.children:
            if child.type in body_types:
                return child
        return None

    def _extract_docstring(self, node: Node, source: bytes, language: str) -> str | None:
        """Extract docstring from a function or class definition."""
        if language == "python":
            # Python: first child of body that is a string
            for child in node.children:
                if child.type == "block":
                    for stmt in child.children:
                        if stmt.type == "expression_statement":
                            for expr in stmt.children:
                                if expr.type == "string":
                                    text = self._node_text(expr, source)
                                    # Clean up triple quotes
                                    text = text.strip("'\"")
                                    if text.startswith("''"):
                                        text = text[2:-2]
                                    return text.strip()
                    break

        elif language in {"typescript", "javascript"}:
            # Look for JSDoc comment before the node
            prev = node.prev_sibling
            if prev and prev.type == "comment":
                text = self._node_text(prev, source)
                if text.startswith("/**"):
                    text = re.sub(r"^/\*\*\s*", "", text)
                    text = re.sub(r"\s*\*/$", "", text)
                    text = re.sub(r"\n\s*\*\s?", "\n", text)
                    return text.strip()

        elif language == "go":
            prev = node.prev_sibling
            if prev and prev.type == "comment":
                text = self._node_text(prev, source)
                text = re.sub(r"^//\s*", "", text)
                return text.strip()

        return None

    def _get_containing_class(self, node: Node, source: bytes) -> str | None:
        """Get the name of the class containing this node, if any.

        Returns the full nested class path for nested classes:
        - For a method in class Foo: returns "Foo"
        - For a method in class Inner inside class Outer: returns "Outer.Inner"
        """
        class_names: list[str] = []
        parent = node.parent

        while parent:
            if parent.type in {
                "class_definition",
                "class_declaration",
                "class_specifier",
                "impl_item",
            }:
                name = self._find_class_name(parent, source, "")
                if name:
                    class_names.append(name)
            parent = parent.parent

        if not class_names:
            return None

        # Reverse to get Outer.Inner order (we collected from inner to outer)
        class_names.reverse()
        return ".".join(class_names)

    def _is_async_function(self, node: Node, source: bytes, language: str) -> bool:
        """Check if a function is async.

        Handles all variations:
        - Python: async def, @decorator async def
        - TypeScript/JavaScript: async function, async () =>, async methods
        - Rust: async fn
        """
        if language == "python":
            # Check if the node itself has async keyword
            for child in node.children:
                if child.type == "async":
                    return True

            # Check parent for decorated async functions: @deco async def
            parent = node.parent
            if parent and parent.type == "decorated_definition":
                for child in parent.children:
                    if child.type == "async":
                        return True
                    # Check if there's an async keyword before the function def
                    if self._node_text(child, source) == "async":
                        return True

            # Check siblings (async def without decorator)
            prev = node.prev_sibling
            if prev:
                if prev.type == "async" or self._node_text(prev, source) == "async":
                    return True

        elif language in {"typescript", "javascript"}:
            # Check direct children for async keyword
            for child in node.children:
                if child.type == "async":
                    return True

            # For arrow functions, check parent variable declarator
            if node.type == "arrow_function":
                parent = node.parent
                if parent and parent.type == "variable_declarator":
                    # Check siblings of the arrow function for async
                    prev = node.prev_sibling
                    while prev:
                        if prev.type == "async" or self._node_text(prev, source) == "async":
                            return True
                        prev = prev.prev_sibling

            # For method definitions, check first child
            if node.type == "method_definition":
                for child in node.children:
                    if child.type == "async":
                        return True
                    # Stop after first non-async child
                    if child.type not in {"async", "static", "get", "set", "*"}:
                        break

        elif language == "rust":
            # Check for async keyword in children
            for child in node.children:
                if child.type == "async":
                    return True

        elif language == "go":
            # Go doesn't have async/await, but goroutines use `go` keyword
            # This is handled differently, not as a function modifier
            pass

        return False

    def _extract_decorators(self, node: Node, source: bytes, language: str) -> list[str]:
        """Extract decorators from a function or class definition.

        Uses AST-based extraction to properly handle:
        - Simple decorators: @decorator
        - Call decorators: @decorator(arg)
        - Nested call decorators: @decorator(nested(arg))
        - Attribute decorators: @module.decorator
        """
        decorators: list[str] = []

        if language == "python":
            parent = node.parent
            if parent and parent.type == "decorated_definition":
                for child in parent.children:
                    if child.type == "decorator":
                        deco_name = self._extract_decorator_name_ast(child, source)
                        if deco_name:
                            decorators.append(deco_name)

        elif language in {"typescript", "javascript"}:
            prev = node.prev_sibling
            while prev and prev.type == "decorator":
                deco_name = self._extract_decorator_name_ast(prev, source)
                if deco_name:
                    decorators.append(deco_name)
                prev = prev.prev_sibling

        return decorators

    def _extract_decorator_name_ast(self, decorator_node: Node, source: bytes) -> str | None:
        """Extract decorator name using AST traversal.

        Handles:
        - @foo -> "foo"
        - @foo.bar -> "foo.bar"
        - @foo() -> "foo"
        - @foo.bar(arg) -> "foo.bar"
        - @foo(nested(arg)) -> "foo"

        Args:
            decorator_node: The decorator AST node
            source: Source code bytes

        Returns:
            Decorator name without arguments
        """
        for child in decorator_node.children:
            # Skip the @ symbol
            if child.type == "@":
                continue

            # Direct identifier: @foo
            if child.type == "identifier":
                return self._node_text(child, source)

            # Attribute access: @foo.bar
            if child.type == "attribute":
                return self._node_text(child, source)

            # Call expression: @foo() or @foo.bar()
            if child.type == "call":
                # Get the function being called (the decorator name)
                for call_child in child.children:
                    if call_child.type == "identifier":
                        return self._node_text(call_child, source)
                    if call_child.type == "attribute":
                        return self._node_text(call_child, source)

            # TypeScript/JS decorator expression
            if child.type == "call_expression":
                for call_child in child.children:
                    if call_child.type == "identifier":
                        return self._node_text(call_child, source)
                    if call_child.type == "member_expression":
                        return self._node_text(call_child, source)

        return None

    def _extract_bases(self, node: Node, source: bytes, language: str) -> list[str]:
        """Extract base classes from a class definition."""
        bases: list[str] = []

        if language == "python":
            for child in node.children:
                if child.type == "argument_list":
                    for arg in child.children:
                        if arg.type in {"identifier", "attribute"}:
                            bases.append(self._node_text(arg, source))

        elif language in {"typescript", "javascript"}:
            for child in node.children:
                if child.type == "class_heritage":
                    for heritage in child.children:
                        if heritage.type == "extends_clause":
                            for ext in heritage.children:
                                if ext.type in {"identifier", "type_identifier"}:
                                    bases.append(self._node_text(ext, source))

        elif language == "java":
            for child in node.children:
                if child.type == "superclass":
                    for super_child in child.children:
                        if super_child.type == "type_identifier":
                            bases.append(self._node_text(super_child, source))

        return bases

    def _extract_method_names(self, node: Node, source: bytes, language: str) -> list[str]:
        """Extract method names from a class body."""
        methods: list[str] = []

        def find_methods(n: Node) -> None:
            if n.type in {
                "function_definition",
                "method_definition",
                "method_declaration",
                "function_item",
            }:
                name = self._find_function_name(n, source, language)
                if name:
                    methods.append(name)
            for child in n.children:
                find_methods(child)

        find_methods(node)
        return methods

    def _determine_type_kind(self, node: Node, language: str) -> str:
        """Determine the kind of type definition."""
        node_type = node.type

        if language == "typescript":
            if node_type == "interface_declaration":
                return "interface"
            elif node_type == "type_alias_declaration":
                return "type"

        elif language == "go":
            for child in node.children:
                if child.type == "type_spec":
                    for spec_child in child.children:
                        if spec_child.type == "struct_type":
                            return "struct"
                        elif spec_child.type == "interface_type":
                            return "interface"

        elif language == "rust":
            if node_type == "enum_item":
                return "enum"
            elif node_type == "type_item":
                return "type"

        return "type"

    def _extract_calls(
        self, body_node: Node, source: bytes, language: str
    ) -> tuple[list[str], list[CallInfo]]:
        """Extract function/method calls from a function body.

        Returns:
            Tuple of (simple call names list, detailed call info list)
        """
        call_query = self._queries[language]["call"]
        call_captures = self._run_query(call_query, body_node)

        calls: list[str] = []
        call_details: list[CallInfo] = []
        seen_names: set[str] = set()

        # Process function calls
        for call_name_node in call_captures.get("call.name", []):
            name = self._node_text(call_name_node, source)
            if name and name not in seen_names:
                seen_names.add(name)
                calls.append(name)

                # Determine call type
                call_type = CallType.FUNCTION

                # Check if it's a constructor (e.g., NewFoo in Go, uppercase in Python)
                if self._looks_like_constructor_call(name, language):
                    call_type = CallType.CONSTRUCTOR

                # Check if nested
                is_nested = self._is_nested_call(call_name_node)

                call_details.append(
                    CallInfo(
                        name=name,
                        call_type=call_type,
                        is_nested=is_nested,
                        line=call_name_node.start_point[0] + 1,
                    )
                )

        # Process method calls
        for call_method_node in call_captures.get("call.method", []):
            method_name = self._node_text(call_method_node, source)
            if not method_name:
                continue

            # Find the receiver (object the method is called on)
            receiver = self._find_call_receiver(call_method_node, source)

            # Check if chained
            is_chained = self._is_chained_call(call_method_node)

            # Check if nested
            is_nested = self._is_nested_call(call_method_node)

            # Determine call type
            call_type = CallType.METHOD

            # Check if it's a static method call (receiver is uppercase class name)
            if receiver and receiver[0].isupper():
                call_type = CallType.STATIC

            # Add to simple calls list (just the method name)
            if method_name not in seen_names:
                seen_names.add(method_name)
                calls.append(method_name)

            call_details.append(
                CallInfo(
                    name=method_name,
                    call_type=call_type,
                    receiver=receiver,
                    is_nested=is_nested,
                    is_chained=is_chained,
                    line=call_method_node.start_point[0] + 1,
                )
            )

        return calls, call_details

    def _find_call_receiver(self, method_node: Node, source: bytes) -> str | None:
        """Find the receiver object for a method call.

        Args:
            method_node: The method name node
            source: Source code bytes

        Returns:
            Receiver name or None
        """
        # Go up to find the member_expression/attribute/selector_expression
        parent = method_node.parent
        while parent:
            if parent.type in {
                "member_expression",  # JS/TS
                "attribute",  # Python
                "selector_expression",  # Go
                "field_expression",  # Rust/C++
            }:
                # Find the object node
                for child in parent.children:
                    if child.type in {"identifier", "this", "self"}:
                        return self._node_text(child, source)
                    if child.type in {"member_expression", "attribute", "selector_expression"}:
                        # Chained call, get the deepest identifier
                        return self._find_deepest_receiver(child, source)
                break
            parent = parent.parent
        return None

    def _find_deepest_receiver(self, node: Node, source: bytes) -> str | None:
        """Find the deepest receiver in a chain like a.b.c().d()."""
        for child in node.children:
            if child.type == "identifier":
                return self._node_text(child, source)
            if child.type in {"member_expression", "attribute", "selector_expression"}:
                return self._find_deepest_receiver(child, source)
        return None

    def _is_nested_call(self, node: Node) -> bool:
        """Check if a call is nested inside another call's arguments."""
        parent = node.parent
        while parent:
            if parent.type in {
                "call_expression",
                "call",
                "method_invocation",
            }:
                # Check if we're in the arguments, not the function position
                for child in parent.children:
                    if child.type in {"arguments", "argument_list", "formal_parameters"}:
                        if self._node_contains(child, node):
                            return True
            parent = parent.parent
        return False

    def _is_chained_call(self, node: Node) -> bool:
        """Check if a call is part of a method chain."""
        parent = node.parent
        while parent:
            if parent.type in {"member_expression", "attribute", "selector_expression"}:
                # Check if the object is a call_expression
                for child in parent.children:
                    if child.type in {"call_expression", "call", "method_invocation"}:
                        return True
            parent = parent.parent
        return False

    def _node_contains(self, parent: Node, target: Node) -> bool:
        """Check if parent node contains target node."""
        if parent == target:
            return True
        for child in parent.children:
            if self._node_contains(child, target):
                return True
        return False

    def _looks_like_constructor_call(self, name: str, language: str) -> bool:
        """Check if a function name looks like a constructor call."""
        if language == "go":
            # Go constructors: NewFoo, MakeFoo
            return name.startswith("New") or name.startswith("Make")
        elif language == "rust":
            # Rust constructors: new, new_with_*
            return name == "new" or name.startswith("new_")
        elif language in {"python", "java"}:
            # Classes start with uppercase
            return name[0].isupper() if name else False
        return False

    def _is_constructor(
        self, func_name: str, class_name: str | None, language: str
    ) -> bool:
        """Check if a function is a constructor.

        Args:
            func_name: Function name
            class_name: Containing class name (if any)
            language: Programming language

        Returns:
            True if this is a constructor
        """
        if language == "python":
            return func_name == "__init__"
        elif language in {"typescript", "javascript"}:
            return func_name == "constructor"
        elif language == "java":
            return class_name is not None and func_name == class_name
        elif language == "go":
            # Go doesn't have constructors, but convention is NewTypeName
            return func_name.startswith("New") if class_name is None else False
        elif language == "rust":
            # Rust convention is new() or new_with_*()
            return func_name == "new" or func_name.startswith("new_")
        elif language in {"c", "cpp"}:
            # C++ constructor has same name as class
            return class_name is not None and func_name == class_name
        return False

    def _extract_access_modifier(
        self, node: Node, source: bytes, language: str
    ) -> AccessModifier | None:
        """Extract access modifier from a function/class definition.

        Args:
            node: The definition node
            source: Source code bytes
            language: Programming language

        Returns:
            AccessModifier or None if no modifier
        """
        if language in {"typescript", "javascript"}:
            # Check for public/private/protected keywords
            for child in node.children:
                text = self._node_text(child, source)
                if text == "public":
                    return AccessModifier.PUBLIC
                elif text == "private":
                    return AccessModifier.PRIVATE
                elif text == "protected":
                    return AccessModifier.PROTECTED
            # TypeScript: also check for #privateField syntax
            if node.type == "method_definition":
                for child in node.children:
                    if child.type == "private_property_identifier":
                        return AccessModifier.PRIVATE

        elif language == "java":
            for child in node.children:
                if child.type == "modifiers":
                    text = self._node_text(child, source)
                    if "public" in text:
                        return AccessModifier.PUBLIC
                    elif "private" in text:
                        return AccessModifier.PRIVATE
                    elif "protected" in text:
                        return AccessModifier.PROTECTED
                    else:
                        return AccessModifier.PACKAGE  # Default in Java

        elif language == "python":
            # Python convention: _private, __very_private
            func_name = self._find_function_name(node, source, language)
            if func_name:
                if func_name.startswith("__") and not func_name.endswith("__"):
                    return AccessModifier.PRIVATE
                elif func_name.startswith("_"):
                    return AccessModifier.PROTECTED

        elif language == "rust":
            # Check for pub keyword
            for child in node.children:
                if child.type == "visibility_modifier":
                    text = self._node_text(child, source)
                    if "pub" in text:
                        return AccessModifier.PUBLIC
            # No pub = private by default
            return AccessModifier.PRIVATE

        return None

    def _is_static(self, node: Node, source: bytes, language: str) -> bool:
        """Check if a function is static.

        Args:
            node: The function definition node
            source: Source code bytes
            language: Programming language

        Returns:
            True if the function is static
        """
        if language in {"typescript", "javascript"}:
            for child in node.children:
                if child.type == "static" or self._node_text(child, source) == "static":
                    return True

        elif language == "java":
            for child in node.children:
                if child.type == "modifiers":
                    text = self._node_text(child, source)
                    if "static" in text:
                        return True

        elif language == "python":
            # Check for @staticmethod decorator
            parent = node.parent
            if parent and parent.type == "decorated_definition":
                for child in parent.children:
                    if child.type == "decorator":
                        deco_name = self._extract_decorator_name_ast(child, source)
                        if deco_name == "staticmethod":
                            return True

        return False

    def _is_abstract(self, node: Node, source: bytes, language: str) -> bool:
        """Check if a function/class is abstract.

        Args:
            node: The definition node
            source: Source code bytes
            language: Programming language

        Returns:
            True if the function/class is abstract
        """
        if language in {"typescript", "javascript"}:
            for child in node.children:
                if child.type == "abstract" or self._node_text(child, source) == "abstract":
                    return True

        elif language == "java":
            for child in node.children:
                if child.type == "modifiers":
                    text = self._node_text(child, source)
                    if "abstract" in text:
                        return True

        elif language == "python":
            # Check for @abstractmethod decorator
            parent = node.parent
            if parent and parent.type == "decorated_definition":
                for child in parent.children:
                    if child.type == "decorator":
                        deco_name = self._extract_decorator_name_ast(child, source)
                        if deco_name in {"abstractmethod", "abc.abstractmethod"}:
                            return True

        return False

    def _extract_type_parameters(
        self, node: Node, source: bytes, language: str
    ) -> list[TypeParameter]:
        """Extract generic type parameters from a function/class definition.

        Args:
            node: The definition node
            source: Source code bytes
            language: Programming language

        Returns:
            List of TypeParameter objects
        """
        type_params: list[TypeParameter] = []

        if language in {"typescript", "javascript"}:
            # Look for type_parameters node: <T, K extends string>
            for child in node.children:
                if child.type == "type_parameters":
                    for param_child in child.children:
                        if param_child.type == "type_parameter":
                            name = None
                            constraint = None
                            default = None
                            for tc in param_child.children:
                                if tc.type == "type_identifier":
                                    name = self._node_text(tc, source)
                                elif tc.type == "constraint":
                                    # Get everything after 'extends'
                                    constraint = self._node_text(tc, source)
                                    if constraint.startswith("extends "):
                                        constraint = constraint[8:]
                                elif tc.type == "default_type":
                                    default = self._node_text(tc, source)
                            if name:
                                type_params.append(TypeParameter(
                                    name=name,
                                    constraint=constraint,
                                    default=default,
                                ))

        elif language == "java":
            # Look for type_parameters node: <T, K extends Comparable<K>>
            for child in node.children:
                if child.type == "type_parameters":
                    for param_child in child.children:
                        if param_child.type == "type_parameter":
                            name = None
                            constraint = None
                            for tc in param_child.children:
                                if tc.type == "type_identifier":
                                    if name is None:
                                        name = self._node_text(tc, source)
                                    else:
                                        # This is the bound
                                        constraint = self._node_text(tc, source)
                                elif tc.type == "type_bound":
                                    constraint = self._node_text(tc, source)
                            if name:
                                type_params.append(TypeParameter(
                                    name=name,
                                    constraint=constraint,
                                ))

        elif language == "rust":
            # Look for type_parameters node: <T: Clone + Debug>
            for child in node.children:
                if child.type == "type_parameters":
                    for param_child in child.children:
                        if param_child.type == "type_identifier":
                            name = self._node_text(param_child, source)
                            type_params.append(TypeParameter(name=name))
                        elif param_child.type == "constrained_type_parameter":
                            name = None
                            constraint = None
                            for tc in param_child.children:
                                if tc.type == "type_identifier":
                                    name = self._node_text(tc, source)
                                elif tc.type == "trait_bounds":
                                    constraint = self._node_text(tc, source)
                            if name:
                                type_params.append(TypeParameter(
                                    name=name,
                                    constraint=constraint,
                                ))

        return type_params

    def _extract_return_type(
        self, node: Node, source: bytes, language: str
    ) -> str | None:
        """Extract return type annotation from a function definition.

        Args:
            node: The function definition node
            source: Source code bytes
            language: Programming language

        Returns:
            Return type string or None
        """
        if language == "python":
            # Look for -> type annotation
            for child in node.children:
                if child.type == "type":
                    return self._node_text(child, source)

        elif language in {"typescript", "javascript"}:
            # Look for type_annotation after parameters
            for child in node.children:
                if child.type == "type_annotation":
                    return self._node_text(child, source).lstrip(": ")

        elif language == "java":
            # Return type is before the method name
            for child in node.children:
                if child.type in {"type_identifier", "generic_type", "void_type", "array_type"}:
                    return self._node_text(child, source)

        elif language == "rust":
            # Look for return_type after ->
            for child in node.children:
                if child.type == "return_type":
                    type_text = self._node_text(child, source)
                    return type_text.lstrip("-> ").strip()

        elif language == "go":
            # Look for parameter_list for return types (Go uses multiple returns)
            found_params = False
            for child in node.children:
                if child.type == "parameter_list":
                    if found_params:
                        # Second parameter_list is return types
                        return self._node_text(child, source)
                    found_params = True

        return None

    def _extract_implements(
        self, node: Node, source: bytes, language: str
    ) -> list[str]:
        """Extract implemented interfaces from a class definition (Java).

        Args:
            node: The class definition node
            source: Source code bytes
            language: Programming language

        Returns:
            List of interface names
        """
        implements: list[str] = []

        if language == "java":
            for child in node.children:
                if child.type == "interfaces":
                    for iface_child in child.children:
                        if iface_child.type == "type_list":
                            for type_child in iface_child.children:
                                if type_child.type == "type_identifier":
                                    implements.append(self._node_text(type_child, source))

        return implements

    def parse_directory(
        self, directory: Path, repo_root: Path | None = None
    ) -> list[AnyEntity]:
        """Parse all supported files in a directory recursively.

        Args:
            directory: Directory to parse
            repo_root: Root of the repository (defaults to directory)

        Returns:
            List of all extracted entities
        """
        if repo_root is None:
            repo_root = directory

        all_entities: list[AnyEntity] = []

        for file_path in directory.rglob("*"):
            if file_path.is_file() and not should_ignore_path(file_path):
                if self.supports_file(file_path):
                    try:
                        entities = self.parse_file(file_path, repo_root)
                        all_entities.extend(entities)
                    except Exception as e:
                        logger.error(f"Failed to parse {file_path}: {e}")

        return all_entities
