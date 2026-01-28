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
from tree_sitter_language_pack import get_language as get_language_pack


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

# Separate JavaScript query patterns
# JS needs different queries because:
# 1. JS uses `identifier` for class names, not `type_identifier`
# 2. JS supports CommonJS require()
# 3. Variable-assigned functions are more common in JS

JS_FUNCTION_QUERY = """
; Regular function declaration
(function_declaration
  name: (identifier) @function.name
  parameters: (formal_parameters) @function.params
  body: (statement_block) @function.body
) @function.def

; Method definition in class
(method_definition
  name: (property_identifier) @function.name
  parameters: (formal_parameters) @function.params
  body: (statement_block) @function.body
) @function.def

; Arrow function (standalone)
(arrow_function
  parameters: (formal_parameters) @function.params
  body: (_) @function.body
) @function.def

; Variable-assigned function: const foo = function() {}
(lexical_declaration
  (variable_declarator
    name: (identifier) @function.name
    value: (function_expression
      parameters: (formal_parameters) @function.params
      body: (statement_block) @function.body
    ) @function.def
  )
)

; Variable-assigned arrow function: const foo = () => {}
(lexical_declaration
  (variable_declarator
    name: (identifier) @function.name
    value: (arrow_function
      parameters: (formal_parameters) @function.params
      body: (_) @function.body
    ) @function.def
  )
)

; var-assigned function: var foo = function() {}
(variable_declaration
  (variable_declarator
    name: (identifier) @function.name
    value: (function_expression
      parameters: (formal_parameters) @function.params
      body: (statement_block) @function.body
    ) @function.def
  )
)

; var-assigned arrow function: var foo = () => {}
(variable_declaration
  (variable_declarator
    name: (identifier) @function.name
    value: (arrow_function
      parameters: (formal_parameters) @function.params
      body: (_) @function.body
    ) @function.def
  )
)
"""

JS_IMPORT_QUERY = """
; ES6 import: import x from 'module'
(import_statement
  source: (string) @import.source
) @import

; ES6 named imports: import { x } from 'module'
(import_clause
  (named_imports
    (import_specifier
      name: (identifier) @import.name
    )
  )
)

; CommonJS require: const x = require('module')
(lexical_declaration
  (variable_declarator
    value: (call_expression
      function: (identifier) @_require
      arguments: (arguments (string) @import.source)
    )
  )
  (#eq? @_require "require")
)

; CommonJS require with var: var x = require('module')
(variable_declaration
  (variable_declarator
    value: (call_expression
      function: (identifier) @_require
      arguments: (arguments (string) @import.source)
    )
  )
  (#eq? @_require "require")
)

; Dynamic import: import('module')
(call_expression
  function: (import)
  arguments: (arguments (string) @import.source)
)
"""

JS_CALL_QUERY = """
; Function call: foo()
(call_expression
  function: (identifier) @call.name
)

; Method call: obj.method()
(call_expression
  function: (member_expression
    property: (property_identifier) @call.method
  )
)

; new constructor: new Foo()
(new_expression
  constructor: (identifier) @call.name
)
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

# Tree-sitter query patterns for Dart
# Note: Dart has a unique AST structure where functions are split into
# function_signature + function_body nodes at the top level.
# Dart uses positional children, not named fields (e.g., (identifier) not name: (identifier))
DART_FUNCTION_QUERY = """
; Top-level function declarations (direct child of program - avoids matching nested)
(program
  (function_signature
    (identifier) @function.name
  ) @function.def
)

; Method declarations inside classes (regular methods)
(method_signature
  (function_signature
    (identifier) @function.name
  )
) @function.def

; Getter declarations
(method_signature
  (getter_signature
    (identifier) @function.name
  )
) @function.def

; Setter declarations
(method_signature
  (setter_signature
    (identifier) @function.name
  )
) @function.def
"""

DART_CLASS_QUERY = """
; Class declarations
(class_definition
  (identifier) @class.name
  (class_body) @class.body
) @class.def

