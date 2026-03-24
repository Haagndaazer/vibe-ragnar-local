"""JSONL-backed graph storage for the Cognition History Graph."""

import json
import logging
from pathlib import Path
from typing import Any

import networkx as nx

from .models import CognitionEdge, CognitionEdgeType, CognitionNode, CognitionNodeType

logger = logging.getLogger(__name__)

JOURNAL_FILENAME = "journal.jsonl"


class CognitionStorage:
    """Cognition graph storage: JSONL source of truth + NetworkX in-memory graph.

    Writes append to JSONL immediately. The NetworkX graph is hydrated from
    JSONL at startup and updated in-place on every write.
    """

    def __init__(self, cognition_dir: Path):
        """Initialize storage, hydrating from JSONL if it exists.

        Args:
            cognition_dir: Directory for .cognition/ files (Git-committed)
        """
        self._dir = cognition_dir
        self._journal_path = cognition_dir / JOURNAL_FILENAME
        self._graph = nx.DiGraph()

        self._dir.mkdir(parents=True, exist_ok=True)

        if self._journal_path.exists():
            self._hydrate()

    @property
    def graph(self) -> nx.DiGraph:
        """Access the underlying NetworkX graph."""
        return self._graph

    # ── Write operations ──────────────────────────────────────────────

    def add_node(self, node: CognitionNode) -> None:
        """Add a cognition node to the graph and journal.

        Args:
            node: The cognition node to add
        """
        self._graph.add_node(
            node.id,
            type=node.type.value,
            summary=node.summary,
            detail=node.detail,
            context=node.context,
            references=node.references,
            severity=node.severity,
            timestamp=node.timestamp,
            author=node.author,
        )
        self._append_journal("add_node", node.model_dump(mode="json"))

    def add_edge(self, edge: CognitionEdge) -> bool:
        """Add an edge between two existing nodes.

        Args:
            edge: The cognition edge to add

        Returns:
            True if both nodes exist and the edge was added
        """
        if edge.from_id not in self._graph or edge.to_id not in self._graph:
            logger.warning(
                f"Cannot add edge: node(s) missing "
                f"(from={edge.from_id}, to={edge.to_id})"
            )
            return False

        self._graph.add_edge(
            edge.from_id,
            edge.to_id,
            type=edge.edge_type.value,
            timestamp=edge.timestamp,
        )
        self._append_journal("add_edge", edge.model_dump(mode="json"))
        return True

    def update_node(self, node_id: str, **kwargs: Any) -> bool:
        """Update fields on an existing node.

        Args:
            node_id: ID of the node to update
            **kwargs: Fields to update (summary, detail, context, etc.)

        Returns:
            True if the node exists and was updated
        """
        if node_id not in self._graph:
            return False

        for key, value in kwargs.items():
            self._graph.nodes[node_id][key] = value

        data = {"id": node_id, **kwargs}
        self._append_journal("update_node", data)
        return True

    def remove_node(self, node_id: str) -> bool:
        """Remove a node and all its edges from the graph.

        Args:
            node_id: ID of the node to remove

        Returns:
            True if the node existed and was removed
        """
        if node_id not in self._graph:
            return False

        self._graph.remove_node(node_id)
        self._append_journal("remove_node", {"id": node_id})
        return True

    def redirect_edges(self, old_node_id: str, new_node_id: str) -> int:
        """Redirect all edges from/to old_node_id to point to/from new_node_id.

        Args:
            old_node_id: The node being replaced
            new_node_id: The node that takes over

        Returns:
            Number of edges redirected
        """
        if old_node_id not in self._graph or new_node_id not in self._graph:
            return 0

        redirected = 0

        # Redirect outgoing edges
        for _, target_id, edge_data in list(self._graph.out_edges(old_node_id, data=True)):
            if target_id != new_node_id:  # Avoid self-loops
                self._graph.add_edge(new_node_id, target_id, **edge_data)
                self._append_journal("add_edge", {
                    "from_id": new_node_id, "to_id": target_id,
                    "edge_type": edge_data.get("type", ""),
                    "timestamp": edge_data.get("timestamp", ""),
                })
                redirected += 1

        # Redirect incoming edges
        for source_id, _, edge_data in list(self._graph.in_edges(old_node_id, data=True)):
            if source_id != new_node_id:  # Avoid self-loops
                self._graph.add_edge(source_id, new_node_id, **edge_data)
                self._append_journal("add_edge", {
                    "from_id": source_id, "to_id": new_node_id,
                    "edge_type": edge_data.get("type", ""),
                    "timestamp": edge_data.get("timestamp", ""),
                })
                redirected += 1

        return redirected

    # ── Read operations ───────────────────────────────────────────────

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Get a node by its ID.

        Args:
            node_id: ID of the node

        Returns:
            Node data dict or None if not found
        """
        if node_id in self._graph:
            return dict(self._graph.nodes[node_id])
        return None

    def has_node(self, node_id: str) -> bool:
        """Check if a node exists."""
        return node_id in self._graph

    def get_all_nodes(self) -> list[dict[str, Any]]:
        """Get all nodes in the graph.

        Returns:
            List of node data dicts with 'id' included
        """
        return [
            {"id": node_id, **data}
            for node_id, data in self._graph.nodes(data=True)
        ]

    def get_nodes_by_type(self, node_type: CognitionNodeType) -> list[dict[str, Any]]:
        """Get all nodes of a specific type.

        Args:
            node_type: Type to filter by

        Returns:
            List of matching node data dicts
        """
        return [
            {"id": node_id, **data}
            for node_id, data in self._graph.nodes(data=True)
            if data.get("type") == node_type.value
        ]

    def get_recent_nodes(
        self,
        limit: int = 10,
        node_type: CognitionNodeType | None = None,
    ) -> list[dict[str, Any]]:
        """Get the most recent nodes, optionally filtered by type.

        Args:
            limit: Maximum number of nodes to return
            node_type: Optional type filter

        Returns:
            List of node data dicts sorted by timestamp descending
        """
        nodes = []
        for node_id, data in self._graph.nodes(data=True):
            if node_type and data.get("type") != node_type.value:
                continue
            nodes.append({"id": node_id, **data})

        nodes.sort(key=lambda n: n.get("timestamp", ""), reverse=True)
        return nodes[:limit]

    def get_successors(
        self,
        node_id: str,
        edge_type: CognitionEdgeType | None = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Get all nodes that this node points to.

        Args:
            node_id: Source node ID
            edge_type: Optional edge type filter

        Returns:
            List of (target_id, edge_data) tuples
        """
        if node_id not in self._graph:
            return []

        result = []
        for _, target_id, edge_data in self._graph.out_edges(node_id, data=True):
            if edge_type is None or edge_data.get("type") == edge_type.value:
                result.append((target_id, edge_data))
        return result

    def get_predecessors(
        self,
        node_id: str,
        edge_type: CognitionEdgeType | None = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Get all nodes that point to this node.

        Args:
            node_id: Target node ID
            edge_type: Optional edge type filter

        Returns:
            List of (source_id, edge_data) tuples
        """
        if node_id not in self._graph:
            return []

        result = []
        for source_id, _, edge_data in self._graph.in_edges(node_id, data=True):
            if edge_type is None or edge_data.get("type") == edge_type.value:
                result.append((source_id, edge_data))
        return result

    def get_statistics(self) -> dict[str, int]:
        """Get graph statistics.

        Returns:
            Dictionary with node/edge counts by type
        """
        stats: dict[str, int] = {
            "nodes": self._graph.number_of_nodes(),
            "edges": self._graph.number_of_edges(),
        }
        for node_type in CognitionNodeType:
            stats[node_type.value] = 0

        for _, data in self._graph.nodes(data=True):
            t = data.get("type", "")
            if t in stats:
                stats[t] += 1

        return stats

    # ── Internal ──────────────────────────────────────────────────────

    def _append_journal(self, action: str, data: dict[str, Any]) -> None:
        """Append a single JSON line to the journal file.

        Args:
            action: The action type (add_node, add_edge, update_node)
            data: The action payload
        """
        line = json.dumps({"action": action, "data": data}, ensure_ascii=False)
        with open(self._journal_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _hydrate(self) -> None:
        """Replay the JSONL journal to rebuild the in-memory graph."""
        count = 0
        with open(self._journal_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    self._replay_entry(entry)
                    count += 1
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.warning(f"Skipping malformed journal line {line_num}: {e}")

        logger.info(f"Cognition graph hydrated: {count} entries, "
                     f"{self._graph.number_of_nodes()} nodes, "
                     f"{self._graph.number_of_edges()} edges")

    def _replay_entry(self, entry: dict[str, Any]) -> None:
        """Replay a single journal entry into the graph (no journal write).

        Args:
            entry: Journal entry with 'action' and 'data' keys
        """
        action = entry["action"]
        data = entry["data"]

        if action == "add_node":
            self._graph.add_node(
                data["id"],
                type=data["type"],
                summary=data["summary"],
                detail=data["detail"],
                context=data.get("context", []),
                references=data.get("references", []),
                severity=data.get("severity"),
                timestamp=data["timestamp"],
                author=data["author"],
            )
        elif action == "add_edge":
            from_id = data["from_id"]
            to_id = data["to_id"]
            if from_id in self._graph and to_id in self._graph:
                self._graph.add_edge(
                    from_id,
                    to_id,
                    type=data["edge_type"],
                    timestamp=data.get("timestamp", ""),
                )
        elif action == "remove_node":
            node_id = data["id"]
            if node_id in self._graph:
                self._graph.remove_node(node_id)
        elif action == "update_node":
            node_id = data.pop("id")
            if node_id in self._graph:
                for key, value in data.items():
                    self._graph.nodes[node_id][key] = value
