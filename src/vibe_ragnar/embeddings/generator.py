"""Embedding generator using Voyage AI for code embeddings."""

import logging
from typing import Any

import voyageai

from ..parser.entities import Class, EmbeddableEntity, Function, TypeDefinition

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generate embeddings for code entities using Voyage AI."""

    # Voyage AI batch limits
    MAX_BATCH_SIZE = 128
    MAX_TOKENS_PER_BATCH = 120000  # Conservative estimate

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "voyage-code-3",
        dimensions: int | None = None,
    ):
        """Initialize the embedding generator.

        Args:
            api_key: Voyage AI API key (uses VOYAGE_API_KEY env var if not provided)
            model: Voyage AI model name
            dimensions: Output dimensions (None for model default)
        """
        self._client = voyageai.Client(api_key=api_key)
        self._model = model
        self._dimensions = dimensions

    def generate(self, text: str, input_type: str = "document") -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed
            input_type: Type of input ("document" or "query")

        Returns:
            Embedding vector as list of floats
        """
        result = self._client.embed(
            [text],
            model=self._model,
            input_type=input_type,
            output_dimension=self._dimensions,
        )
        return result.embeddings[0]

    def generate_batch(
        self, texts: list[str], input_type: str = "document"
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            input_type: Type of input ("document" or "query")

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # Process in batches
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self.MAX_BATCH_SIZE):
            batch = texts[i : i + self.MAX_BATCH_SIZE]
            result = self._client.embed(
                batch,
                model=self._model,
                input_type=input_type,
                output_dimension=self._dimensions,
            )
            all_embeddings.extend(result.embeddings)

        return all_embeddings

    def generate_query_embedding(self, query: str) -> list[float]:
        """Generate embedding for a search query.

        Args:
            query: Search query text

        Returns:
            Embedding vector
        """
        return self.generate(query, input_type="query")

    def prepare_entity_text(self, entity: EmbeddableEntity) -> str:
        """Prepare text representation of an entity for embedding.

        The text includes signature, docstring, and code to create
        a rich representation for semantic search.

        Args:
            entity: Code entity to prepare

        Returns:
            Text representation for embedding
        """
        if isinstance(entity, Function):
            return self._prepare_function_text(entity)
        elif isinstance(entity, Class):
            return self._prepare_class_text(entity)
        elif isinstance(entity, TypeDefinition):
            return self._prepare_type_text(entity)
        else:
            # Fallback for unknown entity types
            return f"{entity.name}\n{getattr(entity, 'code', '')}"

    def _prepare_function_text(self, func: Function) -> str:
        """Prepare text for a function entity."""
        parts = [
            f"File: {func.file_path}",
        ]

        # Add class context if method
        if func.class_name:
            parts.append(f"Class: {func.class_name}")
            parts.append(f"Method: {func.name}")
        else:
            parts.append(f"Function: {func.name}")

        # Add signature
        parts.append(f"Signature: {func.signature}")

        # Add docstring if available
        if func.docstring:
            parts.append(f"Description: {func.docstring}")

        # Add decorators if any
        if func.decorators:
            parts.append(f"Decorators: {', '.join(func.decorators)}")

        # Add the code
        parts.append(f"Code:\n{func.code}")

        return "\n".join(parts)

    def _prepare_class_text(self, cls: Class) -> str:
        """Prepare text for a class entity."""
        parts = [
            f"File: {cls.file_path}",
            f"Class: {cls.name}",
        ]

        # Add base classes
        if cls.bases:
            parts.append(f"Inherits: {', '.join(cls.bases)}")

        # Add docstring if available
        if cls.docstring:
            parts.append(f"Description: {cls.docstring}")

        # Add decorators if any
        if cls.decorators:
            parts.append(f"Decorators: {', '.join(cls.decorators)}")

        # Add method names
        if cls.methods:
            parts.append(f"Methods: {', '.join(cls.methods)}")

        # Add class definition (without full method bodies for brevity)
        parts.append(f"Definition:\n{cls.code[:2000]}")  # Truncate if very long

        return "\n".join(parts)

    def _prepare_type_text(self, type_def: TypeDefinition) -> str:
        """Prepare text for a type definition entity."""
        parts = [
            f"File: {type_def.file_path}",
            f"Type: {type_def.name}",
            f"Kind: {type_def.kind}",
        ]

        # Add docstring if available
        if type_def.docstring:
            parts.append(f"Description: {type_def.docstring}")

        # Add definition
        parts.append(f"Definition:\n{type_def.definition}")

        return "\n".join(parts)

    def embed_entities(
        self, entities: list[EmbeddableEntity]
    ) -> list[tuple[EmbeddableEntity, list[float]]]:
        """Generate embeddings for multiple entities.

        Args:
            entities: List of entities to embed

        Returns:
            List of (entity, embedding) tuples
        """
        if not entities:
            return []

        # Prepare texts
        texts = [self.prepare_entity_text(e) for e in entities]

        # Generate embeddings
        embeddings = self.generate_batch(texts)

        # Pair with entities
        return list(zip(entities, embeddings))
