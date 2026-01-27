"""ChromaDB storage for vector embeddings."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import chromadb

logger = logging.getLogger(__name__)


class ChromaDBStorage:
    """Storage for code embeddings using ChromaDB with local persistence."""

    def __init__(
        self,
        persist_directory: Path,
        collection_name: str = "code_embeddings",
    ):
        """Initialize ChromaDB connection.

        Args:
            persist_directory: Directory for persistent storage
            collection_name: Collection name for embeddings
        """
        persist_directory.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_directory))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"ChromaDB initialized at {persist_directory}")

    def upsert_embedding(
        self,
        entity_id: str,
        embedding: list[float],
        metadata: dict[str, Any],
    ) -> None:
        """Insert or update an embedding.

        Args:
            entity_id: Unique entity ID
            embedding: Embedding vector
            metadata: Entity metadata (content_hash, entity_type, file_path, etc.)
        """
        flat_metadata = self._flatten_metadata(metadata)
        self._collection.upsert(
            ids=[entity_id],
            embeddings=[embedding],
            metadatas=[flat_metadata],
        )

    def bulk_upsert(
        self,
        items: list[tuple[str, list[float], dict[str, Any]]],
    ) -> int:
        """Bulk upsert multiple embeddings.

        Args:
            items: List of (entity_id, embedding, metadata) tuples

        Returns:
            Number of items processed
        """
        if not items:
            return 0

        ids = []
        embeddings = []
        metadatas = []

        for entity_id, embedding, metadata in items:
            ids.append(entity_id)
            embeddings.append(embedding)
            metadatas.append(self._flatten_metadata(metadata))

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        return len(items)

    def _flatten_metadata(self, metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
        """Flatten metadata to ChromaDB-compatible types.

        ChromaDB only supports str, int, float, bool as metadata values.

        Args:
            metadata: Original metadata dict

        Returns:
            Flattened metadata with only primitive types
        """
        flat: dict[str, str | int | float | bool] = {}
        now = datetime.utcnow().isoformat()

        for key, value in metadata.items():
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                flat[key] = value
            elif isinstance(value, list):
                # Convert lists to comma-separated strings
                flat[key] = ",".join(str(v) for v in value)
            else:
                # Convert other types to string
                flat[key] = str(value)

        flat["updated_at"] = now
        return flat

    def delete_embedding(self, entity_id: str) -> bool:
        """Delete an embedding by entity ID.

        Args:
            entity_id: Entity ID to delete

        Returns:
            True if deleted (ChromaDB doesn't report actual deletion)
        """
        try:
            self._collection.delete(ids=[entity_id])
            return True
        except Exception:
            return False

    def delete_by_file(self, repo: str, file_path: str) -> int:
        """Delete all embeddings for a specific file.

        Args:
            repo: Repository name
            file_path: File path

        Returns:
            Number of deleted documents
        """
        # Get all IDs matching the file
        results = self._collection.get(
            where={"$and": [{"repo": repo}, {"file_path": file_path}]},
        )

        if results["ids"]:
            self._collection.delete(ids=results["ids"])
            return len(results["ids"])

        return 0

    def delete_by_repo(self, repo: str) -> int:
        """Delete all embeddings for a repository.

        Args:
            repo: Repository name

        Returns:
            Number of deleted documents
        """
        results = self._collection.get(where={"repo": repo})

        if results["ids"]:
            self._collection.delete(ids=results["ids"])
            return len(results["ids"])

        return 0

    def get_by_id(self, entity_id: str) -> dict[str, Any] | None:
        """Get an embedding document by ID.

        Args:
            entity_id: Entity ID

        Returns:
            Document or None if not found
        """
        results = self._collection.get(
            ids=[entity_id],
            include=["metadatas", "embeddings"],
        )

        if results["ids"]:
            return {
                "_id": results["ids"][0],
                "metadata": results["metadatas"][0] if results["metadatas"] else {},
                "embedding": results["embeddings"][0] if results["embeddings"] else None,
            }

        return None

    def get_content_hashes(self, repo: str) -> dict[str, str]:
        """Get all entity IDs and their content hashes for a repository.

        Args:
            repo: Repository name

        Returns:
            Dictionary mapping entity_id to content_hash
        """
        results = self._collection.get(
            where={"repo": repo},
            include=["metadatas"],
        )

        hashes: dict[str, str] = {}
        for i, entity_id in enumerate(results["ids"]):
            metadata = results["metadatas"][i] if results["metadatas"] else {}
            content_hash = metadata.get("content_hash", "")
            hashes[entity_id] = content_hash if isinstance(content_hash, str) else ""

        return hashes

    def vector_search(
        self,
        query_embedding: list[float],
        limit: int = 10,
        repo: str | None = None,
        entity_type: str | None = None,
        file_path_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        """Perform vector similarity search.

        Args:
            query_embedding: Query embedding vector
            limit: Maximum number of results
            repo: Filter by repository name
            entity_type: Filter by entity type
            file_path_prefix: Filter by file path prefix

        Returns:
            List of matching documents with similarity scores
        """
        # Build where filter
        where_conditions = []
        if repo:
            where_conditions.append({"repo": repo})
        if entity_type:
            where_conditions.append({"entity_type": entity_type})

        where_filter = None
        if len(where_conditions) == 1:
            where_filter = where_conditions[0]
        elif len(where_conditions) > 1:
            where_filter = {"$and": where_conditions}

        # Query more results if we need to filter by prefix
        query_limit = limit * 3 if file_path_prefix else limit

        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=query_limit,
                where=where_filter,
                include=["metadatas", "distances"],
            )
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

        # Process results
        output: list[dict[str, Any]] = []
        ids = results["ids"][0] if results["ids"] else []
        metadatas = results["metadatas"][0] if results["metadatas"] else []
        distances = results["distances"][0] if results["distances"] else []

        for i, entity_id in enumerate(ids):
            metadata = metadatas[i] if i < len(metadatas) else {}
            distance = distances[i] if i < len(distances) else 1.0

            # Apply file_path_prefix filter
            file_path = metadata.get("file_path", "")
            if file_path_prefix and not file_path.startswith(file_path_prefix):
                continue

            # Convert distance to similarity score (cosine: score = 1 - distance)
            score = 1.0 - distance

            output.append({
                "_id": entity_id,
                "name": metadata.get("name"),
                "file_path": file_path,
                "entity_type": metadata.get("entity_type"),
                "signature": metadata.get("signature"),
                "docstring": metadata.get("docstring"),
                "code": metadata.get("code"),
                "class_name": metadata.get("class_name"),
                "start_line": metadata.get("start_line"),
                "end_line": metadata.get("end_line"),
                "score": score,
            })

            if len(output) >= limit:
                break

        return output

    def count_documents(self, filter: dict[str, Any] | None = None) -> int:
        """Count documents in the collection.

        Args:
            filter: Optional filter criteria

        Returns:
            Document count
        """
        if filter:
            results = self._collection.get(where=filter)
            return len(results["ids"])
        return self._collection.count()

    def close(self) -> None:
        """Close the ChromaDB connection (no-op for PersistentClient)."""
        pass
