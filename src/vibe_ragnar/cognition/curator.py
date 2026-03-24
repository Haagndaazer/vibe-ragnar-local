"""Curator for the Cognition History Graph — uses a local LLM to create meaningful edges."""

import json
import logging
import queue
import threading
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
incidents, patterns, and episodes (summaries of completed work).

Available edge types:
- led_to: A causal chain. X led to Y happening. Direction matters.
- supersedes: X replaces/updates a previous decision or assumption Y.
- contradicts: X contradicts or conflicts with Y. Only for genuine conflicts.
- relates_to: Same topic/system but no causal or hierarchical relationship. Use sparingly.
- resolved_by: X (incident/failure) was resolved/fixed by Y (decision/discovery).
- part_of: Entity belongs to an episode. Use when an entity and an episode share the same \
issue/PR reference (e.g., both reference "issue:LL-298"). If the new node is an entity and \
the existing node is an episode, direction is "from_new". If the new node is an episode and \
the existing node is an entity, direction is "to_new".
- duplicate_of: The new node is semantically identical to this existing node — same fact, \
same meaning, same type. Use ONLY when nodes genuinely represent the SAME thing, not merely \
related topics. The new node will be merged into the existing one. Direction is always "from_new".

Rules:
- Only suggest edges where there is a genuine, meaningful relationship.
- Do NOT create edges just because nodes share keywords. The relationship must be substantive.
- Prefer specific edge types (led_to, supersedes, contradicts, resolved_by, part_of) over relates_to.
- For part_of: match on shared references (issue numbers, PR numbers). This is the primary signal.
- For supersedes: only use when the new node explicitly replaces an older decision/assumption.
- For contradicts: only use when there is a genuine logical conflict.
- It is perfectly fine to suggest zero edges if none are meaningful.
- Think about directionality carefully.

