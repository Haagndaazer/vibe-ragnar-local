"""Language configurations for Tree-sitter parsing."""

from dataclasses import dataclass
from pathlib import Path

import tree_sitter_c as tsc
import tree_sitter_cpp as tscpp
import tree_sitter_go as tsgo
import tree_sitter_java as tsjava
import tree_sitter_javascript as tsjs
import tree_sitter_python as tspython
import tree_sitter_rust as tsrust
import tree_sitter_typescript as tsts
from tree_sitter import Language


@dataclass
class LanguageConfig:
    """Configuration for a programming language."""

    name: str
    extensions: tuple[str, ...]
    language: Language
    # Tree-sitter query patterns for extracting entities
    function_query: str
    class_query: str
    import_query: str
    call_query: str
    # Optional: type definition query (for TypeScript, Go)
    type_query: str | None = None


# Tree-sitter query patterns for Python
PYTHON_FUNCTION_QUERY = """
(function_definition
  name: (identifier) @function.name
  parameters: (parameters) @function.params
  body: (block) @function.body
) @function.def

(decorated_definition
  definition: (function_definition
    name: (identifier) @function.name
    parameters: (parameters) @function.params
    body: (block) @function.body
  ) @function.def
) @decorated
"""

PYTHON_CLASS_QUERY = """
(class_definition
  name: (identifier) @class.name
  body: (block) @class.body
) @class.def

(decorated_definition
  definition: (class_definition
    name: (identifier) @class.name
    body: (block) @class.body
  ) @class.def
) @decorated
"""

PYTHON_IMPORT_QUERY = """
(import_statement
  name: (dotted_name) @import.name
) @import

(import_from_statement
  module_name: (dotted_name) @import.module
) @import
"""

PYTHON_CALL_QUERY = """
(call
  function: (identifier) @call.name
)
(call
  function: (attribute
    attribute: (identifier) @call.method
  )
)
"""

# Tree-sitter query patterns for TypeScript/JavaScript
TS_FUNCTION_QUERY = """
(function_declaration
  name: (identifier) @function.name
  parameters: (formal_parameters) @function.params
  body: (statement_block) @function.body
) @function.def

(method_definition
  name: (property_identifier) @function.name
  parameters: (formal_parameters) @function.params
  body: (statement_block) @function.body
) @function.def

(arrow_function
  parameters: (formal_parameters) @function.params
  body: (_) @function.body
) @function.def
"""

TS_CLASS_QUERY = """
(class_declaration
  name: (type_identifier) @class.name
  body: (class_body) @class.body
) @class.def
"""

# JavaScript class query (uses identifier, not type_identifier)
JS_CLASS_QUERY = """
(class_declaration
  name: (identifier) @class.name
) @class.def
"""

TS_IMPORT_QUERY = """
(import_statement
  source: (string) @import.source
) @import

(import_clause
  (named_imports
    (import_specifier
      name: (identifier) @import.name
    )
  )
)
"""

TS_CALL_QUERY = """
(call_expression
  function: (identifier) @call.name
)
(call_expression
  function: (member_expression
    property: (property_identifier) @call.method
  )
)
"""

TS_TYPE_QUERY = """
(interface_declaration
  name: (type_identifier) @type.name
) @type.def

(type_alias_declaration
  name: (type_identifier) @type.name
) @type.def
"""

# Tree-sitter query patterns for Go
GO_FUNCTION_QUERY = """
(function_declaration
  name: (identifier) @function.name
  parameters: (parameter_list) @function.params
  body: (block) @function.body
) @function.def

(method_declaration
  name: (field_identifier) @function.name
  parameters: (parameter_list) @function.params
  body: (block) @function.body
) @function.def
"""

GO_CLASS_QUERY = """
(type_declaration
  (type_spec
    name: (type_identifier) @class.name
    type: (struct_type) @class.body
  )
) @class.def
"""

GO_IMPORT_QUERY = """
(import_declaration
  (import_spec
    path: (interpreted_string_literal) @import.path
  )
) @import

(import_declaration
  (import_spec_list
    (import_spec
      path: (interpreted_string_literal) @import.path
    )
  )
) @import
"""

GO_CALL_QUERY = """
(call_expression
  function: (identifier) @call.name
)
(call_expression
  function: (selector_expression
    field: (field_identifier) @call.method
  )
)
"""

GO_TYPE_QUERY = """
(type_declaration
  (type_spec
    name: (type_identifier) @type.name
    type: (interface_type) @type.body
  )
) @type.def
"""

