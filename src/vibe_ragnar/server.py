"""FastMCP server for Vibe RAGnar - code indexing with graph analysis and semantic search."""

import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from .cognition import CognitionStorage
from .config import Settings, setup_logging
from .embeddings import ChromaDBStorage, EmbeddingGenerator, EmbeddingSync
from .graph import GraphBuilder, GraphStorage
from .parser import TreeSitterParser
from .tools import register_all_tools
from .watcher import FileWatcher

logger = logging.getLogger(__name__)


def create_file_change_handler(
    parser: TreeSitterParser,
    graph_builder: GraphBuilder,
    graph_storage: GraphStorage,
    embedding_sync: EmbeddingSync,
    repo_root: Path,
):
    """Create a callback function for handling file changes.

    Args:
        parser: TreeSitterParser instance
        graph_builder: GraphBuilder instance
        graph_storage: GraphStorage instance for persistence
        embedding_sync: EmbeddingSync instance
        repo_root: Repository root path

    Returns:
        Callback function for FileWatcher
    """

    def handle_changes(changes: dict[str, str]) -> None:
        """Handle accumulated file changes.

        Args:
            changes: Dict mapping file paths to change types ("upsert" or "delete")
        """
        for file_path_str, change_type in changes.items():
            file_path = Path(file_path_str)

            try:
                relative_path = str(file_path.relative_to(repo_root))

                if change_type == "delete":
                    graph_builder.remove_file(relative_path)
                    embedding_sync.delete_file(relative_path)
                    logger.info(f"Removed: {relative_path}")

                else:  # upsert
                    entities = parser.parse_file(file_path, repo_root)
                    graph_builder.update_file(relative_path, entities)
                    result = embedding_sync.sync_file(relative_path, entities)
                    logger.info(f"Updated: {relative_path} ({result})")

            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}")

        # Save graph after processing changes
        graph_storage.save()

    return handle_changes


def run_initial_indexing(
    parser: TreeSitterParser,
    graph_builder: GraphBuilder,
    graph_storage: GraphStorage,
    embedding_sync: EmbeddingSync,
    repo_path: Path,
    context: dict[str, Any],
    include_dirs: list[str] | None = None,
) -> None:
    """Run initial indexing in background thread.

    Args:
        parser: TreeSitterParser instance
        graph_builder: GraphBuilder instance
        graph_storage: GraphStorage instance for persistence
        embedding_sync: EmbeddingSync instance
        repo_path: Repository root path
        context: Server context dict to update indexing_complete flag
        include_dirs: Directories to include even if normally ignored
    """
    try:
        logger.info("Starting background indexing...")

        # Phase 1: Parsing
        context["indexing_phase"] = "parsing"
        entities = parser.parse_directory(repo_path, repo_path, include_dirs=include_dirs)
        context["indexing_total_entities"] = len(entities)
        # Count embeddable entities (functions and classes only)
        embeddable = sum(1 for e in entities if e.entity_type in ("function", "class"))
        context["indexing_embeddable_entities"] = embeddable
        logger.info(f"Parsed {len(entities)} entities ({embeddable} embeddable)")

        # Phase 2: Building graph
        context["indexing_phase"] = "building_graph"
        graph_builder.build_from_entities(entities)
        graph_storage.save()  # Persist graph after initial build
        logger.info("Graph built and saved successfully")

        # Phase 3: Syncing embeddings
        try:
            context["indexing_phase"] = "syncing_embeddings"
            sync_result = embedding_sync.sync_entities(entities)
            logger.info(f"Embedding sync: {sync_result}")
        except Exception as e:
            logger.error(f"Code embedding sync failed: {e}")

        context["indexing_phase"] = "complete"
        context["indexing_complete"] = True
        logger.info("Background indexing completed successfully")

        # Phase 4: Cognition graph sync + curation
        # Runs after code indexing to avoid concurrent embedding model access
        cognition_storage = context.get("cognition_storage")
        cognition_embedding_storage = context.get("cognition_embedding_storage")
        cognition_curator = context.get("cognition_curator")
        embedding_generator = context.get("embedding_generator")

        if cognition_storage and cognition_embedding_storage and embedding_generator:
            logger.info("Syncing cognition embeddings...")
            _sync_cognition_embeddings(
                cognition_storage, cognition_embedding_storage, embedding_generator
            )

        if cognition_curator is not None:
            if cognition_curator.ensure_model():
                count = cognition_curator.curate_uncurated_nodes()
                if count:
                    logger.info(f"Curator: enqueued {count} uncurated node(s)")
            else:
                logger.warning("Curator model not available — skipping startup curation")

    except Exception as e:
        logger.error(f"Background indexing failed: {e}")
        context["indexing_error"] = str(e)


