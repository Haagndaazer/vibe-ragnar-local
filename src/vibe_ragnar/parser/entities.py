"""Pydantic models for code entities extracted from source files."""

import hashlib
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, computed_field


class EntityType(str, Enum):
    """Types of code entities that can be indexed."""

    FUNCTION = "function"
    CLASS = "class"
    FILE = "file"
    TYPE = "type"


class CodeEntity(BaseModel):
    """Base class for all code entities."""

    repo: str = Field(..., description="Repository name")
    file_path: str = Field(..., description="Path to file relative to repository root")
    name: str = Field(..., description="Name of the entity")
    start_line: int = Field(..., description="Starting line number (1-indexed)")
    end_line: int = Field(..., description="Ending line number (1-indexed)")

    @computed_field
    @property
    def id(self) -> str:
        """Generate unique entity ID in format repo:file_path:entity_path."""
        return f"{self.repo}:{self.file_path}:{self.entity_path}"

    @property
    def entity_path(self) -> str:
        """Entity path within the file (to be overridden by subclasses)."""
        return self.name

    @property
    def entity_type(self) -> EntityType:
        """Type of this entity (to be overridden by subclasses)."""
        raise NotImplementedError


class Function(CodeEntity):
    """Represents a function or method in the codebase."""

    signature: str = Field(..., description="Function signature with parameters and types")
    docstring: str | None = Field(default=None, description="Function docstring")
    code: str = Field(..., description="Full function code")
    class_name: str | None = Field(
        default=None, description="Class name if this is a method, None for standalone functions"
    )
    decorators: list[str] = Field(default_factory=list, description="List of decorator names")
    calls: list[str] = Field(
        default_factory=list, description="List of function/method names called within this function"
    )
    is_async: bool = Field(default=False, description="Whether the function is async")

    @computed_field
    @property
    def content_hash(self) -> str:
        """SHA256 hash of the function code for change detection."""
        return hashlib.sha256(self.code.encode()).hexdigest()

    @property
    def entity_path(self) -> str:
        """Entity path: ClassName.method_name or function_name."""
        if self.class_name:
            return f"{self.class_name}.{self.name}"
        return self.name

    @property
    def entity_type(self) -> EntityType:
        return EntityType.FUNCTION


class Class(CodeEntity):
    """Represents a class definition in the codebase."""

    docstring: str | None = Field(default=None, description="Class docstring")
    code: str = Field(..., description="Full class definition code (without method bodies)")
    bases: list[str] = Field(default_factory=list, description="List of base class names")
    decorators: list[str] = Field(default_factory=list, description="List of decorator names")
    methods: list[str] = Field(default_factory=list, description="List of method names")

    @computed_field
    @property
    def content_hash(self) -> str:
        """SHA256 hash of the class definition for change detection."""
        # Hash the class signature (name + bases + decorators), not the full code
        # This way renaming a method doesn't change the class hash
        signature = f"{self.name}:{','.join(sorted(self.bases))}:{','.join(sorted(self.decorators))}"
        return hashlib.sha256(signature.encode()).hexdigest()

    @property
    def entity_type(self) -> EntityType:
        return EntityType.CLASS


class File(CodeEntity):
    """Represents a source file in the codebase.

    Note: Files are used ONLY in the graph for tracking dependencies (IMPORTS, DEFINES).
    Embeddings are NOT created for files.
    """

    language: str = Field(..., description="Programming language of the file")
    imports: list[str] = Field(default_factory=list, description="List of imported modules/files")
    defines: list[str] = Field(
        default_factory=list, description="List of entity IDs defined in this file"
    )

    @computed_field
    @property
    def id(self) -> str:
        """File ID is simpler: repo:file_path."""
        return f"{self.repo}:{self.file_path}"

    @property
    def entity_path(self) -> str:
        """Files don't have an additional entity path."""
        return ""

    @property
    def entity_type(self) -> EntityType:
        return EntityType.FILE


class TypeDefinition(CodeEntity):
    """Represents a type or interface definition (TypeScript/Go).

    Used for TypeScript interfaces, type aliases, Go type definitions, etc.
    """

    definition: str = Field(..., description="Full type definition code")
    docstring: str | None = Field(default=None, description="Type documentation")
    kind: Literal["interface", "type", "struct", "enum"] = Field(
        ..., description="Kind of type definition"
    )

    @computed_field
    @property
    def content_hash(self) -> str:
        """SHA256 hash of the type definition for change detection."""
        return hashlib.sha256(self.definition.encode()).hexdigest()

    @property
    def entity_type(self) -> EntityType:
        return EntityType.TYPE


# Type alias for any embeddable entity (not File)
EmbeddableEntity = Function | Class | TypeDefinition

# Type alias for any code entity
AnyEntity = Function | Class | File | TypeDefinition