# Tree-sitter query patterns for Rust
RUST_FUNCTION_QUERY = """
(function_item
  name: (identifier) @function.name
  parameters: (parameters) @function.params
  body: (block) @function.body
) @function.def
"""

RUST_CLASS_QUERY = """
(struct_item
  name: (type_identifier) @class.name
) @class.def

(impl_item
  type: (type_identifier) @class.name
  body: (declaration_list) @class.body
) @class.def
"""

RUST_IMPORT_QUERY = """
(use_declaration
  argument: (_) @import.path
) @import
"""

RUST_CALL_QUERY = """
(call_expression
  function: (identifier) @call.name
)
(call_expression
  function: (field_expression
    field: (field_identifier) @call.method
  )
)
"""

RUST_TYPE_QUERY = """
(type_item
  name: (type_identifier) @type.name
  type: (_) @type.def
) @type.def

(enum_item
  name: (type_identifier) @type.name
  body: (enum_variant_list) @type.body
) @type.def
"""

# Tree-sitter query patterns for Java
JAVA_FUNCTION_QUERY = """
(method_declaration
  name: (identifier) @function.name
  parameters: (formal_parameters) @function.params
  body: (block) @function.body
) @function.def

(constructor_declaration
  name: (identifier) @function.name
  parameters: (formal_parameters) @function.params
  body: (constructor_body) @function.body
) @function.def
"""

JAVA_CLASS_QUERY = """
(class_declaration
  name: (identifier) @class.name
  body: (class_body) @class.body
) @class.def

(interface_declaration
  name: (identifier) @class.name
  body: (interface_body) @class.body
) @class.def
"""

JAVA_IMPORT_QUERY = """
(import_declaration
  (scoped_identifier) @import.path
) @import
"""

JAVA_CALL_QUERY = """
(method_invocation
  name: (identifier) @call.name
)
(method_invocation
  object: (_)
  name: (identifier) @call.method
)
"""

# Tree-sitter query patterns for C
C_FUNCTION_QUERY = """
(function_definition
  declarator: (function_declarator
    declarator: (identifier) @function.name
    parameters: (parameter_list) @function.params
  )
  body: (compound_statement) @function.body
) @function.def
"""

C_CLASS_QUERY = """
(struct_specifier
  name: (type_identifier) @class.name
  body: (field_declaration_list) @class.body
) @class.def
"""

C_IMPORT_QUERY = """
(preproc_include
  path: (_) @import.path
) @import
"""

C_CALL_QUERY = """
(call_expression
  function: (identifier) @call.name
)
"""

# Tree-sitter query patterns for C++
CPP_FUNCTION_QUERY = """
(function_definition
  declarator: (function_declarator
    declarator: (identifier) @function.name
    parameters: (parameter_list) @function.params
  )
  body: (compound_statement) @function.body
) @function.def

(function_definition
  declarator: (function_declarator
    declarator: (qualified_identifier
      name: (identifier) @function.name
    )
    parameters: (parameter_list) @function.params
  )
  body: (compound_statement) @function.body
) @function.def
"""

CPP_CLASS_QUERY = """
(class_specifier
  name: (type_identifier) @class.name
  body: (field_declaration_list) @class.body
) @class.def

(struct_specifier
  name: (type_identifier) @class.name
  body: (field_declaration_list) @class.body
) @class.def
"""

CPP_IMPORT_QUERY = """
(preproc_include
  path: (_) @import.path
) @import
"""

CPP_CALL_QUERY = """
(call_expression
  function: (identifier) @call.name
)
(call_expression
  function: (field_expression
    field: (field_identifier) @call.method
  )
)
"""


