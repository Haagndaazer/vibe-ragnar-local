"""Tests for the cognition graph curator."""

import json
from unittest.mock import MagicMock, patch

import pytest

from vibe_ragnar.cognition import (
    CognitionEdgeType,
    CognitionNode,
    CognitionNodeType,
    CognitionStorage,
)
from vibe_ragnar.cognition.curator import CognitionCurator


@pytest.fixture
def storage(tmp_path):
    """Create a CognitionStorage with a temporary directory."""
    return CognitionStorage(tmp_path / ".cognition")


@pytest.fixture
def mock_embedding_storage():
    """Create a mock ChromaDBStorage."""
    mock = MagicMock()
    mock.vector_search.return_value = []
    return mock


@pytest.fixture
def mock_generator():
    """Create a mock EmbeddingGenerator."""
    mock = MagicMock()
    mock.generate_query_embedding.return_value = [0.1] * 768
    return mock


def _make_node(node_id="new1", node_type=CognitionNodeType.DECISION,
               summary="Test decision", detail="Test detail"):
    return CognitionNode(
        id=node_id,
        type=node_type,
        summary=summary,
        detail=detail,
        context=["test"],
        timestamp="2026-03-15T10:00:00Z",
        author="tester",
    )


def _make_curator(storage, mock_embedding_storage, mock_generator):
    return CognitionCurator(
        storage=storage,
        embedding_storage=mock_embedding_storage,
        embedding_generator=mock_generator,
        ollama_base_url="http://localhost:11434",
        model="qwen3:8b",
        max_candidates=8,
    )


