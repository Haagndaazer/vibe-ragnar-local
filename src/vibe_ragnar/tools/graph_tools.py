"""MCP tools for graph operations."""

from typing import Any

from fastmcp import Context

from ..graph import (
    GraphStorage,
    get_call_chain,
    get_callers,
    get_class_hierarchy,
    get_function_calls,
)


def register_graph_tools(mcp) -> None:
    """Register graph tools with the MCP server.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool()
    def tool_get_function_calls(
        ctx: Context,
        function_id: str,
    ) -> dict[str, Any]:
        """Get all functions that a given function calls.

        Args:
            function_id: The entity ID of the function
                        (format: repo:file_path:function_name or repo:file_path:ClassName.method_name)

        Returns:
            List of called functions with their details
        """
        storage: GraphStorage = ctx.request_context.lifespan_context["graph"]
        calls = get_function_calls(storage, function_id)
        return {
            "function_id": function_id,
            "calls": calls,
            "count": len(calls),
        }

    @mcp.tool()
    def tool_get_callers(
        ctx: Context,
        function_id: str,
    ) -> dict[str, Any]:
        """Get all functions that call a given function.

        Args:
            function_id: The entity ID of the function

        Returns:
            List of caller functions with their details
        """
        storage: GraphStorage = ctx.request_context.lifespan_context["graph"]
        callers = get_callers(storage, function_id)
        return {
            "function_id": function_id,
            "callers": callers,
            "count": len(callers),
        }

    @mcp.tool()
    def tool_get_call_chain(
        ctx: Context,
        function_id: str,
        max_depth: int = 5,
        direction: str = "outgoing",
    ) -> dict[str, Any]:
        """Get the call chain from/to a function.

        Args:
            function_id: The entity ID of the function
            max_depth: Maximum depth to traverse (default: 5)
            direction: "outgoing" (what it calls) or "incoming" (what calls it)

        Returns:
            Nested structure showing the call tree
        """
        storage: GraphStorage = ctx.request_context.lifespan_context["graph"]
        chain = get_call_chain(storage, function_id, max_depth, direction)
        return chain

    @mcp.tool()
    def tool_get_class_hierarchy(
        ctx: Context,
        class_id: str,
        direction: str = "both",
    ) -> dict[str, Any]:
        """Get the inheritance hierarchy for a class.

        Args:
            class_id: The entity ID of the class
            direction: "parents" (ancestors), "children" (descendants), or "both"

        Returns:
            Hierarchy structure with ancestors and/or descendants
        """
        storage: GraphStorage = ctx.request_context.lifespan_context["graph"]
        hierarchy = get_class_hierarchy(storage, class_id, direction)
        return hierarchy