def _create_language_configs() -> dict[str, LanguageConfig]:
    """Create language configurations with Tree-sitter languages."""
    return {
        "python": LanguageConfig(
            name="python",
            extensions=(".py", ".pyw"),
            language=Language(tspython.language()),
            function_query=PYTHON_FUNCTION_QUERY,
            class_query=PYTHON_CLASS_QUERY,
            import_query=PYTHON_IMPORT_QUERY,
            call_query=PYTHON_CALL_QUERY,
        ),
        "typescript": LanguageConfig(
            name="typescript",
            extensions=(".ts", ".tsx"),
            language=Language(tsts.language_typescript()),
            function_query=TS_FUNCTION_QUERY,
            class_query=TS_CLASS_QUERY,
            import_query=TS_IMPORT_QUERY,
            call_query=TS_CALL_QUERY,
            type_query=TS_TYPE_QUERY,
        ),
        "javascript": LanguageConfig(
            name="javascript",
            extensions=(".js", ".jsx", ".mjs", ".cjs"),
            language=Language(tsjs.language()),
            function_query=TS_FUNCTION_QUERY,  # JS uses same queries as TS
            class_query=JS_CLASS_QUERY,
            import_query=TS_IMPORT_QUERY,
            call_query=TS_CALL_QUERY,
        ),
        "go": LanguageConfig(
            name="go",
            extensions=(".go",),
            language=Language(tsgo.language()),
            function_query=GO_FUNCTION_QUERY,
            class_query=GO_CLASS_QUERY,
            import_query=GO_IMPORT_QUERY,
            call_query=GO_CALL_QUERY,
            type_query=GO_TYPE_QUERY,
        ),
        "rust": LanguageConfig(
            name="rust",
            extensions=(".rs",),
            language=Language(tsrust.language()),
            function_query=RUST_FUNCTION_QUERY,
            class_query=RUST_CLASS_QUERY,
            import_query=RUST_IMPORT_QUERY,
            call_query=RUST_CALL_QUERY,
            type_query=RUST_TYPE_QUERY,
        ),
        "java": LanguageConfig(
            name="java",
            extensions=(".java",),
            language=Language(tsjava.language()),
            function_query=JAVA_FUNCTION_QUERY,
            class_query=JAVA_CLASS_QUERY,
            import_query=JAVA_IMPORT_QUERY,
            call_query=JAVA_CALL_QUERY,
        ),
        "c": LanguageConfig(
            name="c",
            extensions=(".c", ".h"),
            language=Language(tsc.language()),
            function_query=C_FUNCTION_QUERY,
            class_query=C_CLASS_QUERY,
            import_query=C_IMPORT_QUERY,
            call_query=C_CALL_QUERY,
        ),
        "cpp": LanguageConfig(
            name="cpp",
            extensions=(".cpp", ".hpp", ".cc", ".cxx", ".hxx", ".h++"),
            language=Language(tscpp.language()),
            function_query=CPP_FUNCTION_QUERY,
            class_query=CPP_CLASS_QUERY,
            import_query=CPP_IMPORT_QUERY,
            call_query=CPP_CALL_QUERY,
        ),
    }


# Singleton instance of language configs
LANGUAGE_CONFIGS = _create_language_configs()

# Map file extensions to language names
EXTENSION_TO_LANGUAGE: dict[str, str] = {}
for lang_name, config in LANGUAGE_CONFIGS.items():
    for ext in config.extensions:
        EXTENSION_TO_LANGUAGE[ext] = lang_name


def get_language_for_file(file_path: Path | str) -> str | None:
    """Get the language name for a file based on its extension.

    Args:
        file_path: Path to the file

    Returns:
        Language name or None if not supported
    """
    path = Path(file_path)
    ext = path.suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(ext)


def get_language_config(language: str) -> LanguageConfig | None:
    """Get the language configuration for a language.

    Args:
        language: Language name

    Returns:
        LanguageConfig or None if not supported
    """
    return LANGUAGE_CONFIGS.get(language)


def is_supported_file(file_path: Path | str) -> bool:
    """Check if a file is supported for parsing.

    Args:
        file_path: Path to the file

    Returns:
        True if the file extension is supported
    """
    return get_language_for_file(file_path) is not None


# Directories to ignore when scanning for files
IGNORED_DIRECTORIES = frozenset({
    # JavaScript/Node
    "node_modules",
    ".next",
    ".nuxt",
    # React Native / Mobile
    "android",
    "ios",
    ".expo",
    ".expo-shared",
    # Java/Gradle
    ".gradle",
    ".idea",
    # Python
    "__pycache__",
    ".venv",
    "venv",
    ".env",
    ".tox",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov",
    ".coverage",
    "egg-info",
    ".eggs",
    # Rust
    "target",
    # Go
    "vendor",
    # Git
    ".git",
    # Build outputs
    "dist",
    "build",
    "out",
    ".output",
    # Coverage
    "coverage",
})


def should_ignore_path(path: Path) -> bool:
    """Check if a path should be ignored during scanning.

    Args:
        path: Path to check

    Returns:
        True if the path should be ignored
    """
    # Check if any part of the path is in the ignored set
    for part in path.parts:
        if part in IGNORED_DIRECTORIES:
            return True
        # Also ignore hidden directories (except .github, etc.)
        if part.startswith(".") and part not in {".github", ".gitlab"}:
            return True
    return False