def _mock_ollama_response(edges_json):
    """Create a mock httpx response with the given edges."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "message": {"content": json.dumps({"edges": edges_json})}
    }
    return mock_response


class TestCuratorHappyPath:
    """Tests for successful curator operations."""

    def test_creates_edges_from_llm_suggestions(
        self, storage, mock_embedding_storage, mock_generator
    ):
        """Curator creates edges based on LLM suggestions."""
        existing = _make_node("existing1", CognitionNodeType.FAIL,
                              "Previous failure", "Tried X and it failed")
        storage.add_node(existing)

        new_node = _make_node("new1", CognitionNodeType.DECISION,
                              "New approach", "Decided to try Y instead")
        storage.add_node(new_node)

        mock_embedding_storage.vector_search.return_value = [
            {"_id": "existing1", "score": 0.8, "entity_type": "fail",
             "summary": "Previous failure"},
        ]

        curator = _make_curator(storage, mock_embedding_storage, mock_generator)

        with patch("httpx.post", return_value=_mock_ollama_response([{
            "candidate_id": "existing1",
            "edge_type": "led_to",
            "direction": "to_new",
            "reason": "The failure led to this decision",
        }])):
            edges = curator.curate(new_node)

        assert len(edges) == 1
        assert edges[0].from_id == "existing1"
        assert edges[0].to_id == "new1"
        assert edges[0].edge_type == CognitionEdgeType.LED_TO

    def test_creates_multiple_edges(
        self, storage, mock_embedding_storage, mock_generator
    ):
        """Curator can create multiple edges from one curation."""
        node_a = _make_node("a", CognitionNodeType.INCIDENT, "Incident A", "Details")
        node_b = _make_node("b", CognitionNodeType.DISCOVERY, "Discovery B", "Details")
        storage.add_node(node_a)
        storage.add_node(node_b)

        new_node = _make_node("new1", CognitionNodeType.DECISION, "Fix", "Fixed it")
        storage.add_node(new_node)

        mock_embedding_storage.vector_search.return_value = [
            {"_id": "a", "score": 0.9, "entity_type": "incident", "summary": "Incident A"},
            {"_id": "b", "score": 0.7, "entity_type": "discovery", "summary": "Discovery B"},
        ]

        curator = _make_curator(storage, mock_embedding_storage, mock_generator)

        with patch("httpx.post", return_value=_mock_ollama_response([
            {"candidate_id": "a", "edge_type": "resolved_by",
             "direction": "from_new", "reason": "Fix resolves incident"},
            {"candidate_id": "b", "edge_type": "led_to",
             "direction": "to_new", "reason": "Discovery led to fix"},
        ])):
            edges = curator.curate(new_node)

        assert len(edges) == 2

    def test_direction_from_new(
        self, storage, mock_embedding_storage, mock_generator
    ):
        """direction=from_new creates edge new_node -> candidate."""
        existing = _make_node("existing1")
        storage.add_node(existing)
        new_node = _make_node("new1")
        storage.add_node(new_node)

        mock_embedding_storage.vector_search.return_value = [
            {"_id": "existing1", "score": 0.8, "entity_type": "decision",
             "summary": "Existing"},
        ]

        curator = _make_curator(storage, mock_embedding_storage, mock_generator)

        with patch("httpx.post", return_value=_mock_ollama_response([{
            "candidate_id": "existing1",
            "edge_type": "supersedes",
            "direction": "from_new",
            "reason": "New supersedes old",
        }])):
            edges = curator.curate(new_node)

        assert len(edges) == 1
        assert edges[0].from_id == "new1"
        assert edges[0].to_id == "existing1"


class TestCuratorNoCandidates:
    """Tests when there are no candidates to evaluate."""

    def test_empty_graph_returns_no_edges(
        self, storage, mock_embedding_storage, mock_generator
    ):
        """No candidates means no Ollama call and no edges."""
        new_node = _make_node()
        storage.add_node(new_node)

        mock_embedding_storage.vector_search.return_value = []

        curator = _make_curator(storage, mock_embedding_storage, mock_generator)

        with patch("httpx.post") as mock_post:
            edges = curator.curate(new_node)
            mock_post.assert_not_called()

        assert edges == []

    def test_self_match_filtered_out(
        self, storage, mock_embedding_storage, mock_generator
    ):
        """The new node's own ID is excluded from candidates."""
        new_node = _make_node("new1")
        storage.add_node(new_node)

        mock_embedding_storage.vector_search.return_value = [
            {"_id": "new1", "score": 1.0, "entity_type": "decision", "summary": "Test"},
        ]

        curator = _make_curator(storage, mock_embedding_storage, mock_generator)

        with patch("httpx.post") as mock_post:
            edges = curator.curate(new_node)
            mock_post.assert_not_called()

        assert edges == []

    def test_low_similarity_filtered_out(
        self, storage, mock_embedding_storage, mock_generator
    ):
        """Candidates below the similarity threshold are excluded."""
        existing = _make_node("existing1")
        storage.add_node(existing)
        new_node = _make_node("new1")
        storage.add_node(new_node)

        mock_embedding_storage.vector_search.return_value = [
            {"_id": "existing1", "score": 0.1, "entity_type": "decision",
             "summary": "Low match"},
        ]

        curator = _make_curator(storage, mock_embedding_storage, mock_generator)

        with patch("httpx.post") as mock_post:
            edges = curator.curate(new_node)
            mock_post.assert_not_called()

        assert edges == []


