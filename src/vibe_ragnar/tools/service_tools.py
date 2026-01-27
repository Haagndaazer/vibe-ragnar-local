"""MCP tools for service management operations."""

import logging
from typing import Any

from fastmcp import Context

from ..embeddings import ChromaDBStorage, EmbeddingSync
from ..graph import GraphBuilder, GraphStorage
from ..parser import TreeSitterParser

logger = logging.getLogger(__name__)


def register_service_tools(mcp) -> None:
    """Register service tools with the MCP server.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool()
    def get_index_status(ctx: Context) -> dict[str, Any]:
        """Get the current status of the code index.

        Returns statistics about the indexed repository including
        entity counts, embedding counts, and watcher status.

        Returns:
            Index statistics and status information
        """
        config = ctx.request_context.lifespan_context["config"]
        graph: GraphStorage = ctx.request_context.lifespan_context["graph"]
        embedding_storage: ChromaDBStorage = ctx.request_context.lifespan_context["embedding_storage"]
        watcher_active = ctx.request_context.lifespan_context.get("watcher_active", False)
        indexing_complete = ctx.request_context.lifespan_context.get("indexing_complete", False)
        indexing_error = ctx.request_context.lifespan_context.get("indexing_error")
        indexing_phase = ctx.request_context.lifespan_context.get("indexing_phase", "starting")
        indexing_total_entities = ctx.request_context.lifespan_context.get("indexing_total_entities", 0)
        indexing_embeddable = ctx.request_context.lifespan_context.get("indexing_embeddable_entities", 0)

        # Get graph statistics
        graph_stats = graph.get_statistics()

        # Get embedding count
        embedding_count = embedding_storage.count_documents(
            {"repo": config.effective_repo_name}
        )

        # Determine status
        if indexing_error:
            status = "error"
        elif indexing_complete:
            status = "ready"
        else:
            status = "indexing"

        result = {
            "status": status,
            "repo_name": config.effective_repo_name,
            "repo_path": str(config.repo_path),
            "graph": {
                "total_nodes": graph_stats["nodes"],
                "total_edges": graph_stats["edges"],
                "functions": graph_stats["functions"],
                "classes": graph_stats["classes"],
                "files": graph_stats["files"],
                "types": graph_stats["types"],
                "external_references": graph_stats["external"],
            },
            "embeddings": {
                "total": embedding_count,
            },
            "watcher_active": watcher_active,
        }

        # Add indexing progress info
        if not indexing_complete:
            result["indexing"] = {
                "phase": indexing_phase,
                "total_entities": indexing_total_entities,
                "embeddable_entities": indexing_embeddable,
            }
            if indexing_error:
                result["indexing"]["error"] = indexing_error
        else:
            result["indexing"] = {
                "phase": "complete",
                "total_entities": indexing_total_entities,
                "embeddable_entities": indexing_embeddable,
            }

        return result

    @mcp.tool()
    def reindex(
        ctx: Context,
        path: str | None = None,
        full: bool = False,
    ) -> dict[str, Any]:
        """Reindex the codebase or a specific path.

        Use this to force a reindex when files have changed outside
        of the file watcher's detection, or after configuration changes.

        Args:
            path: Optional path to reindex (relative to repo root).
                  If not provided, reindexes the entire repository.
            full: If true, delete all existing embeddings first.
                  Use this for a clean slate reindex.

        Returns:
            Reindexing results with counts
        """
        config = ctx.request_context.lifespan_context["config"]
        parser: TreeSitterParser = ctx.request_context.lifespan_context["parser"]
        graph: GraphStorage = ctx.request_context.lifespan_context["graph"]
        graph_builder: GraphBuilder = ctx.request_context.lifespan_context["graph_builder"]
        embedding_sync: EmbeddingSync = ctx.request_context.lifespan_context["embedding_sync"]

        # Determine target path
        target_path = config.repo_path / path if path else config.repo_path

        if not target_path.exists():
            return {
                "error": f"Path does not exist: {target_path}",
                "path": str(target_path),
            }

        logger.info(f"Reindexing {'(full)' if full else ''}: {target_path}")

        # Clear existing data if full reindex
        if full or path is None:
            graph_builder.clear()
            logger.info("Cleared graph")

        # Parse files
        if target_path.is_file():
            entities = parser.parse_file(target_path, config.repo_path)
        else:
            entities = parser.parse_directory(target_path, config.repo_path)

        # Build graph
        graph_builder.build_from_entities(entities)

        # Sync embeddings
        if full:
            sync_result = embedding_sync.full_reindex(entities)
        else:
            sync_result = embedding_sync.sync_entities(entities)

        # Get updated stats
        graph_stats = graph.get_statistics()

        return {
            "path": str(target_path),
            "full_reindex": full,
            "entities_parsed": len(entities),
            "graph": {
                "nodes": graph_stats["nodes"],
                "edges": graph_stats["edges"],
            },
            "embeddings": {
                "added": sync_result.added,
                "updated": sync_result.updated,
                "deleted": sync_result.deleted,
                "skipped": sync_result.skipped,
                "errors": len(sync_result.errors),
            },
        }
