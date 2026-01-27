"""Embeddings module for vector storage and semantic search."""

from .generator import (
    EmbeddingBackend,
    EmbeddingGenerator,
    OllamaBackend,
    SentenceTransformersBackend,
)
from .storage import ChromaDBStorage
from .sync import EmbeddingSync, SyncResult

__all__ = [
    "ChromaDBStorage",
    "EmbeddingBackend",
    "EmbeddingGenerator",
    "EmbeddingSync",
    "OllamaBackend",
    "SentenceTransformersBackend",
    "SyncResult",
]