; Mixin declarations
(mixin_declaration
  (identifier) @class.name
  (class_body) @class.body
) @class.def

; Extension declarations
(extension_declaration
  (identifier) @class.name
) @class.def

; Enum declarations
(enum_declaration
  (identifier) @class.name
) @class.def
"""

DART_IMPORT_QUERY = """
; Import statements: import 'package:foo/bar.dart';
(import_specification
  (configurable_uri
    (uri
      (string_literal) @import.path
    )
  )
) @import

; Export statements: export 'src/widget.dart';
(library_export
  (configurable_uri
    (uri
      (string_literal) @import.path
    )
  )
) @import

; Part directives: part 'part_file.dart';
(part_directive
  (uri
    (string_literal) @import.path
  )
) @import
"""

DART_CALL_QUERY = """
; Simple function call: foo()
; In Dart, calls are identifier + selector with argument_part
(expression_statement
  (identifier) @call.name
  (selector
    (argument_part)
  )
)

; Method/property access call: obj.method()
(expression_statement
  (identifier)
  (selector
    (unconditional_assignable_selector
      (identifier) @call.method
    )
  )
)
"""

DART_TYPE_QUERY = """
; Type alias: typedef IntList = List<int>;
(type_alias
  (type_identifier) @type.name
) @type.def
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
            function_query=JS_FUNCTION_QUERY,  # JS-specific queries
            class_query=JS_CLASS_QUERY,
            import_query=JS_IMPORT_QUERY,
            call_query=JS_CALL_QUERY,
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
        "dart": LanguageConfig(
            name="dart",
            extensions=(".dart",),
            language=get_language_pack("dart"),
            function_query=DART_FUNCTION_QUERY,
            class_query=DART_CLASS_QUERY,
            import_query=DART_IMPORT_QUERY,
            call_query=DART_CALL_QUERY,
            type_query=DART_TYPE_QUERY,
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
    # === Version Control ===
    ".git",
    ".svn",
    ".hg",

    # === Python ===
    "__pycache__",
    ".venv",
    "venv",
    ".env",
    "env",
    "ENV",
    ".tox",
    ".nox",
    ".pytest_cache",
    ".mypy_cache",
    ".pytype",
    ".ruff_cache",
    ".coverage",
    "htmlcov",
    "coverage",
    ".eggs",
    "egg-info",
    "wheels",
    "sdist",
    ".Python",
    "lib",
    "lib64",

    # === JavaScript / TypeScript ===
    "node_modules",
    ".npm",
    ".pnpm-store",
    ".yarn",
    "bower_components",
    ".cache",
    ".parcel-cache",
    ".turbo",

    # === JS Frameworks ===
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".vitepress",
    ".docusaurus",
    ".astro",
    ".remix",
    "storybook-static",
    ".vercel",
    ".netlify",

    # === React Native / Mobile ===
    "android",
    "ios",
    ".expo",
    ".expo-shared",
    "Pods",
    ".bundle",
    "DerivedData",
    "xcuserdata",

    # === Go ===
    "vendor",
    "bin",
    "pkg",

    # === Rust ===
    "target",

    # === Dart / Flutter ===
    ".dart_tool",
    ".pub-cache",
    ".pub",
    ".packages",
    ".fvm",

    # === Java ===
    ".gradle",
    ".mvn",
    ".settings",

    # === C / C++ ===
    "CMakeFiles",
    "cmake-build-debug",
    "cmake-build-release",
    "Debug",
    "Release",
    "x64",
    "x86",
    "ipch",
    ".ccls-cache",

    # === IDEs ===
    ".idea",
    ".vscode",
    ".vs",
    ".eclipse",
    "nbproject",

    # === Build Outputs ===
    "dist",
    "build",
    "out",
    ".output",

    # === Misc ===
    "logs",
    "log",
    "tmp",
    "temp",
    ".tmp",
    ".temp",
    ".local",
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
