"""Tests for the cognition history graph module."""

import json
import tempfile
from pathlib import Path

import pytest

from vibe_ragnar.cognition import (
    CognitionEdge,
    CognitionEdgeType,
    CognitionNode,
    CognitionNodeType,
    CognitionStorage,
    generate_node_id,
    get_history_for_context,
    get_incident_resolution,
    get_reasoning_chain,
    get_superseded_chain,
)


class TestModels:
    """Tests for cognition data models."""

    def test_node_types(self):
        """All 8 node types exist."""
        assert len(CognitionNodeType) == 8
        assert CognitionNodeType.DECISION.value == "decision"
        assert CognitionNodeType.FAIL.value == "fail"
        assert CognitionNodeType.DISCOVERY.value == "discovery"
        assert CognitionNodeType.ASSUMPTION.value == "assumption"
        assert CognitionNodeType.CONSTRAINT.value == "constraint"
        assert CognitionNodeType.INCIDENT.value == "incident"
        assert CognitionNodeType.PATTERN.value == "pattern"
        assert CognitionNodeType.EPISODE.value == "episode"

    def test_edge_types(self):
        """All 7 edge types exist."""
        assert len(CognitionEdgeType) == 7
        assert CognitionEdgeType.PART_OF.value == "part_of"
        assert CognitionEdgeType.DUPLICATE_OF.value == "duplicate_of"
        assert CognitionEdgeType.LED_TO.value == "led_to"
        assert CognitionEdgeType.SUPERSEDES.value == "supersedes"
        assert CognitionEdgeType.CONTRADICTS.value == "contradicts"
        assert CognitionEdgeType.RELATES_TO.value == "relates_to"
        assert CognitionEdgeType.RESOLVED_BY.value == "resolved_by"

    def test_generate_node_id_deterministic(self):
        """Same inputs produce same ID."""
        id1 = generate_node_id("decision", "Use Redis", "2026-03-15T10:00:00Z")
        id2 = generate_node_id("decision", "Use Redis", "2026-03-15T10:00:00Z")
        assert id1 == id2
        assert len(id1) == 12

    def test_generate_node_id_unique(self):
        """Different inputs produce different IDs."""
        id1 = generate_node_id("decision", "Use Redis", "2026-03-15T10:00:00Z")
        id2 = generate_node_id("decision", "Use Redis", "2026-03-15T10:00:01Z")
        id3 = generate_node_id("fail", "Use Redis", "2026-03-15T10:00:00Z")
        assert id1 != id2  # different timestamp
        assert id1 != id3  # different type

    def test_cognition_node_model(self):
        """CognitionNode validates correctly."""
        node = CognitionNode(
            id="abc123def456",
            type=CognitionNodeType.DECISION,
            summary="Use Redis for caching",
            detail="Chose over Memcached for pub/sub support",
            context=["src/cache/", "caching"],
            references=["pr:97", "issue:LL-298"],
            severity="high",
            timestamp="2026-03-15T10:00:00Z",
            author="alice",
        )
        assert node.type == CognitionNodeType.DECISION
        assert node.severity == "high"
        assert len(node.references) == 2

    def test_cognition_node_defaults(self):
        """CognitionNode optional fields have correct defaults."""
        node = CognitionNode(
            id="abc123def456",
            type=CognitionNodeType.DISCOVERY,
            summary="Found a bug",
            detail="Details here",
            timestamp="2026-03-15T10:00:00Z",
            author="bob",
        )
        assert node.context == []
        assert node.references == []
        assert node.severity is None


