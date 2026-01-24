"""Query functions for traversing the code dependency graph."""

import logging
from typing import Any

import networkx as nx

from ..parser.entities import EntityType
from .storage import EdgeType, GraphStorage

logger = logging.getLogger(__name__)


def get_function_calls(storage: GraphStorage, function_id: str) -> list[dict[str, Any]]:
    """Get all functions that a given function calls.

    Args:
        storage: Graph storage instance
        function_id: ID of the function to query

    Returns:
        List of called function details
    """
    result = []
    for target_id, edge_data in storage.get_successors(function_id, EdgeType.CALLS):
        node_data = storage.get_entity(target_id)
        if node_data:
            result.append({
                "id": target_id,
                "name": node_data.get("name"),
                "file_path": node_data.get("file_path"),
                "type": node_data.get("type"),
            })
    return result


def get_callers(storage: GraphStorage, function_id: str) -> list[dict[str, Any]]:
    """Get all functions that call a given function.

    Args:
        storage: Graph storage instance
        function_id: ID of the function to query

    Returns:
        List of caller function details
    """
    result = []
    for source_id, edge_data in storage.get_predecessors(function_id, EdgeType.CALLS):
        node_data = storage.get_entity(source_id)
        if node_data:
            result.append({
                "id": source_id,
                "name": node_data.get("name"),
                "file_path": node_data.get("file_path"),
                "type": node_data.get("type"),
            })
    return result


def get_call_chain(
    storage: GraphStorage,
    function_id: str,
    max_depth: int = 5,
    direction: str = "outgoing",
) -> dict[str, Any]:
    """Get the call chain from/to a function.

    Args:
        storage: Graph storage instance
        function_id: ID of the function to start from
        max_depth: Maximum depth to traverse
        direction: "outgoing" (what it calls) or "incoming" (what calls it)

    Returns:
        Nested dictionary representing the call tree
    """
    visited: set[str] = set()

    def traverse(node_id: str, depth: int) -> dict[str, Any]:
        if depth > max_depth or node_id in visited:
            node_data = storage.get_entity(node_id)
            return {
                "id": node_id,
                "name": node_data.get("name") if node_data else "unknown",
                "truncated": depth > max_depth,
                "cycle": node_id in visited,
                "calls": [] if direction == "outgoing" else None,
                "callers": [] if direction == "incoming" else None,
            }

        visited.add(node_id)
        node_data = storage.get_entity(node_id)

        result: dict[str, Any] = {
            "id": node_id,
            "name": node_data.get("name") if node_data else "unknown",
            "file_path": node_data.get("file_path") if node_data else None,
            "truncated": False,
            "cycle": False,
        }

        if direction == "outgoing":
            calls = []
            for target_id, _ in storage.get_successors(node_id, EdgeType.CALLS):
                calls.append(traverse(target_id, depth + 1))
            result["calls"] = calls
        else:
            callers = []
            for source_id, _ in storage.get_predecessors(node_id, EdgeType.CALLS):
                callers.append(traverse(source_id, depth + 1))
            result["callers"] = callers

        return result

    return traverse(function_id, 0)


def get_file_dependencies(storage: GraphStorage, file_id: str) -> list[dict[str, Any]]:
    """Get all files/modules that a file imports.

    Args:
        storage: Graph storage instance
        file_id: ID of the file to query

    Returns:
        List of imported file/module details
    """
    result = []
    for target_id, edge_data in storage.get_successors(file_id, EdgeType.IMPORTS):
        node_data = storage.get_entity(target_id)
        if node_data:
            result.append({
                "id": target_id,
                "name": node_data.get("name"),
                "file_path": node_data.get("file_path"),
                "type": node_data.get("type"),
                "is_external": node_data.get("type") == "external",
            })
    return result


def get_file_dependents(storage: GraphStorage, file_id: str) -> list[dict[str, Any]]:
    """Get all files that import a given file.

    Args:
        storage: Graph storage instance
        file_id: ID of the file to query

    Returns:
        List of files that import this file
    """
    result = []
    for source_id, edge_data in storage.get_predecessors(file_id, EdgeType.IMPORTS):
        node_data = storage.get_entity(source_id)
        if node_data:
            result.append({
                "id": source_id,
                "name": node_data.get("name"),
                "file_path": node_data.get("file_path"),
            })
    return result


