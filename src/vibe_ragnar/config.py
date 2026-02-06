"""Configuration management for Vibe RAGnar."""

import logging
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Repository settings
    repo_path: Path = Field(
        default_factory=Path.cwd,
        description="Path to the repository to index",
    )
    repo_name: str | None = Field(
        default=None,
        description="Name of the repository (defaults to directory name)",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )

    # Local storage settings
    persist_dir: str = Field(
        default=".embeddings",
        description="Directory for local storage (relative to repo_path)",
    )

    # Embedding backend settings
    embedding_backend: Literal["sentence-transformers", "ollama"] = Field(
        default="sentence-transformers",
        description="Embedding backend to use",
    )
    embedding_model: str = Field(
        default="nomic-ai/nomic-embed-text-v1.5",
        description="Model name for sentence-transformers backend",
    )
    embedding_dimensions: int = Field(
        default=768,
        description="Embedding vector dimensions",
    )

    # Ollama settings
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama server base URL",
    )
    ollama_model: str = Field(
        default="nomic-embed-text",
        description="Ollama model name for embeddings",
    )

    # ChromaDB settings
    chromadb_collection: str = Field(
        default="code_embeddings",
        description="ChromaDB collection name",
    )

    # Watcher settings
    debounce_seconds: float = Field(
        default=5.0,
        description="Debounce delay for file watcher in seconds",
    )

    # Directory filtering
    include_dirs: list[str] = Field(
        default_factory=list,
        description="Directories to include even if normally ignored (comma-separated)",
    )

    @field_validator("include_dirs", mode="before")
    @classmethod
    def parse_include_dirs(cls, v: str | list[str]) -> list[str]:
        """Parse comma-separated string into list."""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [d.strip() for d in v.split(",") if d.strip()]
        return v

    @field_validator("repo_path", mode="before")
    @classmethod
    def validate_repo_path(cls, v: str | Path) -> Path:
        """Convert string to Path and validate it exists."""
        path = Path(v) if isinstance(v, str) else v
        if not path.exists():
            raise ValueError(f"Repository path does not exist: {path}")
        if not path.is_dir():
            raise ValueError(f"Repository path is not a directory: {path}")
        return path.resolve()

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper_v = v.upper()
        if upper_v not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return upper_v

    @property
    def effective_repo_name(self) -> str:
        """Get the repository name, defaulting to directory name."""
        return self.repo_name or self.repo_path.name

    @property
    def chromadb_path(self) -> Path:
        """Get the ChromaDB storage path."""
        return self.repo_path / self.persist_dir / "chromadb"

    @property
    def graph_pickle_path(self) -> Path:
        """Get the graph pickle storage path."""
        return self.repo_path / self.persist_dir / "graph.pickle"


def setup_logging(level: str) -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
