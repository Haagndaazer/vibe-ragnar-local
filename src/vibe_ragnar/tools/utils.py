"""Shared utilities for MCP tools."""

from typing import Any

from fastmcp import Context


def require_embeddings(ctx: Context) -> dict[str, Any] | None:
    """Check if the embedding model is loaded. Returns error dict if not ready, None if ready."""
    lc = ctx.request_context.lifespan_context
    event = lc.get("embedding_ready")
    if event is None or not event.is_set():
        return {
            "error": "Embedding model is still loading. Graph and cognition history "
                     "tools are available now. Try again in a few seconds.",
            "status": "loading_embeddings",
        }
    error = lc.get("embedding_error")
    if error:
        return {"error": f"Embedding model failed to load: {error}", "status": "embedding_error"}
    return None