def get_class_hierarchy(
    storage: GraphStorage,
    class_id: str,
    direction: str = "both",
) -> dict[str, Any]:
    """Get the inheritance hierarchy for a class.

    Args:
        storage: Graph storage instance
        class_id: ID of the class to query
        direction: "parents" (ancestors), "children" (descendants), or "both"

    Returns:
        Hierarchy structure with ancestors and/or descendants
    """
    node_data = storage.get_entity(class_id)
    result: dict[str, Any] = {
        "id": class_id,
        "name": node_data.get("name") if node_data else "unknown",
        "file_path": node_data.get("file_path") if node_data else None,
    }

    if direction in ("both", "parents"):
        # Get parent classes (what this class inherits from)
        parents = []
        for target_id, _ in storage.get_successors(class_id, EdgeType.INHERITS):
            parent_data = storage.get_entity(target_id)
            if parent_data:
                parents.append({
                    "id": target_id,
                    "name": parent_data.get("name"),
                    "file_path": parent_data.get("file_path"),
                    "is_external": parent_data.get("type") == "external",
                })
        result["parents"] = parents

    if direction in ("both", "children"):
        # Get child classes (classes that inherit from this)
        children = []
        for source_id, _ in storage.get_predecessors(class_id, EdgeType.INHERITS):
            child_data = storage.get_entity(source_id)
            if child_data:
                children.append({
                    "id": source_id,
                    "name": child_data.get("name"),
                    "file_path": child_data.get("file_path"),
                })
        result["children"] = children

    return result


def find_symbol(
    storage: GraphStorage,
    name: str,
    file_context: str | None = None,
) -> list[dict[str, Any]]:
    """Find a symbol (function, class, etc.) by name.

    Args:
        storage: Graph storage instance
        name: Name of the symbol to find
        file_context: Optional file path to prioritize local definitions

    Returns:
        List of matching entities, sorted by relevance
    """
    results = []

    for node_id, data in storage.graph.nodes(data=True):
        node_name = data.get("name", "")

        # Exact match
        if node_name == name:
            score = 100
            # Boost score if in same file
            if file_context and data.get("file_path") == file_context:
                score += 50
            results.append({
                "id": node_id,
                "name": node_name,
                "file_path": data.get("file_path"),
                "type": data.get("type"),
                "start_line": data.get("start_line"),
                "end_line": data.get("end_line"),
                "score": score,
            })

        # Partial match (name ends with the search term - for qualified names)
        elif node_name.endswith(f".{name}") or node_id.endswith(f":{name}"):
            score = 50
            if file_context and data.get("file_path") == file_context:
                score += 25
            results.append({
                "id": node_id,
                "name": node_name,
                "file_path": data.get("file_path"),
                "type": data.get("type"),
                "start_line": data.get("start_line"),
                "end_line": data.get("end_line"),
                "score": score,
            })

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def get_file_structure(storage: GraphStorage, file_id: str) -> dict[str, Any]:
    """Get the structure of a file (classes, functions, imports).

    Args:
        storage: Graph storage instance
        file_id: ID of the file

    Returns:
        File structure with classes and functions
    """
    file_data = storage.get_entity(file_id)
    if not file_data:
        return {"error": f"File not found: {file_id}"}

    result: dict[str, Any] = {
        "id": file_id,
        "name": file_data.get("name"),
        "file_path": file_data.get("file_path"),
        "classes": [],
        "functions": [],
        "imports": [],
    }

    # Get all entities defined in this file
    for target_id, _ in storage.get_successors(file_id, EdgeType.DEFINES):
        entity_data = storage.get_entity(target_id)
        if not entity_data:
            continue

        entity_type = entity_data.get("type")
        entity_info = {
            "id": target_id,
            "name": entity_data.get("name"),
            "start_line": entity_data.get("start_line"),
            "end_line": entity_data.get("end_line"),
        }

        if entity_type == EntityType.CLASS.value:
            # Get methods for this class
            methods = []
            for method_id, _ in storage.get_successors(target_id, EdgeType.CONTAINS):
                method_data = storage.get_entity(method_id)
                if method_data:
                    methods.append({
                        "name": method_data.get("name"),
                        "start_line": method_data.get("start_line"),
                    })
            entity_info["methods"] = methods
            result["classes"].append(entity_info)

        elif entity_type == EntityType.FUNCTION.value:
            # Only add top-level functions (not methods)
            data_dict = entity_data.get("data", {})
            if not data_dict.get("class_name"):
                result["functions"].append(entity_info)

    # Get imports
    for target_id, _ in storage.get_successors(file_id, EdgeType.IMPORTS):
        entity_data = storage.get_entity(target_id)
        if entity_data:
            result["imports"].append({
                "name": entity_data.get("name"),
                "is_external": entity_data.get("type") == "external",
            })

    return result


def get_connected_components(storage: GraphStorage) -> list[list[str]]:
    """Get all connected components in the graph.

    Args:
        storage: Graph storage instance

    Returns:
        List of component lists (each component is a list of entity IDs)
    """
    # Use weakly connected components for directed graph
    components = list(nx.weakly_connected_components(storage.graph))
    return [list(comp) for comp in components]


def find_paths(
    storage: GraphStorage,
    source_id: str,
    target_id: str,
    max_length: int = 10,
) -> list[list[str]]:
    """Find all paths between two entities.

    Args:
        storage: Graph storage instance
        source_id: Starting entity ID
        target_id: Ending entity ID
        max_length: Maximum path length

    Returns:
        List of paths (each path is a list of entity IDs)
    """
    try:
        paths = list(
            nx.all_simple_paths(
                storage.graph, source_id, target_id, cutoff=max_length
            )
        )
        return paths
    except nx.NetworkXError:
        return []
