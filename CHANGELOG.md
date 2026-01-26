# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - 2025-01-26

### Changed

#### Agent Prompts
- Streamlined Explore and Plan agent instructions
- Removed verbose examples, kept essential guidance
- Cleaner MCP tool documentation

#### Plan Agent
- Added `Write` and `Edit` tools for plan file output
- New "Critical Files for Implementation" output section

#### Install Script
- Added model selection for Explore agent (haiku/sonnet)
- Added option to add `.claude/` to `.gitignore`
- Sonnet disclaimer about higher usage limits but better MCP integration

## [0.1.1] - 2025-01-26

### Added

#### Scoped Symbol Table
- Hierarchical symbol table with file-based scoping for better symbol resolution
- Qualified names support for methods (`ClassName.method`)
- Global scope for exported symbols with proper cross-file resolution

#### Enhanced Call Extraction
- New `CallInfo` model with detailed call information:
  - Call types: `function`, `method`, `constructor`, `decorator`, `static`
  - Receiver tracking for method calls (`obj.method()`)
  - Nested and chained call detection
  - Line number tracking for each call
- Constructor detection for Go (`NewType`) and Rust (`new()`)

#### Import Resolver
- New `ImportResolver` module with language-specific resolution:
  - Python: relative imports (`from . import`), absolute imports, alias imports
  - TypeScript/JavaScript: ES6 imports, relative paths
  - Go: package imports, standard library detection
  - Rust: `use` statements, `self`/`super`/`crate` paths
  - Java: package imports
  - C/C++: `#include` directives

#### JavaScript-Specific Queries
- Separate Tree-sitter queries for JavaScript (previously shared with TypeScript)
- Support for variable-assigned functions (`const fn = function() {}`)
- CommonJS `require()` detection
- `new` constructor call detection

#### Access Modifiers & Generics
- `AccessModifier` enum: `public`, `private`, `protected`, `internal`, `package`
- `TypeParameter` model for generic type parameters
- New fields on `Function`: `access_modifier`, `is_static`, `is_abstract`, `type_parameters`, `return_type`
- New fields on `Class`: `access_modifier`, `is_abstract`, `is_interface`, `type_parameters`, `implements`

### Fixed

- **Decorator extraction**: Now uses AST-based parsing instead of naive `split("(")[0]`
  - Correctly handles nested parentheses: `@decorator(nested(arg))`
  - Properly extracts attribute decorators: `@module.decorator`

- **Nested classes**: Returns full path (`Outer.Inner`) instead of just the immediate parent

- **Async function detection**: Extended support for all variations:
  - Python: decorated async functions (`@deco async def`)
  - TypeScript/JavaScript: async arrow functions, async methods
  - Rust: `async fn`

### Changed

- `GraphBuilder` now accepts optional `repo_root` parameter for import resolution
- Symbol table uses hierarchical scoping instead of flat dictionary
- JavaScript uses dedicated queries instead of sharing TypeScript queries

### Tests

- Added `tests/test_languages.py` with 40+ tests covering all 8 supported languages:
  - Python, TypeScript, JavaScript, Go, Rust, Java, C, C++
- Extended `tests/test_graph.py` with tests for all `GraphQueries` functions:
  - `get_callers`, `get_call_chain`, `get_file_dependencies`, `get_file_dependents`
  - `get_class_hierarchy`, `get_file_structure`, `get_connected_components`, `find_paths`
- Added tests for `ScopedSymbolTable`
- Total test count: 14 → 66

### Coverage Improvements

| Module | Before | After |
|--------|--------|-------|
| `parser/treesitter.py` | 55% | 78% |
| `graph/builder.py` | 49% | 70% |
| `graph/queries.py` | 26% | 90% |
| `parser/entities.py` | 95% | 94% |
| `parser/languages.py` | 92% | 92% |

## [0.1.0] - 2025-01-20

### Added

- Initial release
- MCP server for code indexing with semantic search
- Tree-sitter parsing for 8 languages: Python, TypeScript, JavaScript, Go, Rust, Java, C, C++
- NetworkX-based dependency graph
- MongoDB storage for embeddings
- Voyage AI integration for semantic embeddings
- File watcher for automatic reindexing
- Graph query tools: `get_function_calls`, `get_callers`, `get_call_chain`, `get_class_hierarchy`
- Semantic search tool

[0.1.2]: https://github.com/BlckLvls/vibe-ragnar/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/BlckLvls/vibe-ragnar/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/BlckLvls/vibe-ragnar/releases/tag/v0.1.0