class TestCognitionStorage:
    """Tests for CognitionStorage class."""

    @pytest.fixture
    def storage(self, tmp_path):
        """Create a CognitionStorage with a temporary directory."""
        return CognitionStorage(tmp_path / ".cognition")

    def _make_node(self, node_id="test123", node_type=CognitionNodeType.DECISION,
                   summary="Test decision", detail="Test detail",
                   context=None, timestamp="2026-03-15T10:00:00Z"):
        return CognitionNode(
            id=node_id,
            type=node_type,
            summary=summary,
            detail=detail,
            context=context or ["test"],
            timestamp=timestamp,
            author="tester",
        )

    def test_add_and_get_node(self, storage):
        """Test adding and retrieving a node."""
        node = self._make_node()
        storage.add_node(node)

        retrieved = storage.get_node("test123")
        assert retrieved is not None
        assert retrieved["summary"] == "Test decision"
        assert retrieved["type"] == "decision"

    def test_has_node(self, storage):
        """Test node existence check."""
        assert not storage.has_node("test123")
        storage.add_node(self._make_node())
        assert storage.has_node("test123")

    def test_add_edge(self, storage):
        """Test adding edges between nodes."""
        storage.add_node(self._make_node("node1"))
        storage.add_node(self._make_node("node2"))

        edge = CognitionEdge(
            from_id="node1",
            to_id="node2",
            edge_type=CognitionEdgeType.LED_TO,
            timestamp="2026-03-15T10:01:00Z",
        )
        assert storage.add_edge(edge)

        successors = storage.get_successors("node1", CognitionEdgeType.LED_TO)
        assert len(successors) == 1
        assert successors[0][0] == "node2"

    def test_add_edge_missing_node(self, storage):
        """Test that adding an edge with missing nodes returns False."""
        storage.add_node(self._make_node("node1"))
        edge = CognitionEdge(
            from_id="node1",
            to_id="nonexistent",
            edge_type=CognitionEdgeType.LED_TO,
            timestamp="2026-03-15T10:01:00Z",
        )
        assert not storage.add_edge(edge)

    def test_update_node(self, storage):
        """Test updating node fields."""
        storage.add_node(self._make_node())
        assert storage.update_node("test123", detail="Updated detail")

        retrieved = storage.get_node("test123")
        assert retrieved["detail"] == "Updated detail"

    def test_update_nonexistent_node(self, storage):
        """Test that updating a missing node returns False."""
        assert not storage.update_node("nonexistent", detail="nope")

    def test_remove_node(self, storage):
        """Test removing a node and its edges."""
        storage.add_node(self._make_node("n1"))
        storage.add_node(self._make_node("n2"))
        storage.add_edge(CognitionEdge(
            from_id="n1", to_id="n2",
            edge_type=CognitionEdgeType.LED_TO,
            timestamp="2026-03-15T10:00:00Z",
        ))

        assert storage.remove_node("n1")
        assert not storage.has_node("n1")
        assert storage.get_successors("n1") == []
        assert storage.get_predecessors("n2") == []  # Edge removed with node

    def test_remove_nonexistent_node(self, storage):
        """Test that removing a missing node returns False."""
        assert not storage.remove_node("nonexistent")

    def test_redirect_edges(self, storage):
        """Test redirecting edges from one node to another."""
        storage.add_node(self._make_node("old"))
        storage.add_node(self._make_node("new"))
        storage.add_node(self._make_node("other"))

        # old -> other (outgoing)
        storage.add_edge(CognitionEdge(
            from_id="old", to_id="other",
            edge_type=CognitionEdgeType.LED_TO,
            timestamp="2026-03-15T10:00:00Z",
        ))
        # other -> old (incoming)
        storage.add_edge(CognitionEdge(
            from_id="other", to_id="old",
            edge_type=CognitionEdgeType.RESOLVED_BY,
            timestamp="2026-03-15T10:01:00Z",
        ))

        redirected = storage.redirect_edges("old", "new")
        assert redirected == 2

        # new -> other should exist
        successors = storage.get_successors("new", CognitionEdgeType.LED_TO)
        assert len(successors) == 1
        assert successors[0][0] == "other"

        # other -> new should exist
        preds = storage.get_predecessors("new", CognitionEdgeType.RESOLVED_BY)
        assert len(preds) == 1
        assert preds[0][0] == "other"

    def test_get_all_nodes(self, storage):
        """Test getting all nodes."""
        storage.add_node(self._make_node("n1"))
        storage.add_node(self._make_node("n2"))
        storage.add_node(self._make_node("n3"))

        nodes = storage.get_all_nodes()
        assert len(nodes) == 3

    def test_get_nodes_by_type(self, storage):
        """Test filtering nodes by type."""
        storage.add_node(self._make_node("d1", CognitionNodeType.DECISION))
        storage.add_node(self._make_node("f1", CognitionNodeType.FAIL))
        storage.add_node(self._make_node("d2", CognitionNodeType.DECISION))

        decisions = storage.get_nodes_by_type(CognitionNodeType.DECISION)
        assert len(decisions) == 2

        fails = storage.get_nodes_by_type(CognitionNodeType.FAIL)
        assert len(fails) == 1

    def test_get_recent_nodes(self, storage):
        """Test getting recent nodes sorted by timestamp."""
        storage.add_node(self._make_node("n1", timestamp="2026-03-01T00:00:00Z"))
        storage.add_node(self._make_node("n2", timestamp="2026-03-03T00:00:00Z"))
        storage.add_node(self._make_node("n3", timestamp="2026-03-02T00:00:00Z"))

        recent = storage.get_recent_nodes(limit=2)
        assert len(recent) == 2
        assert recent[0]["id"] == "n2"  # newest first
        assert recent[1]["id"] == "n3"

    def test_get_predecessors(self, storage):
        """Test getting predecessor nodes."""
        storage.add_node(self._make_node("a"))
        storage.add_node(self._make_node("b"))
        storage.add_edge(CognitionEdge(
            from_id="a", to_id="b",
            edge_type=CognitionEdgeType.RESOLVED_BY,
            timestamp="2026-03-15T10:00:00Z",
        ))

        preds = storage.get_predecessors("b", CognitionEdgeType.RESOLVED_BY)
        assert len(preds) == 1
        assert preds[0][0] == "a"

    def test_statistics(self, storage):
        """Test graph statistics."""
        storage.add_node(self._make_node("d1", CognitionNodeType.DECISION))
        storage.add_node(self._make_node("i1", CognitionNodeType.INCIDENT))
        storage.add_edge(CognitionEdge(
            from_id="d1", to_id="i1",
            edge_type=CognitionEdgeType.LED_TO,
            timestamp="2026-03-15T10:00:00Z",
        ))

        stats = storage.get_statistics()
        assert stats["nodes"] == 2
        assert stats["edges"] == 1
        assert stats["decision"] == 1
        assert stats["incident"] == 1


