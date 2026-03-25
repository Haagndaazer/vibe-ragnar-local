"""MCP tools for graph queries, semantic search, and cognition history."""

from typing import Any

from fastmcp import Context

from .cognition_tools import register_cognition_tools
from .graph_tools import register_graph_tools
from .search_tools import register_search_tools
from .service_tools import register_service_tools


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


def register_all_tools(mcp) -> None:
    """Register all MCP tools with the server.

    Args:
        mcp: FastMCP server instance
    """
    register_graph_tools(mcp)
    register_search_tools(mcp)
    register_service_tools(mcp)
    register_cognition_tools(mcp)


__all__ = [
    "register_all_tools",
    "register_cognition_tools",
    "register_graph_tools",
    "register_search_tools",
    "register_service_tools",
]
