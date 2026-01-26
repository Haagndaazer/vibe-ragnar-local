"""Graph module for code dependency analysis using NetworkX."""

from .builder import GraphBuilder, ScopedSymbolTable
from .import_resolver import ImportResolver, ResolvedImport
from .queries import (
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
from .storage import EdgeType, GraphStorage

__all__ = [
    # Storage
    "EdgeType",
    "GraphStorage",
    # Builder
    "GraphBuilder",
    "ScopedSymbolTable",
    # Import Resolution
    "ImportResolver",
    "ResolvedImport",
    # Queries
    "find_paths",
    "find_symbol",
    "get_call_chain",
    "get_callers",
    "get_class_hierarchy",
    "get_connected_components",
    "get_file_dependencies",
    "get_file_dependents",
    "get_file_structure",
    "get_function_calls",
]
