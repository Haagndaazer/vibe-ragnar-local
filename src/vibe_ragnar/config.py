"""Configuration management for Vibe RAGnar."""

import logging
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required settings
    mongodb_uri: str = Field(
        ...,
        description="MongoDB Atlas connection string",
    )
    voyage_api_key: str = Field(
        ...,
        description="Voyage AI API key for embeddings",
    )

    # Optional settings with defaults
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
    embedding_model: str = Field(
        default="voyage-code-3",
        description="Voyage AI model for code embeddings",
    )
    embedding_dimensions: int = Field(
        default=1024,
        description="Embedding vector dimensions",
    )
    debounce_seconds: float = Field(
        default=5.0,
        description="Debounce delay for file watcher in seconds",
    )

    # MongoDB settings
    mongodb_database: str = Field(
        default="vibe_ragnar",
        description="MongoDB database name",
    )
    mongodb_collection: str = Field(
        default="code_embeddings",
        description="MongoDB collection name for embeddings",
    )

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


def setup_logging(level: str) -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