def _sync_cognition_embeddings(
    cognition_storage: CognitionStorage,
    embedding_storage: ChromaDBStorage,
    generator: EmbeddingGenerator,
) -> None:
    """Sync cognition nodes from JSONL into ChromaDB if missing.

    This handles the case where a teammate pulled new JSONL entries via Git
    but the local ChromaDB doesn't have their embeddings yet.
    """
    all_nodes = cognition_storage.get_all_nodes()
    if not all_nodes:
        return

    # Get existing IDs from ChromaDB in one call
    existing_ids = set()
    try:
        results = embedding_storage._collection.get(ids=[n["id"] for n in all_nodes])
        existing_ids = set(results["ids"])
    except Exception:
        pass  # If collection is empty or IDs not found, treat all as missing

    missing = [n for n in all_nodes if n["id"] not in existing_ids]

    if not missing:
        logger.info("Cognition embeddings: all nodes already synced")
        return

    logger.info(f"Syncing {len(missing)} cognition nodes to ChromaDB...")
    for node in missing:
        embed_text = f"{node.get('type', '')}: {node.get('summary', '')}\n{node.get('detail', '')}"
        embedding = generator.generate_query_embedding(embed_text)
        metadata = {
            "entity_type": node.get("type", ""),
            "summary": node.get("summary", ""),
            "author": node.get("author", ""),
            "timestamp": node.get("timestamp", ""),
            "context": ",".join(node.get("context", [])),
        }
        if node.get("severity"):
            metadata["severity"] = node["severity"]
        if node.get("references"):
            metadata["references"] = ",".join(node["references"])
        embedding_storage.upsert_embedding(node["id"], embedding, metadata)

    logger.info(f"Cognition embedding sync complete: {len(missing)} nodes added")


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Manage server lifecycle - initialize and cleanup resources."""
    # Load configuration
    try:
        config = Settings()
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise

    setup_logging(config.log_level)
    logger.info(f"Starting Vibe RAGnar for repository: {config.effective_repo_name}")
    logger.info(f"Repository path: {config.repo_path}")

    # Initialize ChromaDB storage
    logger.info(f"Initializing ChromaDB at {config.chromadb_path}...")
    embedding_storage = ChromaDBStorage(
        persist_directory=config.chromadb_path,
        collection_name=config.chromadb_collection,
    )

    # Initialize embedding generator
    logger.info(f"Initializing embedding backend ({config.embedding_backend})...")
    embedding_generator = EmbeddingGenerator.from_config(config)

    # Initialize graph storage with persistence
    logger.info(f"Initializing graph storage at {config.graph_pickle_path}...")
    graph_storage = GraphStorage(persist_path=config.graph_pickle_path)

    # Initialize parser
    logger.info("Initializing parser...")
    parser = TreeSitterParser(config.effective_repo_name)

    # Initialize graph builder
    graph_builder = GraphBuilder(graph_storage)

    # Initialize embedding sync
    embedding_sync = EmbeddingSync(
        generator=embedding_generator,
        storage=embedding_storage,
        repo_name=config.effective_repo_name,
    )

    # Initialize cognition graph
    logger.info(f"Initializing cognition graph at {config.cognition_dir}...")
    cognition_storage = CognitionStorage(config.cognition_dir)
    cognition_embedding_storage = ChromaDBStorage(
        persist_directory=config.cognition_chromadb_path,
        collection_name="cognition_embeddings",
    )

    # Initialize cognition curator
    cognition_curator = None
    if config.curator_enabled:
        from .cognition.curator import CognitionCurator

        cognition_curator = CognitionCurator(
            storage=cognition_storage,
            embedding_storage=cognition_embedding_storage,
            embedding_generator=embedding_generator,
            ollama_base_url=config.ollama_base_url,
            model=config.curator_model,
            max_candidates=config.curator_max_candidates,
        )
        logger.info(f"Cognition curator initialized (model: {config.curator_model})")

    # Build context for tools (before indexing so MCP handshake completes quickly)
    context: dict[str, Any] = {
        "config": config,
        "graph": graph_storage,
        "graph_builder": graph_builder,
        "parser": parser,
        "embedding_storage": embedding_storage,
        "embedding_generator": embedding_generator,
        "embedding_sync": embedding_sync,
        "cognition_storage": cognition_storage,
        "cognition_embedding_storage": cognition_embedding_storage,
        "cognition_curator": cognition_curator,
        "watcher": None,  # Will be set after watcher starts
        "watcher_active": False,
        "indexing_complete": False,
        "indexing_error": None,
        "indexing_phase": "starting",
        "indexing_total_entities": 0,
        "indexing_embeddable_entities": 0,
    }

    # Start background indexing
    indexing_thread = threading.Thread(
        target=run_initial_indexing,
        args=(
            parser,
            graph_builder,
            graph_storage,
            embedding_sync,
            config.repo_path,
            context,
            config.include_dirs,
        ),
        daemon=True,
    )
    indexing_thread.start()

    # Initialize file watcher
    logger.info("Starting file watcher...")
    change_handler = create_file_change_handler(
        parser=parser,
        graph_builder=graph_builder,
        graph_storage=graph_storage,
        embedding_sync=embedding_sync,
        repo_root=config.repo_path,
    )

    watcher = FileWatcher(
        repo_path=config.repo_path,
        on_changes=change_handler,
        debounce_seconds=config.debounce_seconds,
    )
    watcher.start()

    # Update context with watcher
    context["watcher"] = watcher
    context["watcher_active"] = True

    logger.info("Vibe RAGnar ready (indexing in background)")

    yield context

    # Cleanup
    logger.info("Shutting down Vibe RAGnar...")
    watcher.stop()
    graph_storage.save()  # Save graph on shutdown
    embedding_storage.close()
    cognition_embedding_storage.close()
    logger.info("Shutdown complete")


# Create the MCP server
mcp = FastMCP("Vibe RAGnar", lifespan=lifespan)

# Register all tools
register_all_tools(mcp)


def main():
    """Entry point for the Vibe RAGnar MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
