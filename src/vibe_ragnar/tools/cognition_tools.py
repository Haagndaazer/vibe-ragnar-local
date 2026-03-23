"""MCP tools for the Cognition History Graph."""

from datetime import datetime, timezone
from typing import Any

from fastmcp import Context

from ..cognition import (
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
from ..embeddings import ChromaDBStorage, EmbeddingGenerator


def _record_node(
    ctx: Context,
    node_type: CognitionNodeType,
    summary: str,
    detail: str,
    context: str,
    author: str,
    severity: str | None = None,
    references: str | None = None,
    led_from: str | None = None,
) -> dict[str, Any]:
    """Shared logic for cognition_record tool."""
    storage: CognitionStorage = ctx.request_context.lifespan_context["cognition_storage"]
    embedding_storage: ChromaDBStorage = ctx.request_context.lifespan_context[
        "cognition_embedding_storage"
    ]
    generator: EmbeddingGenerator = ctx.request_context.lifespan_context["embedding_generator"]

    # Parse comma-separated strings into lists
    context_list = [c.strip() for c in context.split(",") if c.strip()] if context else []
    references_list = [r.strip() for r in references.split(",") if r.strip()] if references else []

    timestamp = datetime.now(timezone.utc).isoformat()
    node_id = generate_node_id(node_type.value, summary, timestamp)

    node = CognitionNode(
        id=node_id,
        type=node_type,
        summary=summary,
        detail=detail,
        context=context_list,
        references=references_list,
        severity=severity,
        timestamp=timestamp,
        author=author,
    )
    storage.add_node(node)

    # Embed and upsert to ChromaDB
    embed_text = f"{node_type.value}: {summary}\n{detail}"
    embedding = generator.generate_query_embedding(embed_text)
    metadata: dict[str, Any] = {
        "entity_type": node_type.value,
        "summary": summary,
        "author": author,
        "timestamp": timestamp,
        "context": ",".join(context_list),
    }
    if severity:
        metadata["severity"] = severity
    if references_list:
        metadata["references"] = ",".join(references_list)
    embedding_storage.upsert_embedding(node_id, embedding, metadata)

    # Optionally create LED_TO edge from an existing node
    edge_created = False
    if led_from and storage.has_node(led_from):
        edge = CognitionEdge(
            from_id=led_from,
            to_id=node_id,
            edge_type=CognitionEdgeType.LED_TO,
            timestamp=timestamp,
        )
        edge_created = storage.add_edge(edge)

    return {
        "id": node_id,
        "type": node_type.value,
        "summary": summary,
        "timestamp": timestamp,
        "edge_from": led_from if edge_created else None,
    }


def register_cognition_tools(mcp) -> None:
    """Register cognition graph tools with the MCP server.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool()
    def cognition_record(
        ctx: Context,
        node_type: str,
        summary: str,
        detail: str,
        context: str,
        author: str,
        severity: str | None = None,
        references: str | None = None,
        led_from: str | None = None,
    ) -> dict[str, Any]:
        """Record a cognition node — a decision, failure, discovery, or other knowledge artifact.

        Use this to capture important context from conversations: what was decided,
        what failed, what was discovered, assumptions made, constraints identified,
        production incidents, or generalized patterns/lessons learned.

        Args:
            node_type: One of: decision, fail, discovery, assumption, constraint, incident, pattern
            summary: Short description
            detail: Full context, rationale, and reasoning
            context: Related code areas, file paths, or topics (comma-separated)
            author: Who is recording this
            severity: Optional priority (critical, high, normal, low)
            references: Optional external refs, comma-separated (e.g., "pr:97,issue:LL-298")
            led_from: Optional existing node ID that led to this (creates a LED_TO edge)

        Returns:
            The created node with ID and timestamp
        """
        try:
            nt = CognitionNodeType(node_type)
        except ValueError:
            valid = [e.value for e in CognitionNodeType]
            return {"error": f"Invalid node_type '{node_type}'. Valid: {valid}"}

        return _record_node(
            ctx, nt, summary, detail, context, author,
            severity, references, led_from,
        )

    @mcp.tool()
    def cognition_add_edge(
        ctx: Context,
        from_id: str,
        to_id: str,
        edge_type: str,
    ) -> dict[str, Any]:
        """Create a typed edge between two existing cognition nodes.

        Args:
            from_id: Source node ID
            to_id: Target node ID
            edge_type: One of: led_to, supersedes, contradicts, relates_to, resolved_by

        Returns:
            Edge details or error
        """
        storage: CognitionStorage = ctx.request_context.lifespan_context["cognition_storage"]

        try:
            et = CognitionEdgeType(edge_type)
        except ValueError:
            valid = [e.value for e in CognitionEdgeType]
            return {"error": f"Invalid edge type '{edge_type}'. Valid: {valid}"}

        timestamp = datetime.now(timezone.utc).isoformat()
        edge = CognitionEdge(
            from_id=from_id,
            to_id=to_id,
            edge_type=et,
            timestamp=timestamp,
        )

        if storage.add_edge(edge):
            return {
                "from_id": from_id,
                "to_id": to_id,
                "edge_type": edge_type,
                "timestamp": timestamp,
            }
        return {"error": f"One or both nodes not found (from={from_id}, to={to_id})"}

    @mcp.tool()
    def cognition_search(
        ctx: Context,
        query: str,
        node_type: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search cognition history using natural language.

        Finds decisions, failures, discoveries, incidents, patterns, etc.
        by semantic similarity to the query.

        Args:
            query: What you're looking for, e.g.:
                   - "caching strategy decisions"
                   - "what failed with the migration"
                   - "localization issues"
            node_type: Optional filter: decision, fail, discovery, assumption,
                       constraint, incident, pattern
            limit: Max results (default: 10)

        Returns:
            Matching cognition nodes with similarity scores
        """
        embedding_storage: ChromaDBStorage = ctx.request_context.lifespan_context[
            "cognition_embedding_storage"
        ]
        generator: EmbeddingGenerator = ctx.request_context.lifespan_context["embedding_generator"]

        limit = min(limit, 50)
        query_embedding = generator.generate_query_embedding(query)

        results = embedding_storage.vector_search(
            query_embedding=query_embedding,
            limit=limit,
            entity_type=node_type,
        )

        formatted = []
        for r in results:
            formatted.append({
                "id": r.get("_id"),
                "node_type": r.get("entity_type"),
                "summary": r.get("summary") or r.get("name"),
                "author": r.get("author"),
                "timestamp": r.get("timestamp"),
                "severity": r.get("severity"),
                "context": r.get("context", ""),
                "score": r.get("score"),
            })

        return {
            "query": query,
            "results": formatted,
            "count": len(formatted),
        }

    @mcp.tool()
    def cognition_get_history(
        ctx: Context,
        context_term: str | None = None,
        node_type: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Get cognition nodes by context area, type, or recency.

        If context_term is provided, filters nodes whose context fields match
        (case-insensitive substring). Otherwise returns the most recent nodes.

        Args:
            context_term: Optional term to search in context fields (file paths, topics)
            node_type: Optional filter: decision, fail, discovery, assumption,
                       constraint, incident, pattern
            limit: Max results (default: 20)

        Returns:
            Matching cognition nodes sorted by timestamp (newest first)
        """
        storage: CognitionStorage = ctx.request_context.lifespan_context["cognition_storage"]

        nt = None
        if node_type:
            try:
                nt = CognitionNodeType(node_type)
            except ValueError:
                valid = [e.value for e in CognitionNodeType]
                return {"error": f"Invalid node type '{node_type}'. Valid: {valid}"}

        if context_term:
            results = get_history_for_context(storage, context_term, nt)
            results = results[:limit]
        else:
            results = storage.get_recent_nodes(limit=limit, node_type=nt)

        return {
            "context_term": context_term,
            "results": results,
            "count": len(results),
        }
