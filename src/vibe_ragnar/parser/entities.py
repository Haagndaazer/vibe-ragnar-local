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


class CallType(str, Enum):
    """Types of function/method calls."""

    FUNCTION = "function"  # Regular function call: foo()
    METHOD = "method"  # Method call: obj.method()
    CONSTRUCTOR = "constructor"  # Constructor call: new Foo() or Foo()
    DECORATOR = "decorator"  # Decorator: @decorator
    STATIC = "static"  # Static method: Class.method()


class AccessModifier(str, Enum):
    """Access modifiers for functions, classes, and fields."""

    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    INTERNAL = "internal"  # C#, Kotlin
    PACKAGE = "package"  # Java default


class TypeParameter(BaseModel):
    """Represents a generic type parameter.

    Examples:
    - TypeScript: function foo<T extends Base>() -> TypeParameter(name="T", constraint="Base")
    - Java: class Box<T> -> TypeParameter(name="T")
    - Rust: fn foo<T: Clone>() -> TypeParameter(name="T", constraint="Clone")
    """

    name: str = Field(..., description="Name of the type parameter (e.g., 'T', 'K', 'V')")
    constraint: str | None = Field(
        default=None, description="Type constraint/bound (e.g., 'extends Base', ': Clone')"
    )
    default: str | None = Field(
        default=None, description="Default type if not specified"
    )
    variance: Literal["in", "out", "inout"] | None = Field(
        default=None, description="Variance annotation (Kotlin: in/out)"
    )


class CallInfo(BaseModel):
    """Detailed information about a function/method call."""

    name: str = Field(..., description="Name of the called function/method")
    call_type: CallType = Field(
        default=CallType.FUNCTION, description="Type of call"
    )
    receiver: str | None = Field(
        default=None,
        description="Receiver object for method calls (e.g., 'obj' in obj.method())",
    )
    is_nested: bool = Field(
        default=False,
        description="Whether this call is nested inside another call",
    )
    is_chained: bool = Field(
        default=False,
        description="Whether this is part of a method chain",
    )
    line: int | None = Field(
        default=None,
        description="Line number where the call occurs",
    )

    @property
    def qualified_name(self) -> str:
        """Get qualified name for method calls."""
        if self.receiver and self.call_type in (CallType.METHOD, CallType.STATIC):
            return f"{self.receiver}.{self.name}"
        return self.name


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
    call_details: list[CallInfo] = Field(
        default_factory=list,
        description="Detailed information about each call in this function",
    )
    is_async: bool = Field(default=False, description="Whether the function is async")
    is_constructor: bool = Field(
        default=False,
        description="Whether this function is a constructor",
    )
    # New fields for Phase 3
    access_modifier: AccessModifier | None = Field(
        default=None,
        description="Access modifier (public/private/protected)",
    )
    is_static: bool = Field(
        default=False,
        description="Whether the function is static",
    )
    is_abstract: bool = Field(
        default=False,
        description="Whether the function is abstract (no implementation)",
    )
    type_parameters: list[TypeParameter] = Field(
        default_factory=list,
        description="Generic type parameters for the function",
    )
    return_type: str | None = Field(
        default=None,
        description="Return type annotation if present",
    )

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
    # New fields for Phase 3
    access_modifier: AccessModifier | None = Field(
        default=None,
        description="Access modifier (public/private/protected)",
    )
    is_abstract: bool = Field(
        default=False,
        description="Whether the class is abstract",
    )
    is_interface: bool = Field(
        default=False,
        description="Whether this is an interface (TypeScript, Java)",
    )
    type_parameters: list[TypeParameter] = Field(
        default_factory=list,
        description="Generic type parameters for the class",
    )
    implements: list[str] = Field(
        default_factory=list,
        description="List of interfaces this class implements (Java)",
    )

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
