"""MCP tools for semantic search operations."""

from typing import Any

from fastmcp import Context

from ..embeddings import EmbeddingGenerator, MongoDBStorage


def register_search_tools(mcp) -> None:
    """Register search tools with the MCP server.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool()
    def semantic_search(
        ctx: Context,
        query: str,
        limit: int = 5,
        entity_type: str | None = None,
        file_path_prefix: str | None = None,
    ) -> dict[str, Any]:
        """Search for code using natural language.

        Args:
            query: What you're looking for, e.g.:
                   - "how to parse JSON config"
                   - "error handling in API calls"
                   - "user authentication logic"
                   - "where are database queries executed"
            limit: Max results (default: 5, max: 50)
            entity_type: Optional, don't use by default. Only set when you
                         specifically need just "function", "class", or "type"
            file_path_prefix: Optional, filter to files starting with this path

        Returns:
            Matching code entities with similarity scores
        """
        generator: EmbeddingGenerator = ctx.request_context.lifespan_context["embedding_generator"]
        storage: MongoDBStorage = ctx.request_context.lifespan_context["embedding_storage"]
        config = ctx.request_context.lifespan_context["config"]

        # Enforce limit
        limit = min(limit, 50)

        # Generate query embedding
        query_embedding = generator.generate_query_embedding(query)

        # Search MongoDB
        results = storage.vector_search(
            query_embedding=query_embedding,
            limit=limit,
            repo=config.effective_repo_name,
            entity_type=entity_type,
            file_path_prefix=file_path_prefix,
        )

        # Format results
        formatted_results = []
        for r in results:
            formatted_results.append({
                "id": r.get("_id"),
                "name": r.get("name"),
                "file_path": r.get("file_path"),
                "entity_type": r.get("entity_type"),
                "signature": r.get("signature"),
                "docstring": r.get("docstring"),
                "class_name": r.get("class_name"),
                "start_line": r.get("start_line"),
                "end_line": r.get("end_line"),
                "score": r.get("score"),
            })

        return {
            "query": query,
            "results": formatted_results,
            "count": len(formatted_results),
        }
