"""Parser module for extracting code entities using Tree-sitter."""

from .entities import (
    AccessModifier,
    AnyEntity,
    CallInfo,
    CallType,
    Class,
    CodeEntity,
    EmbeddableEntity,
    EntityType,
    File,
    Function,
    TypeDefinition,
    TypeParameter,
)
from .languages import (
    IGNORED_DIRECTORIES,
    LANGUAGE_CONFIGS,
    LanguageConfig,
    get_language_config,
    get_language_for_file,
    is_supported_file,
    should_ignore_path,
)
from .treesitter import TreeSitterParser

__all__ = [
    # Entities
    "AccessModifier",
    "AnyEntity",
    "CallInfo",
    "CallType",
    "Class",
    "CodeEntity",
    "EmbeddableEntity",
    "EntityType",
    "File",
    "Function",
    "TypeDefinition",
    "TypeParameter",
    # Languages
    "IGNORED_DIRECTORIES",
    "LANGUAGE_CONFIGS",
    "LanguageConfig",
    "get_language_config",
    "get_language_for_file",
    "is_supported_file",
    "should_ignore_path",
    # Parser
    "TreeSitterParser",
]
