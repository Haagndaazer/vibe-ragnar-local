"""MCP tools for graph queries and semantic search."""

from .graph_tools import register_graph_tools
from .search_tools import register_search_tools
from .service_tools import register_service_tools


def register_all_tools(mcp) -> None:
    """Register all MCP tools with the server.

    Args:
        mcp: FastMCP server instance
    """
    register_graph_tools(mcp)
    register_search_tools(mcp)
    register_service_tools(mcp)


__all__ = [
    "register_all_tools",
    "register_graph_tools",
    "register_search_tools",
    "register_service_tools",
]
