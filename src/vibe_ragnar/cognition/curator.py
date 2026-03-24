"""Curator for the Cognition History Graph — uses a local LLM to create meaningful edges."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from ..embeddings import ChromaDBStorage, EmbeddingGenerator
from .models import CognitionEdge, CognitionEdgeType, CognitionNode
from .storage import CognitionStorage

logger = logging.getLogger(__name__)

CURATOR_SYSTEM_PROMPT = """\
You are a knowledge graph curator. You analyze a new node being added to a cognition \
history graph and determine if it has meaningful relationships to existing nodes.

The graph tracks development decisions, failures, discoveries, assumptions, constraints, \
incidents, and patterns.

Available edge types:
- led_to: A causal chain. X led to Y happening. Direction matters.
- supersedes: X replaces/updates a previous decision or assumption Y.
- contradicts: X contradicts or conflicts with Y. Only for genuine conflicts.
- relates_to: Same topic/system but no causal or hierarchical relationship. Use sparingly.
- resolved_by: X (incident/failure) was resolved/fixed by Y (decision/discovery).

Rules:
- Only suggest edges where there is a genuine, meaningful relationship.
- Do NOT create edges just because nodes share keywords. The relationship must be substantive.
- Prefer specific edge types (led_to, supersedes, contradicts, resolved_by) over relates_to.
- For supersedes: only use when the new node explicitly replaces an older decision/assumption.
- For contradicts: only use when there is a genuine logical conflict.
- It is perfectly fine to suggest zero edges if none are meaningful.
- Think about directionality carefully.

Respond with JSON only:
{
  "edges": [
    {
      "candidate_id": "<id of the existing node>",
      "edge_type": "<led_to|supersedes|contradicts|relates_to|resolved_by>",
      "direction": "<from_new|to_new>",
      "reason": "<brief explanation>"
    }
  ]
}