class TestJSONLPersistence:
    """Tests for JSONL round-trip persistence."""

    def test_hydration_round_trip(self, tmp_path):
        """Test that nodes and edges survive a restart (JSONL hydration)."""
        cog_dir = tmp_path / ".cognition"

        # First session: create data
        storage1 = CognitionStorage(cog_dir)
        storage1.add_node(CognitionNode(
            id="dec1", type=CognitionNodeType.DECISION,
            summary="Use Redis", detail="For caching",
            context=["cache"], timestamp="2026-03-15T10:00:00Z", author="alice",
        ))
        storage1.add_node(CognitionNode(
            id="fail1", type=CognitionNodeType.FAIL,
            summary="Memcached failed", detail="No pub/sub",
            context=["cache"], timestamp="2026-03-15T09:00:00Z", author="alice",
        ))
        storage1.add_edge(CognitionEdge(
            from_id="fail1", to_id="dec1",
            edge_type=CognitionEdgeType.LED_TO,
            timestamp="2026-03-15T10:01:00Z",
        ))
        storage1.update_node("dec1", detail="For caching with pub/sub support")

        # Second session: hydrate from JSONL
        storage2 = CognitionStorage(cog_dir)

        # Verify nodes
        dec = storage2.get_node("dec1")
        assert dec is not None
        assert dec["summary"] == "Use Redis"
        assert dec["detail"] == "For caching with pub/sub support"  # updated

        fail = storage2.get_node("fail1")
        assert fail is not None

        # Verify edge
        successors = storage2.get_successors("fail1", CognitionEdgeType.LED_TO)
        assert len(successors) == 1
        assert successors[0][0] == "dec1"

    def test_journal_format(self, tmp_path):
        """Test that the JSONL file has the expected format."""
        cog_dir = tmp_path / ".cognition"
        storage = CognitionStorage(cog_dir)

        storage.add_node(CognitionNode(
            id="n1", type=CognitionNodeType.INCIDENT,
            summary="Data wipe", detail="Users lost data",
            context=["migration"], references=["issue:LL-298"],
            severity="critical",
            timestamp="2026-03-07T23:07:14Z", author="colton",
        ))

        journal = (cog_dir / "journal.jsonl").read_text(encoding="utf-8")
        lines = [l for l in journal.strip().split("\n") if l]
        assert len(lines) == 1

        entry = json.loads(lines[0])
        assert entry["action"] == "add_node"
        assert entry["data"]["type"] == "incident"
        assert entry["data"]["severity"] == "critical"
        assert "issue:LL-298" in entry["data"]["references"]

    def test_malformed_journal_lines_skipped(self, tmp_path):
        """Test that malformed JSONL lines are skipped gracefully."""
        cog_dir = tmp_path / ".cognition"
        cog_dir.mkdir(parents=True)

        journal = cog_dir / "journal.jsonl"
        journal.write_text(
            '{"action":"add_node","data":{"id":"n1","type":"decision","summary":"Good","detail":"OK","context":[],"references":[],"severity":null,"timestamp":"2026-03-15T10:00:00Z","author":"test"}}\n'
            'THIS IS NOT JSON\n'
            '{"action":"add_node","data":{"id":"n2","type":"fail","summary":"Also good","detail":"OK","context":[],"references":[],"severity":null,"timestamp":"2026-03-15T11:00:00Z","author":"test"}}\n',
            encoding="utf-8",
        )

        storage = CognitionStorage(cog_dir)
        assert storage.has_node("n1")
        assert storage.has_node("n2")


