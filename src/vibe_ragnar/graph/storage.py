"""Graph storage using NetworkX for in-memory code dependency graph."""

import logging
from enum import Enum
from typing import Any

import networkx as nx

from ..parser.entities import AnyEntity, Class, EntityType, File, Function, TypeDefinition

logger = logging.getLogger(__name__)


class EdgeType(str, Enum):
    """Types of edges in the code graph."""

    IMPORTS = "imports"  # File A imports module B
    DEFINES = "defines"  # File/Class defines Function
    CALLS = "calls"  # Function A calls Function B
    INHERITS = "inherits"  # Class A inherits from Class B
    USES = "uses"  # Function uses Type/Variable
    CONTAINS = "contains"  # File contains Class/Function


class GraphStorage:
    """In-memory graph storage using NetworkX DiGraph."""

    def __init__(self):
        """Initialize an empty directed graph."""
        self._graph = nx.DiGraph()

    @property
    def graph(self) -> nx.DiGraph:
        """Access the underlying NetworkX graph."""
        return self._graph

    def add_entity(self, entity: AnyEntity) -> None:
        """Add an entity as a node in the graph.

        Args:
            entity: The code entity to add
        """
        self._graph.add_node(
            entity.id,
            type=entity.entity_type.value,
            name=entity.name,
            file_path=entity.file_path,
            start_line=entity.start_line,
            end_line=entity.end_line,
            data=entity.model_dump(),
        )

    def remove_entity(self, entity_id: str) -> None:
        """Remove an entity from the graph.

        Args:
            entity_id: ID of the entity to remove
        """
        if entity_id in self._graph:
            self._graph.remove_node(entity_id)

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """Get an entity by its ID.

        Args:
            entity_id: ID of the entity

        Returns:
            Node data or None if not found
        """
        if entity_id in self._graph:
            return dict(self._graph.nodes[entity_id])
        return None

    def has_entity(self, entity_id: str) -> bool:
        """Check if an entity exists in the graph.

        Args:
            entity_id: ID of the entity

        Returns:
            True if the entity exists
        """
        return entity_id in self._graph

    def add_edge(self, from_id: str, to_id: str, edge_type: EdgeType) -> None:
        """Add an edge between two entities.

        Args:
            from_id: Source entity ID
            to_id: Target entity ID
            edge_type: Type of the relationship
        """
        # Only add edge if both nodes exist
        if from_id in self._graph and to_id in self._graph:
            self._graph.add_edge(from_id, to_id, type=edge_type.value)

    def add_edge_by_name(
        self, from_id: str, to_name: str, edge_type: EdgeType, create_if_missing: bool = False
    ) -> bool:
        """Add an edge to an entity by name (creates external reference if needed).

        Args:
            from_id: Source entity ID
            to_name: Target entity name (will be resolved or created)
            edge_type: Type of the relationship
            create_if_missing: Create a placeholder node if target doesn't exist

        Returns:
            True if edge was added
        """
        if from_id not in self._graph:
            return False

        # Try to find existing node with this name
        to_id = self._find_by_name(to_name)

        if to_id is None and create_if_missing:
            # Create external reference node
            to_id = f"external:{to_name}"
            self._graph.add_node(to_id, type="external", name=to_name)

        if to_id:
            self._graph.add_edge(from_id, to_id, type=edge_type.value)
            return True

        return False

    def _find_by_name(self, name: str) -> str | None:
        """Find an entity ID by its name.

        Args:
            name: Entity name to search for

        Returns:
            Entity ID or None if not found
        """
        for node_id, data in self._graph.nodes(data=True):
            if data.get("name") == name:
                return node_id
        return None

    def get_successors(
        self, entity_id: str, edge_type: EdgeType | None = None
    ) -> list[tuple[str, dict[str, Any]]]:
        """Get all entities that this entity points to.

        Args:
            entity_id: Source entity ID
            edge_type: Filter by edge type (optional)

        Returns:
            List of (target_id, edge_data) tuples
        """
        if entity_id not in self._graph:
            return []

        result = []
        for _, target_id, edge_data in self._graph.out_edges(entity_id, data=True):
            if edge_type is None or edge_data.get("type") == edge_type.value:
                result.append((target_id, edge_data))

        return result

    def get_predecessors(
        self, entity_id: str, edge_type: EdgeType | None = None
    ) -> list[tuple[str, dict[str, Any]]]:
        """Get all entities that point to this entity.

        Args:
            entity_id: Target entity ID
            edge_type: Filter by edge type (optional)

        Returns:
            List of (source_id, edge_data) tuples
        """
        if entity_id not in self._graph:
            return []

        result = []
        for source_id, _, edge_data in self._graph.in_edges(entity_id, data=True):
            if edge_type is None or edge_data.get("type") == edge_type.value:
                result.append((source_id, edge_data))

        return result

    def get_entities_by_type(self, entity_type: EntityType) -> list[str]:
        """Get all entity IDs of a specific type.

        Args:
            entity_type: Type of entities to find

        Returns:
            List of entity IDs
        """
        return [
            node_id
            for node_id, data in self._graph.nodes(data=True)
            if data.get("type") == entity_type.value
        ]

    def get_entities_by_file(self, file_path: str) -> list[str]:
        """Get all entity IDs in a specific file.

        Args:
            file_path: Path to the file

        Returns:
            List of entity IDs
        """
        return [
            node_id
            for node_id, data in self._graph.nodes(data=True)
            if data.get("file_path") == file_path
        ]

    def get_statistics(self) -> dict[str, int]:
        """Get graph statistics.

        Returns:
            Dictionary with counts of nodes, edges, and entity types
        """
        stats = {
            "nodes": self._graph.number_of_nodes(),
            "edges": self._graph.number_of_edges(),
            "functions": 0,
            "classes": 0,
            "files": 0,
            "types": 0,
            "external": 0,
        }

        for _, data in self._graph.nodes(data=True):
            entity_type = data.get("type", "")
            if entity_type == EntityType.FUNCTION.value:
                stats["functions"] += 1
            elif entity_type == EntityType.CLASS.value:
                stats["classes"] += 1
            elif entity_type == EntityType.FILE.value:
                stats["files"] += 1
            elif entity_type == EntityType.TYPE.value:
                stats["types"] += 1
            elif entity_type == "external":
                stats["external"] += 1

        return stats

    def clear(self) -> None:
        """Clear all nodes and edges from the graph."""
        self._graph.clear()

    def remove_file(self, file_path: str) -> list[str]:
        """Remove all entities from a specific file.

        Args:
            file_path: Path to the file

        Returns:
            List of removed entity IDs
        """
        to_remove = self.get_entities_by_file(file_path)
        for entity_id in to_remove:
            self._graph.remove_node(entity_id)
        return to_remove