If no meaningful edges exist, respond with: {"edges": []}"""

VALID_EDGE_TYPES = {e.value for e in CognitionEdgeType}
VALID_DIRECTIONS = {"from_new", "to_new"}
MIN_SIMILARITY_SCORE = 0.3


class CognitionCurator:
    """Analyzes new cognition nodes and creates edges to existing related nodes via local LLM."""

    def __init__(
        self,
        storage: CognitionStorage,
        embedding_storage: ChromaDBStorage,
        embedding_generator: EmbeddingGenerator,
        ollama_base_url: str = "http://localhost:11434",
        model: str = "qwen3:8b",
        max_candidates: int = 8,
    ):
        self._storage = storage
        self._embedding_storage = embedding_storage
        self._embedding_generator = embedding_generator
        self._ollama_base_url = ollama_base_url
        self._model = model
        self._max_candidates = max_candidates

    def ensure_model(self) -> bool:
        """Ensure the curator model is available in Ollama, pulling if needed.

        Returns:
            True if the model is available (or was pulled), False on failure
        """
        try:
            import httpx

            # Check if model exists
            resp = httpx.get(
                f"{self._ollama_base_url}/api/tags", timeout=10.0
            )
            resp.raise_for_status()
            models = resp.json().get("models", [])
            model_names = [m.get("name", "") for m in models]

            # Check for exact match or match without tag
            base_name = self._model.split(":")[0]
            if any(self._model in n or base_name in n for n in model_names):
                logger.info(f"Curator model '{self._model}' is available")
                return True

            # Pull the model
            logger.info(f"Pulling curator model '{self._model}' (this may take a few minutes)...")
            pull_resp = httpx.post(
                f"{self._ollama_base_url}/api/pull",
                json={"name": self._model, "stream": False},
                timeout=600.0,  # 10 min timeout for large model downloads
            )
            pull_resp.raise_for_status()
            logger.info(f"Curator model '{self._model}' pulled successfully")
            return True
        except Exception as e:
            logger.warning(f"Failed to ensure curator model: {e}")
            return False

    def curate_uncurated_nodes(self) -> int:
        """Find nodes with no edges and curate them.

        Returns:
            Number of nodes that were curated
        """
        all_nodes = self._storage.get_all_nodes()
        if not all_nodes:
            return 0

        curated_count = 0
        for node_data in all_nodes:
            node_id = node_data["id"]
            # Skip if this node already has any edges (incoming or outgoing)
            if (self._storage.get_successors(node_id) or
                    self._storage.get_predecessors(node_id)):
                continue

            # Reconstruct CognitionNode from stored data
            try:
                node = CognitionNode(
                    id=node_id,
                    type=node_data["type"],
                    summary=node_data.get("summary", ""),
                    detail=node_data.get("detail", ""),
                    context=node_data.get("context", []),
                    references=node_data.get("references", []),
                    severity=node_data.get("severity"),
                    timestamp=node_data.get("timestamp", ""),
                    author=node_data.get("author", ""),
                )
                edges = self.curate(node)
                if edges:
                    curated_count += 1
            except Exception as e:
                logger.warning(f"Failed to curate node {node_id}: {e}")

        return curated_count

    def curate(self, node: CognitionNode) -> list[CognitionEdge]:
        """Analyze a new node and create edges to related existing nodes.

        Args:
            node: The newly added cognition node

        Returns:
            List of edges that were created
        """
        # Find candidate nodes via semantic search
        query_text = f"{node.type.value}: {node.summary}\n{node.detail}"
        query_embedding = self._embedding_generator.generate_query_embedding(query_text)

        results = self._embedding_storage.vector_search(
            query_embedding=query_embedding,
            limit=self._max_candidates + 1,  # +1 to account for self-match
        )

        # Filter out self and low-similarity candidates, enrich with full data
        candidates = []
        for r in results:
            cid = r.get("_id", "")
            score = r.get("score", 0)
            if cid == node.id or score < MIN_SIMILARITY_SCORE:
                continue

            full_data = self._storage.get_node(cid)
            if full_data:
                candidates.append({"id": cid, "score": score, **full_data})

            if len(candidates) >= self._max_candidates:
                break

        if not candidates:
            return []

        # Build prompt and call LLM
        prompt = self._build_prompt(node, candidates)
        suggestions = self._call_ollama(prompt)
        if not suggestions:
            return []

        # Validate and create edges
        return self._parse_and_create_edges(node.id, suggestions)

    def _build_prompt(self, new_node: CognitionNode, candidates: list[dict]) -> str:
        """Build the user prompt with the new node and candidate nodes."""
        parts = [
            "NEW NODE being added:",
            f"  ID: {new_node.id}",
            f"  Type: {new_node.type.value}",
            f"  Summary: {new_node.summary}",
            f"  Detail: {new_node.detail}",
        ]
        if new_node.context:
            parts.append(f"  Context: {', '.join(new_node.context)}")
        if new_node.severity:
            parts.append(f"  Severity: {new_node.severity}")

        parts.append("")
        parts.append("EXISTING NODES to evaluate for relationships:")

        for i, c in enumerate(candidates, 1):
            parts.append(f"  [{i}] ID: {c['id']}")
            parts.append(f"      Type: {c.get('type', 'unknown')}")
            parts.append(f"      Summary: {c.get('summary', '')}")
            parts.append(f"      Detail: {c.get('detail', '')}")
            ctx = c.get("context", [])
            if ctx:
                ctx_str = ", ".join(ctx) if isinstance(ctx, list) else ctx
                parts.append(f"      Context: {ctx_str}")
            parts.append("")

        parts.append("Analyze the new node and suggest meaningful edges to the existing nodes.")
        return "\n".join(parts)

    def _call_ollama(self, prompt: str) -> list[dict] | None:
        """Call Ollama chat API for structured JSON edge suggestions.

        Uses httpx directly to avoid the ollama package (which can hang on import
        when the Ollama server isn't running).

        Returns:
            List of edge suggestion dicts, or None on failure
        """
        try:
            import httpx

            url = f"{self._ollama_base_url}/api/chat"
            payload = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": CURATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.1},
            }
            response = httpx.post(url, json=payload, timeout=120.0)
            response.raise_for_status()

            data = response.json()
            content = data["message"]["content"]
            parsed = json.loads(content)
            edges = parsed.get("edges", [])
            if not isinstance(edges, list):
                logger.warning("Curator response 'edges' is not a list")
                return None
            return edges
        except Exception as e:
            logger.warning(f"Curator LLM call failed: {e}")
            return None

    def _parse_and_create_edges(
        self, new_node_id: str, suggestions: list[dict]
    ) -> list[CognitionEdge]:
        """Validate suggestions and create edges in storage.

        Args:
            new_node_id: ID of the newly added node
            suggestions: Raw edge suggestions from the LLM

        Returns:
            List of successfully created edges
        """
        created = []
        timestamp = datetime.now(timezone.utc).isoformat()

        for s in suggestions:
            candidate_id = s.get("candidate_id", "")
            edge_type_str = s.get("edge_type", "")
            direction = s.get("direction", "")
            reason = s.get("reason", "")

            # Validate
            if edge_type_str not in VALID_EDGE_TYPES:
                logger.debug(f"Curator: skipping invalid edge type '{edge_type_str}'")
                continue
            if direction not in VALID_DIRECTIONS:
                logger.debug(f"Curator: skipping invalid direction '{direction}'")
                continue
            if not self._storage.has_node(candidate_id):
                logger.debug(f"Curator: skipping nonexistent node '{candidate_id}'")
                continue

            # Determine edge direction
            if direction == "from_new":
                from_id, to_id = new_node_id, candidate_id
            else:
                from_id, to_id = candidate_id, new_node_id

            edge = CognitionEdge(
                from_id=from_id,
                to_id=to_id,
                edge_type=CognitionEdgeType(edge_type_str),
                timestamp=timestamp,
            )

            if self._storage.add_edge(edge):
                logger.debug(
                    f"Curator: created {edge_type_str} edge "
                    f"{from_id} -> {to_id} ({reason})"
                )
                created.append(edge)

        return created