class TestQueries:
    """Tests for cognition query functions."""

    @pytest.fixture
    def storage_with_chain(self, tmp_path):
        """Create a storage with a reasoning chain for testing."""
        storage = CognitionStorage(tmp_path / ".cognition")

        # incident → discovery → decision (resolved_by)
        storage.add_node(CognitionNode(
            id="inc1", type=CognitionNodeType.INCIDENT,
            summary="Data wipe", detail="Users lost data",
            context=["migration"], severity="critical",
            timestamp="2026-03-07T23:00:00Z", author="colton",
        ))
        storage.add_node(CognitionNode(
            id="disc1", type=CognitionNodeType.DISCOVERY,
            summary="Double-filter bug", detail="Redundant language filter",
            context=["flashcard_local_datasource.dart"],
            timestamp="2026-03-08T09:00:00Z", author="colton",
        ))
        storage.add_node(CognitionNode(
            id="dec1", type=CognitionNodeType.DECISION,
            summary="Remove redundant filter", detail="From all 5 query methods",
            context=["flashcard_local_datasource.dart"],
            timestamp="2026-03-08T09:30:00Z", author="colton",
        ))

        # Chain: incident --led_to--> discovery --led_to--> decision
        storage.add_edge(CognitionEdge(
            from_id="inc1", to_id="disc1",
            edge_type=CognitionEdgeType.LED_TO,
            timestamp="2026-03-08T09:01:00Z",
        ))
        storage.add_edge(CognitionEdge(
            from_id="disc1", to_id="dec1",
            edge_type=CognitionEdgeType.LED_TO,
            timestamp="2026-03-08T09:31:00Z",
        ))

        # Also: incident --resolved_by--> decision
        storage.add_edge(CognitionEdge(
            from_id="inc1", to_id="dec1",
            edge_type=CognitionEdgeType.RESOLVED_BY,
            timestamp="2026-03-08T09:32:00Z",
        ))

        return storage

    def test_get_reasoning_chain_outgoing(self, storage_with_chain):
        """Test outgoing reasoning chain traversal."""
        chain = get_reasoning_chain(storage_with_chain, "inc1", direction="outgoing")

        assert chain["id"] == "inc1"
        assert chain["type"] == "incident"
        assert len(chain["chain"]) == 1  # LED_TO to disc1

        disc = chain["chain"][0]
        assert disc["id"] == "disc1"
        assert len(disc["chain"]) == 1  # LED_TO to dec1

        dec = disc["chain"][0]
        assert dec["id"] == "dec1"

    def test_get_reasoning_chain_incoming(self, storage_with_chain):
        """Test incoming reasoning chain traversal."""
        chain = get_reasoning_chain(storage_with_chain, "dec1", direction="incoming")

        assert chain["id"] == "dec1"
        assert len(chain["chain"]) == 1  # LED_TO from disc1

    def test_get_reasoning_chain_max_depth(self, storage_with_chain):
        """Test that max_depth limits traversal."""
        chain = get_reasoning_chain(storage_with_chain, "inc1", max_depth=1)

        assert chain["id"] == "inc1"
        disc = chain["chain"][0]
        assert disc["id"] == "disc1"
        # At depth 2 (> max_depth 1), should be truncated
        assert disc["chain"][0]["truncated"] is True

    def test_get_superseded_chain(self, tmp_path):
        """Test following SUPERSEDES edges."""
        storage = CognitionStorage(tmp_path / ".cognition")

        storage.add_node(CognitionNode(
            id="v3", type=CognitionNodeType.DECISION,
            summary="Use Redis v3", detail="Latest",
            timestamp="2026-03-15T12:00:00Z", author="alice",
        ))
        storage.add_node(CognitionNode(
            id="v2", type=CognitionNodeType.DECISION,
            summary="Use Redis v2", detail="Middle",
            timestamp="2026-03-14T12:00:00Z", author="alice",
        ))
        storage.add_node(CognitionNode(
            id="v1", type=CognitionNodeType.DECISION,
            summary="Use Redis v1", detail="Original",
            timestamp="2026-03-13T12:00:00Z", author="alice",
        ))

        storage.add_edge(CognitionEdge(
            from_id="v3", to_id="v2",
            edge_type=CognitionEdgeType.SUPERSEDES,
            timestamp="2026-03-15T12:00:00Z",
        ))
        storage.add_edge(CognitionEdge(
            from_id="v2", to_id="v1",
            edge_type=CognitionEdgeType.SUPERSEDES,
            timestamp="2026-03-14T12:00:00Z",
        ))

        chain = get_superseded_chain(storage, "v3")
        assert len(chain) == 3
        assert chain[0]["id"] == "v3"
        assert chain[1]["id"] == "v2"
        assert chain[2]["id"] == "v1"

    def test_get_history_for_context(self, storage_with_chain):
        """Test filtering by context term."""
        results = get_history_for_context(
            storage_with_chain, "flashcard_local_datasource"
        )
        assert len(results) == 2  # disc1 and dec1

    def test_get_history_for_context_with_type_filter(self, storage_with_chain):
        """Test filtering by context term and type."""
        results = get_history_for_context(
            storage_with_chain, "flashcard_local_datasource",
            node_type=CognitionNodeType.DISCOVERY,
        )
        assert len(results) == 1
        assert results[0]["id"] == "disc1"

    def test_get_incident_resolution(self, storage_with_chain):
        """Test getting incident resolution details."""
        result = get_incident_resolution(storage_with_chain, "inc1")

        assert result["id"] == "inc1"
        assert result["type"] == "incident"
        assert len(result["resolutions"]) == 1
        assert result["resolutions"][0]["id"] == "dec1"

    def test_get_incident_resolution_not_found(self, storage_with_chain):
        """Test incident resolution for nonexistent node."""
        result = get_incident_resolution(storage_with_chain, "nonexistent")
        assert "error" in result
