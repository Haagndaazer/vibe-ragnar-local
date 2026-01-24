"""Tree-sitter parser for extracting code entities from source files."""

import logging
import re
from pathlib import Path

from tree_sitter import Language, Node, Parser, Query, QueryCursor

from .entities import AnyEntity, Class, File, Function, TypeDefinition
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
            body_node = self._find_body(def_node, language)
            if body_node:
                call_captures = self._run_query(call_query, body_node)
                for call_name in call_captures.get("call.name", []):
                    calls.append(self._node_text(call_name, source))
                for call_method in call_captures.get("call.method", []):
                    calls.append(self._node_text(call_method, source))

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
                calls=list(set(calls)),  # Deduplicate
                is_async=is_async,
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
        """Get the name of the class containing this node, if any."""
        parent = node.parent
        while parent:
            if parent.type in {
                "class_definition",
                "class_declaration",
                "class_specifier",
                "impl_item",
            }:
                return self._find_class_name(parent, source, "")
            parent = parent.parent
        return None

    def _is_async_function(self, node: Node, source: bytes, language: str) -> bool:
        """Check if a function is async."""
        if language == "python":
            # Check parent for async
            parent = node.parent
            if parent and parent.type == "decorated_definition":
                for child in parent.children:
                    if self._node_text(child, source) == "async":
                        return True
            # Check siblings
            prev = node.prev_sibling
            if prev and self._node_text(prev, source) == "async":
                return True

        elif language in {"typescript", "javascript"}:
            for child in node.children:
                if child.type == "async":
                    return True

        elif language == "rust":
            for child in node.children:
                if child.type == "async":
                    return True

        return False

    def _extract_decorators(self, node: Node, source: bytes, language: str) -> list[str]:
        """Extract decorators from a function or class definition."""
        decorators: list[str] = []

        if language == "python":
            parent = node.parent
            if parent and parent.type == "decorated_definition":
                for child in parent.children:
                    if child.type == "decorator":
                        for deco_child in child.children:
                            if deco_child.type in {"identifier", "attribute", "call"}:
                                text = self._node_text(deco_child, source)
                                if "(" in text:
                                    text = text.split("(")[0]
                                decorators.append(text)
                                break

        elif language in {"typescript", "javascript"}:
            prev = node.prev_sibling
            while prev and prev.type == "decorator":
                text = self._node_text(prev, source)
                text = text.lstrip("@")
                if "(" in text:
                    text = text.split("(")[0]
                decorators.append(text)
                prev = prev.prev_sibling

        return decorators

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