class TestCuratorErrorHandling:
    """Tests for error conditions."""

    def test_ollama_connection_error(
        self, storage, mock_embedding_storage, mock_generator
    ):
        """Ollama being down returns empty edges, no crash."""
        existing = _make_node("existing1")
        storage.add_node(existing)
        new_node = _make_node("new1")
        storage.add_node(new_node)

        mock_embedding_storage.vector_search.return_value = [
            {"_id": "existing1", "score": 0.8, "entity_type": "decision",
             "summary": "Existing"},
        ]

        curator = _make_curator(storage, mock_embedding_storage, mock_generator)

        with patch("httpx.post", side_effect=ConnectionError("Ollama not running")):
            edges = curator.curate(new_node)

        assert edges == []

    def test_malformed_json_response(
        self, storage, mock_embedding_storage, mock_generator
    ):
        """Malformed JSON from Ollama returns empty edges."""
        existing = _make_node("existing1")
        storage.add_node(existing)
        new_node = _make_node("new1")
        storage.add_node(new_node)

        mock_embedding_storage.vector_search.return_value = [
            {"_id": "existing1", "score": 0.8, "entity_type": "decision",
             "summary": "Existing"},
        ]

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "message": {"content": "this is not json"}
        }

        curator = _make_curator(storage, mock_embedding_storage, mock_generator)

        with patch("httpx.post", return_value=mock_response):
            edges = curator.curate(new_node)

        assert edges == []

    def test_invalid_edge_type_skipped(
        self, storage, mock_embedding_storage, mock_generator
    ):
        """Suggestions with invalid edge types are skipped."""
        existing = _make_node("existing1")
        storage.add_node(existing)
        new_node = _make_node("new1")
        storage.add_node(new_node)

        mock_embedding_storage.vector_search.return_value = [
            {"_id": "existing1", "score": 0.8, "entity_type": "decision",
             "summary": "Existing"},
        ]

        curator = _make_curator(storage, mock_embedding_storage, mock_generator)

        with patch("httpx.post", return_value=_mock_ollama_response([{
            "candidate_id": "existing1",
            "edge_type": "invalid_type",
            "direction": "from_new",
            "reason": "bad",
        }])):
            edges = curator.curate(new_node)

        assert edges == []

    def test_nonexistent_candidate_skipped(
        self, storage, mock_embedding_storage, mock_generator
    ):
        """Suggestions referencing nonexistent nodes are skipped."""
        new_node = _make_node("new1")
        storage.add_node(new_node)

        mock_embedding_storage.vector_search.return_value = [
            {"_id": "ghost", "score": 0.8, "entity_type": "decision",
             "summary": "Ghost node"},
        ]

        curator = _make_curator(storage, mock_embedding_storage, mock_generator)

        # No candidates after enrichment (ghost not in storage)
        edges = curator.curate(new_node)
        assert edges == []

    def test_llm_suggests_zero_edges(
        self, storage, mock_embedding_storage, mock_generator
    ):
        """LLM returning empty edges list is handled correctly."""
        existing = _make_node("existing1")
        storage.add_node(existing)
        new_node = _make_node("new1")
        storage.add_node(new_node)

        mock_embedding_storage.vector_search.return_value = [
            {"_id": "existing1", "score": 0.8, "entity_type": "decision",
             "summary": "Existing"},
        ]

        curator = _make_curator(storage, mock_embedding_storage, mock_generator)

        with patch("httpx.post", return_value=_mock_ollama_response([])):
            edges = curator.curate(new_node)

        assert edges == []


class TestCuratorPrompt:
    """Tests for prompt construction."""

    def test_prompt_contains_node_details(
        self, storage, mock_embedding_storage, mock_generator
    ):
        """Prompt includes the new node's type, summary, detail, and context."""
        existing = _make_node("existing1")
        storage.add_node(existing)
        new_node = _make_node("new1", CognitionNodeType.INCIDENT,
                              "Data loss", "Users lost flashcards")
        new_node.context = ["migration", "hive"]
        new_node.severity = "critical"
        storage.add_node(new_node)

        mock_embedding_storage.vector_search.return_value = [
            {"_id": "existing1", "score": 0.8, "entity_type": "decision",
             "summary": "Test decision"},
        ]

        curator = _make_curator(storage, mock_embedding_storage, mock_generator)

        with patch("httpx.post", return_value=_mock_ollama_response([])) as mock_post:
            curator.curate(new_node)

            # Check the prompt sent to Ollama
            call_args = mock_post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            user_prompt = payload["messages"][1]["content"]

            assert "incident" in user_prompt
            assert "Data loss" in user_prompt
            assert "Users lost flashcards" in user_prompt
            assert "migration" in user_prompt
            assert "critical" in user_prompt
