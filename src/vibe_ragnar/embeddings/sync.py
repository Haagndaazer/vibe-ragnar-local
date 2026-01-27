"""Synchronization logic for incremental embedding updates."""

import logging
from dataclasses import dataclass, field
from typing import Any

from ..parser.entities import (
    AnyEntity,
    Class,
    EmbeddableEntity,
    Function,
    TypeDefinition,
)
from .generator import EmbeddingGenerator
from .storage import ChromaDBStorage

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of a sync operation."""

    added: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_processed(self) -> int:
        """Total number of entities processed."""
        return self.added + self.updated + self.deleted + self.skipped

    def __str__(self) -> str:
        return (
            f"SyncResult(added={self.added}, updated={self.updated}, "
            f"deleted={self.deleted}, skipped={self.skipped}, errors={len(self.errors)})"
        )


class EmbeddingSync:
    """Synchronize embeddings between parsed entities and ChromaDB storage."""

    BATCH_SIZE = 32  # Batch size for embedding generation

    def __init__(
        self,
        generator: EmbeddingGenerator,
        storage: ChromaDBStorage,
        repo_name: str,
    ):
        """Initialize the sync manager.

        Args:
            generator: Embedding generator instance
            storage: MongoDB storage instance
            repo_name: Name of the repository
        """
        self._generator = generator
        self._storage = storage
        self._repo_name = repo_name

    def sync_entities(self, entities: list[AnyEntity]) -> SyncResult:
        """Synchronize entities with the embedding storage.

        This performs incremental updates:
        - New entities are added
        - Changed entities (different content_hash) are updated
        - Unchanged entities are skipped
        - Deleted entities are removed

        Args:
            entities: List of entities from the parser

        Returns:
            SyncResult with counts and any errors
        """
        result = SyncResult()

        # Filter to only embeddable entities (not Files)
        embeddable = [e for e in entities if self._is_embeddable(e)]
        embeddable_ids = {e.id for e in embeddable}

        logger.info(f"Syncing {len(embeddable)} embeddable entities")

        # Get existing content hashes from storage
        existing_hashes = self._storage.get_content_hashes(self._repo_name)
        existing_ids = set(existing_hashes.keys())

        # Categorize entities
        to_embed: list[EmbeddableEntity] = []
        to_skip: list[str] = []

        for entity in embeddable:
            entity_embeddable = self._cast_embeddable(entity)
            if entity_embeddable is None:
                continue

            existing_hash = existing_hashes.get(entity.id)

            if existing_hash is None:
                # New entity
                to_embed.append(entity_embeddable)
                result.added += 1
            elif existing_hash != entity_embeddable.content_hash:
                # Changed entity
                to_embed.append(entity_embeddable)
                result.updated += 1
            else:
                # Unchanged
                to_skip.append(entity.id)
                result.skipped += 1

        # Find entities to delete (in storage but not in parsed entities)
        # Only consider entities for files that were actually parsed
        parsed_files = {e.file_path for e in entities}
        to_delete = [
            eid for eid in existing_ids
            if eid not in embeddable_ids
            and self._get_file_from_id(eid) in parsed_files
        ]

        logger.info(
            f"To embed: {len(to_embed)}, to skip: {len(to_skip)}, to delete: {len(to_delete)}"
        )

        # Delete removed entities
        for entity_id in to_delete:
            try:
                self._storage.delete_embedding(entity_id)
                result.deleted += 1
            except Exception as e:
                result.errors.append(f"Failed to delete {entity_id}: {e}")

        # Generate and store embeddings in batches
        for i in range(0, len(to_embed), self.BATCH_SIZE):
            batch = to_embed[i : i + self.BATCH_SIZE]
            try:
                self._process_batch(batch)
            except Exception as e:
                for entity in batch:
                    result.errors.append(f"Failed to embed {entity.id}: {e}")
                # Adjust counts since batch failed
                for entity in batch:
                    if entity.id in existing_ids:
                        result.updated -= 1
                    else:
                        result.added -= 1

        logger.info(f"Sync completed: {result}")
        return result

    def sync_file(
        self,
        file_path: str,
        entities: list[AnyEntity],
    ) -> SyncResult:
        """Synchronize entities for a specific file.

        Args:
            file_path: Path of the file that changed
            entities: Entities parsed from the file

        Returns:
            SyncResult with counts
        """
        result = SyncResult()

        # Filter to embeddable entities
        embeddable = [e for e in entities if self._is_embeddable(e)]

        # Get existing entities for this file
        existing = self._storage.get_content_hashes(self._repo_name)
        existing_in_file = {
            eid: h for eid, h in existing.items()
            if self._get_file_from_id(eid) == file_path
        }

        # Categorize
        to_embed: list[EmbeddableEntity] = []
        current_ids: set[str] = set()

        for entity in embeddable:
            entity_embeddable = self._cast_embeddable(entity)
            if entity_embeddable is None:
                continue

            current_ids.add(entity.id)
            existing_hash = existing_in_file.get(entity.id)

            if existing_hash is None:
                to_embed.append(entity_embeddable)
                result.added += 1
            elif existing_hash != entity_embeddable.content_hash:
                to_embed.append(entity_embeddable)
                result.updated += 1
            else:
                result.skipped += 1

        # Delete entities that no longer exist in this file
        to_delete = set(existing_in_file.keys()) - current_ids
        for entity_id in to_delete:
            try:
                self._storage.delete_embedding(entity_id)
                result.deleted += 1
            except Exception as e:
                result.errors.append(f"Failed to delete {entity_id}: {e}")

        # Generate and store embeddings
        for i in range(0, len(to_embed), self.BATCH_SIZE):
            batch = to_embed[i : i + self.BATCH_SIZE]
            try:
                self._process_batch(batch)
            except Exception as e:
                for entity in batch:
                    result.errors.append(f"Failed to embed {entity.id}: {e}")

        logger.debug(f"File sync for {file_path}: {result}")
        return result

    def delete_file(self, file_path: str) -> int:
        """Delete all embeddings for a file.

        Args:
            file_path: Path of the file to remove

        Returns:
            Number of deleted embeddings
        """
        return self._storage.delete_by_file(self._repo_name, file_path)

    def full_reindex(self, entities: list[AnyEntity]) -> SyncResult:
        """Perform a full reindex, deleting all existing embeddings first.

        Args:
            entities: All entities to index

        Returns:
            SyncResult with counts
        """
        # Delete all existing embeddings for this repo
        deleted = self._storage.delete_by_repo(self._repo_name)
        logger.info(f"Deleted {deleted} existing embeddings for full reindex")

        # Sync all entities
        result = self.sync_entities(entities)
        result.deleted = deleted

        return result

    def _process_batch(self, batch: list[EmbeddableEntity]) -> None:
        """Process a batch of entities: generate embeddings and store.

        Args:
            batch: List of entities to process
        """
        if not batch:
            return

        # Generate embeddings
        entity_embeddings = self._generator.embed_entities(batch)

        # Prepare for bulk upsert
        items: list[tuple[str, list[float], dict[str, Any]]] = []
        for entity, embedding in entity_embeddings:
            metadata = self._entity_to_metadata(entity)
            items.append((entity.id, embedding, metadata))

        # Bulk upsert
        self._storage.bulk_upsert(items)

    def _entity_to_metadata(self, entity: EmbeddableEntity) -> dict[str, Any]:
        """Convert entity to metadata dictionary for storage.

        Args:
            entity: Entity to convert

        Returns:
            Metadata dictionary
        """
        metadata: dict[str, Any] = {
            "repo": self._repo_name,
            "entity_type": entity.entity_type.value,
            "file_path": entity.file_path,
            "name": entity.name,
            "content_hash": entity.content_hash,
            "start_line": entity.start_line,
            "end_line": entity.end_line,
        }

        if isinstance(entity, Function):
            metadata["signature"] = entity.signature
            metadata["docstring"] = entity.docstring
            metadata["code"] = entity.code
            metadata["class_name"] = entity.class_name

        elif isinstance(entity, Class):
            metadata["docstring"] = entity.docstring
            metadata["code"] = entity.code[:5000]  # Truncate very long class definitions

        elif isinstance(entity, TypeDefinition):
            metadata["docstring"] = entity.docstring
            metadata["code"] = entity.definition

        return metadata

    def _is_embeddable(self, entity: AnyEntity) -> bool:
        """Check if an entity should be embedded.

        Files are NOT embedded, only functions, classes, and types.

        Args:
            entity: Entity to check

        Returns:
            True if entity should be embedded
        """
        return isinstance(entity, (Function, Class, TypeDefinition))

    def _cast_embeddable(self, entity: AnyEntity) -> EmbeddableEntity | None:
        """Cast an entity to EmbeddableEntity if possible.

        Args:
            entity: Entity to cast

        Returns:
            EmbeddableEntity or None if not embeddable
        """
        if isinstance(entity, (Function, Class, TypeDefinition)):
            return entity
        return None

    def _get_file_from_id(self, entity_id: str) -> str:
        """Extract file path from entity ID.

        Entity ID format: repo:file_path:entity_path

        Args:
            entity_id: Entity ID

        Returns:
            File path portion of the ID
        """
        parts = entity_id.split(":")
        if len(parts) >= 2:
            # Return everything between repo and entity_path
            return ":".join(parts[1:-1]) if len(parts) > 2 else parts[1]
        return ""
