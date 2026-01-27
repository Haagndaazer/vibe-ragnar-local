"""Embedding generator with pluggable backends for local embedding generation."""

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ..parser.entities import Class, EmbeddableEntity, Function, TypeDefinition

if TYPE_CHECKING:
    from ..config import Settings

logger = logging.getLogger(__name__)


class EmbeddingBackend(ABC):
    """Abstract base class for embedding backends."""

    @abstractmethod
    def encode(self, texts: list[str], is_query: bool = False) -> list[list[float]]:
        """Encode texts into embeddings.

        Args:
            texts: List of texts to encode
            is_query: Whether the texts are queries (vs documents)

        Returns:
            List of embedding vectors
        """
        pass


class SentenceTransformersBackend(EmbeddingBackend):
    """Embedding backend using sentence-transformers library."""

    DOCUMENT_PREFIX = "search_document: "
    QUERY_PREFIX = "search_query: "

    def __init__(self, model_name: str, dimensions: int | None = None):
        """Initialize the sentence-transformers backend.

        Args:
            model_name: Name of the model to use (e.g., 'nomic-ai/nomic-embed-text-v1.5')
            dimensions: Optional dimension truncation
        """
        from sentence_transformers import SentenceTransformer

        logger.info(f"Loading sentence-transformers model: {model_name}")
        self._model = SentenceTransformer(model_name, trust_remote_code=True)
        self._dimensions = dimensions
        logger.info(f"Model loaded successfully")

    def encode(self, texts: list[str], is_query: bool = False) -> list[list[float]]:
        """Encode texts into embeddings.

        Args:
            texts: List of texts to encode
            is_query: Whether the texts are queries (vs documents)

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # Add task-specific prefixes for nomic models
        prefix = self.QUERY_PREFIX if is_query else self.DOCUMENT_PREFIX
        prefixed = [prefix + t for t in texts]

        embeddings = self._model.encode(prefixed, convert_to_numpy=True)

        # Truncate to specified dimensions if set
        if self._dimensions:
            embeddings = embeddings[:, : self._dimensions]

        return embeddings.tolist()


class OllamaBackend(EmbeddingBackend):
    """Embedding backend using Ollama server."""

    def __init__(self, model: str, base_url: str):
        """Initialize the Ollama backend.

        Args:
            model: Name of the Ollama model to use
            base_url: Ollama server base URL
        """
        import ollama

        self._model = model
        self._client = ollama.Client(host=base_url)
        logger.info(f"Ollama client initialized with model: {model} at {base_url}")

    def encode(self, texts: list[str], is_query: bool = False) -> list[list[float]]:
        """Encode texts into embeddings.

        Args:
            texts: List of texts to encode
            is_query: Whether the texts are queries (ignored for Ollama)

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        embeddings = []
        for text in texts:
            response = self._client.embeddings(model=self._model, prompt=text)
            embeddings.append(response["embedding"])

        return embeddings


class EmbeddingGenerator:
    """Generate embeddings for code entities using pluggable backends."""

    # Batch limits
    MAX_BATCH_SIZE = 128

    def __init__(self, backend: EmbeddingBackend):
        """Initialize the embedding generator.

        Args:
            backend: Embedding backend to use
        """
        self._backend = backend

    @classmethod
    def from_config(cls, config: "Settings") -> "EmbeddingGenerator":
        """Create an EmbeddingGenerator from configuration.

        Args:
            config: Application settings

        Returns:
            Configured EmbeddingGenerator instance
        """
        if config.embedding_backend == "ollama":
            backend = OllamaBackend(
                model=config.ollama_model,
                base_url=config.ollama_base_url,
            )
        else:
            backend = SentenceTransformersBackend(
                model_name=config.embedding_model,
                dimensions=config.embedding_dimensions,
            )

        return cls(backend)

    def generate(self, text: str, input_type: str = "document") -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed
            input_type: Type of input ("document" or "query")

        Returns:
            Embedding vector as list of floats
        """
        is_query = input_type == "query"
        result = self._backend.encode([text], is_query=is_query)
        return result[0] if result else []

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

        is_query = input_type == "query"

        # Process in batches
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self.MAX_BATCH_SIZE):
            batch = texts[i : i + self.MAX_BATCH_SIZE]
            embeddings = self._backend.encode(batch, is_query=is_query)
            all_embeddings.extend(embeddings)

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