Respond with JSON only:
{
  "edges": [
    {
      "candidate_id": "<id of the existing node>",
      "edge_type": "<led_to|supersedes|contradicts|relates_to|resolved_by|part_of|duplicate_of>",
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
    """Analyzes new cognition nodes and creates edges to existing related nodes via local LLM.

    Uses a single worker thread with a queue to serialize all curation work,
    preventing concurrent Ollama calls and embedding model access.
    """

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

        self._queue: queue.Queue[CognitionNode | None] = queue.Queue()
        self._ready = threading.Event()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def enqueue(self, node: CognitionNode) -> None:
        """Add a node to the curation queue. Non-blocking."""
        self._queue.put(node)

    def ensure_model(self) -> bool:
        """Ensure the curator model is available in Ollama, pulling if needed.

        Sets the readiness gate on success so the worker thread can begin processing.

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
                self._ready.set()
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
            self._ready.set()
            return True
        except Exception as e:
            logger.warning(f"Failed to ensure curator model: {e}")
            return False

    def curate_uncurated_nodes(self) -> int:
        """Find nodes with no edges and enqueue them for curation.

        Returns:
            Number of nodes enqueued
        """
        all_nodes = self._storage.get_all_nodes()
        if not all_nodes:
            return 0

        enqueued = 0
        for node_data in all_nodes:
            node_id = node_data["id"]
            # Skip if this node already has any edges (incoming or outgoing)
            if (self._storage.get_successors(node_id) or
                    self._storage.get_predecessors(node_id)):
                continue

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
                self.enqueue(node)
                enqueued += 1
            except Exception as e:
                logger.warning(f"Failed to enqueue node {node_id}: {e}")

        if enqueued:
            logger.info(f"Enqueued {enqueued} uncurated node(s) for curation")
        return enqueued

    def _worker_loop(self) -> None:
        """Process nodes from the queue one at a time."""
        while True:
            node = None
            try:
                node = self._queue.get()
                if node is None:
                    break  # Shutdown sentinel
                self._ready.wait()  # Block until ensure_model has succeeded
                logger.info(
                    f"Curating node {node.id} "
                    f"({node.type.value}: {node.summary[:60]})"
                )
                edges = self.curate(node)
                if edges:
                    logger.info(f"Curator created {len(edges)} edge(s) for node {node.id}")
                else:
                    logger.info(f"Curator: no edges created for node {node.id}")
            except Exception as e:
                node_id = node.id if node else "unknown"
                logger.warning(f"Curator failed for node {node_id}: {e}")
            finally:
                self._queue.task_done()

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

        # Validate and create edges (or merge if duplicate detected)
        return self._parse_and_create_edges(node, suggestions)

    @staticmethod
    def _truncate(text: str, max_len: int = 500) -> str:
        """Truncate text to max_len, appending '...' if truncated."""
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."

    def _build_prompt(self, new_node: CognitionNode, candidates: list[dict]) -> str:
        """Build the user prompt with the new node and candidate nodes."""
        parts = [
            "NEW NODE being added:",
            f"  ID: {new_node.id}",
            f"  Type: {new_node.type.value}",
            f"  Summary: {new_node.summary}",
            f"  Detail: {self._truncate(new_node.detail)}",
        ]
        if new_node.context:
            parts.append(f"  Context: {', '.join(new_node.context)}")
        if new_node.references:
            parts.append(f"  References: {', '.join(new_node.references)}")
        if new_node.severity:
            parts.append(f"  Severity: {new_node.severity}")

        parts.append("")
        parts.append("EXISTING NODES to evaluate for relationships:")

        for i, c in enumerate(candidates, 1):
            parts.append(f"  [{i}] ID: {c['id']}")
            parts.append(f"      Type: {c.get('type', 'unknown')}")
            parts.append(f"      Summary: {c.get('summary', '')}")
            detail = c.get('detail', '')
            parts.append(f"      Detail: {self._truncate(detail)}")
            refs = c.get("references", [])
            if refs:
                refs_str = ", ".join(refs) if isinstance(refs, list) else refs
                parts.append(f"      References: {refs_str}")
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
                "options": {"temperature": 0.1, "num_ctx": 4096},
            }
            response = httpx.post(url, json=payload, timeout=300.0)
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
        self, new_node: CognitionNode, suggestions: list[dict]
    ) -> list[CognitionEdge]:
        """Validate suggestions and create edges or handle merges.

        Args:
            new_node: The newly added node
            suggestions: Raw edge suggestions from the LLM

        Returns:
            List of successfully created edges (empty if merged)
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

            # Handle duplicate detection — merge and return early
            if edge_type_str == CognitionEdgeType.DUPLICATE_OF.value:
                self._handle_merge(new_node, candidate_id)
                return []  # No edges to return — node was merged

            # Determine edge direction
            if direction == "from_new":
                from_id, to_id = new_node.id, candidate_id
            else:
                from_id, to_id = candidate_id, new_node.id

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

    def _handle_merge(self, new_node: CognitionNode, existing_id: str) -> None:
        """Merge a duplicate new node into an existing node.

        Keeps the existing (older) node, enriches it with context/references
        from the new node, redirects edges, and removes the new node.
        """
        existing = self._storage.get_node(existing_id)
        if not existing:
            return

        # Merge context (union, dedup)
        merged_context = list(set(existing.get("context", []) + new_node.context))

        # Merge references (union, dedup)
        merged_refs = list(set(existing.get("references", []) + new_node.references))

        # Take higher severity
        severity = existing.get("severity")
        if new_node.severity:
            levels = {"critical": 4, "high": 3, "normal": 2, "low": 1}
            if levels.get(new_node.severity, 0) > levels.get(severity or "", 0):
                severity = new_node.severity

        # Update existing node with merged data
        self._storage.update_node(
            existing_id,
            context=merged_context,
            references=merged_refs,
            severity=severity,
        )

        # Redirect any edges from/to new node to existing node
        redirected = self._storage.redirect_edges(new_node.id, existing_id)

        # Remove new node from graph
        self._storage.remove_node(new_node.id)

        # Remove new node from ChromaDB
        self._embedding_storage.delete_embedding(new_node.id)

        logger.info(
            f"Curator: merged duplicate node {new_node.id} into {existing_id} "
            f"({redirected} edge(s) redirected)"
        )
