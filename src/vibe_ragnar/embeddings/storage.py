"""MongoDB Atlas storage for vector embeddings."""

import logging
from datetime import datetime
from typing import Any

from pymongo import MongoClient, UpdateOne
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.operations import SearchIndexModel

logger = logging.getLogger(__name__)


class MongoDBStorage:
    """Storage for code embeddings in MongoDB Atlas with vector search."""

    def __init__(
        self,
        uri: str,
        database: str = "vibe_ragnar",
        collection: str = "code_embeddings",
    ):
        """Initialize MongoDB connection.

        Args:
            uri: MongoDB connection URI
            database: Database name
            collection: Collection name for embeddings
        """
        self._client = MongoClient(uri)
        self._db: Database = self._client[database]
        self._collection: Collection = self._db[collection]
        self._index_name = "vector_index"

    def ensure_vector_index(self, dimensions: int = 1024) -> None:
        """Create the vector search index if it doesn't exist.

        Args:
            dimensions: Embedding vector dimensions
        """
        # Check if index already exists
        existing_indexes = list(self._collection.list_search_indexes())
        for idx in existing_indexes:
            if idx.get("name") == self._index_name:
                logger.info(f"Vector index '{self._index_name}' already exists")
                return

        # Create the vector search index
        index_definition = {
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": dimensions,
                    "similarity": "cosine",
                },
                {
                    "type": "filter",
                    "path": "repo",
                },
                {
                    "type": "filter",
                    "path": "entity_type",
                },
                {
                    "type": "filter",
                    "path": "file_path",
                },
            ]
        }

        try:
            search_index = SearchIndexModel(
                definition=index_definition,
                name=self._index_name,
                type="vectorSearch",
            )
            self._collection.create_search_index(search_index)
            logger.info(f"Created vector index '{self._index_name}'")
        except Exception as e:
            # Index might already exist or Atlas might not support vector search
            logger.warning(f"Could not create vector index: {e}")

    def ensure_standard_indexes(self) -> None:
        """Create standard indexes for efficient querying."""
        # Index for content hash lookups
        self._collection.create_index("content_hash")
        # Index for file-based queries
        self._collection.create_index([("repo", 1), ("file_path", 1)])
        # Index for entity type filtering
        self._collection.create_index([("repo", 1), ("entity_type", 1)])
        logger.info("Standard indexes created")

    def upsert_embedding(
        self,
        entity_id: str,
        embedding: list[float],
        metadata: dict[str, Any],
    ) -> None:
        """Insert or update an embedding.

        Args:
            entity_id: Unique entity ID (used as _id)
            embedding: Embedding vector
            metadata: Entity metadata (content_hash, entity_type, file_path, etc.)
        """
        document = {
            "_id": entity_id,
            "embedding": embedding,
            "content_hash": metadata.get("content_hash"),
            "repo": metadata.get("repo"),
            "entity_type": metadata.get("entity_type"),
            "file_path": metadata.get("file_path"),
            "name": metadata.get("name"),
            "signature": metadata.get("signature"),
            "docstring": metadata.get("docstring"),
            "code": metadata.get("code"),
            "class_name": metadata.get("class_name"),
            "start_line": metadata.get("start_line"),
            "end_line": metadata.get("end_line"),
            "updated_at": datetime.utcnow(),
        }

        self._collection.update_one(
            {"_id": entity_id},
            {"$set": document},
            upsert=True,
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

        operations = []
        now = datetime.utcnow()

        for entity_id, embedding, metadata in items:
            document = {
                "_id": entity_id,
                "embedding": embedding,
                "content_hash": metadata.get("content_hash"),
                "repo": metadata.get("repo"),
                "entity_type": metadata.get("entity_type"),
                "file_path": metadata.get("file_path"),
                "name": metadata.get("name"),
                "signature": metadata.get("signature"),
                "docstring": metadata.get("docstring"),
                "code": metadata.get("code"),
                "class_name": metadata.get("class_name"),
                "start_line": metadata.get("start_line"),
                "end_line": metadata.get("end_line"),
                "updated_at": now,
            }

            operations.append(
                UpdateOne({"_id": entity_id}, {"$set": document}, upsert=True)
            )

        if operations:
            result = self._collection.bulk_write(operations)
            return result.upserted_count + result.modified_count

        return 0

    def delete_embedding(self, entity_id: str) -> bool:
        """Delete an embedding by entity ID.

        Args:
            entity_id: Entity ID to delete

        Returns:
            True if deleted, False if not found
        """
        result = self._collection.delete_one({"_id": entity_id})
        return result.deleted_count > 0

    def delete_by_file(self, repo: str, file_path: str) -> int:
        """Delete all embeddings for a specific file.

        Args:
            repo: Repository name
            file_path: File path

        Returns:
            Number of deleted documents
        """
        result = self._collection.delete_many({
            "repo": repo,
            "file_path": file_path,
        })
        return result.deleted_count

    def delete_by_repo(self, repo: str) -> int:
        """Delete all embeddings for a repository.

        Args:
            repo: Repository name

        Returns:
            Number of deleted documents
        """
        result = self._collection.delete_many({"repo": repo})
        return result.deleted_count

    def get_by_id(self, entity_id: str) -> dict[str, Any] | None:
        """Get an embedding document by ID.

        Args:
            entity_id: Entity ID

        Returns:
            Document or None if not found
        """
        return self._collection.find_one({"_id": entity_id})

    def get_content_hashes(self, repo: str) -> dict[str, str]:
        """Get all entity IDs and their content hashes for a repository.

        Args:
            repo: Repository name

        Returns:
            Dictionary mapping entity_id to content_hash
        """
        cursor = self._collection.find(
            {"repo": repo},
            {"_id": 1, "content_hash": 1},
        )
        return {doc["_id"]: doc.get("content_hash", "") for doc in cursor}

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
        # Build filter
        filter_conditions = {}
        if repo:
            filter_conditions["repo"] = repo
        if entity_type:
            filter_conditions["entity_type"] = entity_type

        # Build aggregation pipeline
        pipeline = [
            {
                "$vectorSearch": {
                    "index": self._index_name,
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": limit * 10,  # Over-fetch for filtering
                    "limit": limit * 2 if file_path_prefix else limit,
                    "filter": filter_conditions if filter_conditions else None,
                }
            },
            {
                "$project": {
                    "_id": 1,
                    "name": 1,
                    "file_path": 1,
                    "entity_type": 1,
                    "signature": 1,
                    "docstring": 1,
                    "code": 1,
                    "class_name": 1,
                    "start_line": 1,
                    "end_line": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]

        # Remove None filter
        if not filter_conditions:
            del pipeline[0]["$vectorSearch"]["filter"]

        try:
            results = list(self._collection.aggregate(pipeline))

            # Apply file_path_prefix filter if specified
            if file_path_prefix:
                results = [
                    r for r in results
                    if r.get("file_path", "").startswith(file_path_prefix)
                ][:limit]

            return results
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            # Fallback to regular search if vector search not available
            return self._fallback_search(repo, entity_type, file_path_prefix, limit)

    def _fallback_search(
        self,
        repo: str | None,
        entity_type: str | None,
        file_path_prefix: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fallback search when vector search is not available."""
        query: dict[str, Any] = {}
        if repo:
            query["repo"] = repo
        if entity_type:
            query["entity_type"] = entity_type
        if file_path_prefix:
            query["file_path"] = {"$regex": f"^{file_path_prefix}"}

        cursor = self._collection.find(
            query,
            {
                "_id": 1,
                "name": 1,
                "file_path": 1,
                "entity_type": 1,
                "signature": 1,
                "docstring": 1,
                "start_line": 1,
                "end_line": 1,
            },
        ).limit(limit)

        return list(cursor)

    def count_documents(self, filter: dict[str, Any] | None = None) -> int:
        """Count documents in the collection.

        Args:
            filter: Optional filter criteria

        Returns:
            Document count
        """
        return self._collection.count_documents(filter or {})

    def close(self) -> None:
        """Close the MongoDB connection."""
        self._client.close()
