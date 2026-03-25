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


def _load_embeddings_and_index(config: Settings, context: dict[str, Any]) -> None:
    """Background thread: load embedding model, start watcher, run indexing.

    This runs after the MCP handshake completes so the server starts fast.
    """
    try:
        # Load embedding model (the bottleneck: 2-30s)
        logger.info(f"Loading embedding model ({config.embedding_backend})...")
        embedding_generator = EmbeddingGenerator.from_config(config)
        logger.info("Embedding model loaded")

        embedding_storage: ChromaDBStorage = context["embedding_storage"]
        embedding_sync = EmbeddingSync(
            generator=embedding_generator,
            storage=embedding_storage,
            repo_name=config.effective_repo_name,
        )

        # Populate context
        context["embedding_generator"] = embedding_generator
        context["embedding_sync"] = embedding_sync

        # Init curator (depends on embedding_generator)
        cognition_curator = None
        if config.curator_enabled:
            from .cognition.curator import CognitionCurator

            cognition_curator = CognitionCurator(
                storage=context["cognition_storage"],
                embedding_storage=context["cognition_embedding_storage"],
                embedding_generator=embedding_generator,
                ollama_base_url=config.ollama_base_url,
                model=config.curator_model,
                max_candidates=config.curator_max_candidates,
            )
            context["cognition_curator"] = cognition_curator
            logger.info(f"Cognition curator initialized (model: {config.curator_model})")

        # Signal that embedding-dependent tools are ready
        context["embedding_ready"].set()
        logger.info("All tools now available")

        # Start file watcher (depends on embedding_sync)
        parser: TreeSitterParser = context["parser"]
        graph_builder: GraphBuilder = context["graph_builder"]
        graph_storage: GraphStorage = context["graph"]

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
        context["watcher"] = watcher
        context["watcher_active"] = True
        logger.info("File watcher started")

        # Run initial indexing
        run_initial_indexing(
            parser=parser,
            graph_builder=graph_builder,
            graph_storage=graph_storage,
            embedding_sync=embedding_sync,
            repo_path=config.repo_path,
            context=context,
            include_dirs=config.include_dirs,
        )

    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        context["embedding_error"] = str(e)
        context["embedding_ready"].set()  # Signal so tools don't hang forever


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

    # ── Fast init (blocking, ~500ms-1s) ───────────────────────────────

    # Initialize ChromaDB storage
    logger.info(f"Initializing ChromaDB at {config.chromadb_path}...")
    embedding_storage = ChromaDBStorage(
        persist_directory=config.chromadb_path,
        collection_name=config.chromadb_collection,
    )

    # Initialize graph storage with persistence
    logger.info(f"Initializing graph storage at {config.graph_pickle_path}...")
    graph_storage = GraphStorage(persist_path=config.graph_pickle_path)

    # Initialize parser
    logger.info("Initializing parser...")
    parser = TreeSitterParser(config.effective_repo_name)

    # Initialize graph builder
    graph_builder = GraphBuilder(graph_storage)

    # Initialize cognition graph
    logger.info(f"Initializing cognition graph at {config.cognition_dir}...")
    cognition_storage = CognitionStorage(config.cognition_dir)
    cognition_embedding_storage = ChromaDBStorage(
        persist_directory=config.cognition_chromadb_path,
        collection_name="cognition_embeddings",
    )

    # Build context for tools
    context: dict[str, Any] = {
        "config": config,
        "graph": graph_storage,
        "graph_builder": graph_builder,
        "parser": parser,
        "embedding_storage": embedding_storage,
        "embedding_generator": None,  # Set by background thread
        "embedding_sync": None,  # Set by background thread
        "cognition_storage": cognition_storage,
        "cognition_embedding_storage": cognition_embedding_storage,
        "cognition_curator": None,  # Set by background thread
        "embedding_ready": threading.Event(),
        "watcher": None,  # Set by background thread
        "watcher_active": False,
        "indexing_complete": False,
        "indexing_error": None,
        "indexing_phase": "starting",
        "indexing_total_entities": 0,
        "indexing_embeddable_entities": 0,
    }

    # ── Background init (2-30s for model, then indexing) ──────────────

    bg_thread = threading.Thread(
        target=_load_embeddings_and_index,
        args=(config, context),
        daemon=True,
    )
    bg_thread.start()
    context["_bg_thread"] = bg_thread

    logger.info("Vibe RAGnar ready (embedding model loading in background)")

    yield context

    # ── Cleanup ───────────────────────────────────────────────────────

    logger.info("Shutting down Vibe RAGnar...")

    # Give background thread a chance to finish
    bg_thread = context.get("_bg_thread")
    if bg_thread:
        bg_thread.join(timeout=5.0)

    watcher = context.get("watcher")
    if watcher:
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
