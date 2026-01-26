"""Import resolver for resolving import statements to file entities."""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ResolvedImport:
    """Result of resolving an import statement."""

    original: str  # Original import string
    resolved_path: str | None  # Resolved file path (None if external)
    is_external: bool  # True if this is an external/third-party module
    is_relative: bool  # True if this was a relative import
    alias: str | None  # Import alias if any (import x as y)
    imported_names: list[str] = field(default_factory=list)  # Names imported (for star imports)


class BaseImportResolver(ABC):
    """Base class for language-specific import resolvers."""

    def __init__(self, repo_root: Path, known_files: set[str]):
        """Initialize the resolver.

        Args:
            repo_root: Root directory of the repository
            known_files: Set of known file paths (relative to repo root)
        """
        self.repo_root = repo_root
        self.known_files = known_files

    @abstractmethod
    def resolve(self, import_name: str, context_file: str) -> ResolvedImport:
        """Resolve an import to a file path.

        Args:
            import_name: The import string (e.g., "os", "./utils", "../models")
            context_file: The file containing the import (for relative imports)

        Returns:
            ResolvedImport with resolution details
        """
        pass

    def _find_file(self, possible_paths: list[str]) -> str | None:
        """Find the first existing file from a list of possible paths.

        Args:
            possible_paths: List of possible file paths to check

        Returns:
            The first matching file path or None
        """
        for path in possible_paths:
            # Normalize path
            path = os.path.normpath(path)
            if path in self.known_files:
                return path
            # Also check with different separators
            normalized = path.replace("\\", "/")
            if normalized in self.known_files:
                return normalized
        return None


class PythonImportResolver(BaseImportResolver):
    """Import resolver for Python."""

    def resolve(self, import_name: str, context_file: str) -> ResolvedImport:
        """Resolve a Python import.

        Handles:
        - Absolute imports: import os, from utils import foo
        - Relative imports: from . import foo, from ..models import Bar
        - Package imports: import package.submodule
        """
        # Check for relative import indicators
        is_relative = import_name.startswith(".")

        if is_relative:
            return self._resolve_relative(import_name, context_file)
        else:
            return self._resolve_absolute(import_name, context_file)

    def _resolve_relative(self, import_name: str, context_file: str) -> ResolvedImport:
        """Resolve a relative import."""
        # Count leading dots to determine level
        level = 0
        while level < len(import_name) and import_name[level] == ".":
            level += 1

        # Get the module path after dots
        module_part = import_name[level:]

        # Get the directory of the context file
        context_dir = Path(context_file).parent

        # Go up 'level - 1' directories (one dot = current package)
        for _ in range(level - 1):
            context_dir = context_dir.parent

        # Build the module path
        if module_part:
            module_path = str(context_dir / module_part.replace(".", "/"))
        else:
            module_path = str(context_dir)

        # Try to find the file
        possible_paths = [
            f"{module_path}.py",
            f"{module_path}/__init__.py",
        ]

        resolved_path = self._find_file(possible_paths)

        return ResolvedImport(
            original=import_name,
            resolved_path=resolved_path,
            is_external=resolved_path is None,
            is_relative=True,
            alias=None,
        )

    def _resolve_absolute(self, import_name: str, context_file: str) -> ResolvedImport:
        """Resolve an absolute import."""
        # Convert module path to file path
        module_path = import_name.replace(".", "/")

        # Standard library and third-party modules
        stdlib_modules = {
            "os", "sys", "re", "json", "logging", "pathlib", "typing",
            "collections", "itertools", "functools", "dataclasses", "abc",
            "hashlib", "datetime", "time", "unittest", "pytest", "asyncio",
            "enum", "copy", "io", "tempfile", "shutil", "glob", "subprocess",
        }

        # Check if it's a known stdlib module
        root_module = import_name.split(".")[0]
        if root_module in stdlib_modules:
            return ResolvedImport(
                original=import_name,
                resolved_path=None,
                is_external=True,
                is_relative=False,
                alias=None,
            )

        # Try to find the file in the repository
        possible_paths = [
            f"{module_path}.py",
            f"{module_path}/__init__.py",
            f"src/{module_path}.py",
            f"src/{module_path}/__init__.py",
        ]

        resolved_path = self._find_file(possible_paths)

        return ResolvedImport(
            original=import_name,
            resolved_path=resolved_path,
            is_external=resolved_path is None,
            is_relative=False,
            alias=None,
        )


class TypeScriptImportResolver(BaseImportResolver):
    """Import resolver for TypeScript/JavaScript."""

    def resolve(self, import_name: str, context_file: str) -> ResolvedImport:
        """Resolve a TypeScript/JavaScript import.

        Handles:
        - Relative imports: ./utils, ../models
        - Absolute imports: lodash, @types/node
        - Path aliases: @/components (not fully supported yet)
        """
        # Check for relative import
        is_relative = import_name.startswith("./") or import_name.startswith("../")

        if is_relative:
            return self._resolve_relative(import_name, context_file)
        else:
            return self._resolve_absolute(import_name)

    def _resolve_relative(self, import_name: str, context_file: str) -> ResolvedImport:
        """Resolve a relative import."""
        context_dir = Path(context_file).parent

        # Resolve the relative path
        resolved = os.path.normpath(str(context_dir / import_name))

        # Try different extensions
        possible_paths = [
            f"{resolved}.ts",
            f"{resolved}.tsx",
            f"{resolved}.js",
            f"{resolved}.jsx",
            f"{resolved}/index.ts",
            f"{resolved}/index.tsx",
            f"{resolved}/index.js",
            f"{resolved}/index.jsx",
        ]

        resolved_path = self._find_file(possible_paths)

        return ResolvedImport(
            original=import_name,
            resolved_path=resolved_path,
            is_external=resolved_path is None,
            is_relative=True,
            alias=None,
        )

    def _resolve_absolute(self, import_name: str) -> ResolvedImport:
        """Resolve an absolute (package) import."""
        # npm packages are external
        # Could try to resolve from node_modules but that's typically external
        return ResolvedImport(
            original=import_name,
            resolved_path=None,
            is_external=True,
            is_relative=False,
            alias=None,
        )


class GoImportResolver(BaseImportResolver):
    """Import resolver for Go."""

    def resolve(self, import_name: str, context_file: str) -> ResolvedImport:
        """Resolve a Go import.

        Handles:
        - Standard library: fmt, os, net/http
        - Internal packages: ./internal/utils
        - External packages: github.com/user/repo
        """
        # Clean up the import path (remove quotes)
        import_name = import_name.strip('"\'')

        # Standard library packages don't have dots in the first segment
        first_segment = import_name.split("/")[0]

        # Check if it looks like an external package (has domain-like structure)
        is_external = "." in first_segment or first_segment in {
            "fmt", "os", "io", "net", "sync", "context", "strings", "strconv",
            "encoding", "errors", "log", "path", "time", "testing", "flag",
            "bytes", "bufio", "sort", "math", "crypto", "database", "html",
            "regexp", "runtime", "reflect", "unsafe", "debug",
        }

        if is_external:
            return ResolvedImport(
                original=import_name,
                resolved_path=None,
                is_external=True,
                is_relative=False,
                alias=None,
            )

        # Try to resolve internal package
        possible_paths = [
            f"{import_name}.go",
            f"{import_name}/main.go",
        ]

        # Also try relative to common Go project structures
        for subdir in ["", "pkg/", "internal/", "cmd/"]:
            possible_paths.extend([
                f"{subdir}{import_name}.go",
                f"{subdir}{import_name}/main.go",
            ])

        resolved_path = self._find_file(possible_paths)

        return ResolvedImport(
            original=import_name,
            resolved_path=resolved_path,
            is_external=resolved_path is None,
            is_relative=False,
            alias=None,
        )


class RustImportResolver(BaseImportResolver):
    """Import resolver for Rust."""

    def resolve(self, import_name: str, context_file: str) -> ResolvedImport:
        """Resolve a Rust use statement.

        Handles:
        - Crate imports: use std::collections::HashMap
        - Self imports: use self::module
        - Super imports: use super::parent_module
        - External crates: use serde::Serialize
        """
        # Split the use path
        parts = import_name.split("::")

        if not parts:
            return ResolvedImport(
                original=import_name,
                resolved_path=None,
                is_external=True,
                is_relative=False,
                alias=None,
            )

        first_part = parts[0]

        # Standard library and common external crates
        external_crates = {
            "std", "core", "alloc",  # Rust stdlib
            "serde", "tokio", "async_std", "futures",  # Common crates
            "log", "env_logger", "tracing",
            "anyhow", "thiserror",
        }

        if first_part in external_crates:
            return ResolvedImport(
                original=import_name,
                resolved_path=None,
                is_external=True,
                is_relative=False,
                alias=None,
            )

        # Handle self/super/crate
        is_relative = first_part in {"self", "super", "crate"}

        if is_relative:
            return self._resolve_relative(import_name, context_file, parts)
        else:
            return self._resolve_absolute(import_name)

    def _resolve_relative(
        self, import_name: str, context_file: str, parts: list[str]
    ) -> ResolvedImport:
        """Resolve a relative Rust import."""
        context_dir = Path(context_file).parent

        # Handle self/super/crate prefixes
        module_parts = parts[:]
        if module_parts[0] == "self":
            module_parts = module_parts[1:]
        elif module_parts[0] == "super":
            context_dir = context_dir.parent
            module_parts = module_parts[1:]
        elif module_parts[0] == "crate":
            # Go to crate root (src/)
            context_dir = Path("src")
            module_parts = module_parts[1:]

        if not module_parts:
            # Just self or super without further path
            return ResolvedImport(
                original=import_name,
                resolved_path=None,
                is_external=True,
                is_relative=True,
                alias=None,
            )

        # Build the module path
        module_path = str(context_dir / "/".join(module_parts))

        possible_paths = [
            f"{module_path}.rs",
            f"{module_path}/mod.rs",
        ]

        resolved_path = self._find_file(possible_paths)

        return ResolvedImport(
            original=import_name,
            resolved_path=resolved_path,
            is_external=resolved_path is None,
            is_relative=True,
            alias=None,
        )

    def _resolve_absolute(self, import_name: str) -> ResolvedImport:
        """Resolve an absolute Rust import (external crate)."""
        return ResolvedImport(
            original=import_name,
            resolved_path=None,
            is_external=True,
            is_relative=False,
            alias=None,
        )


class JavaImportResolver(BaseImportResolver):
    """Import resolver for Java."""

    def resolve(self, import_name: str, context_file: str) -> ResolvedImport:
        """Resolve a Java import.

        Handles:
        - Standard library: java.util.List
        - Project classes: com.mycompany.MyClass
        """
        # Convert package path to file path
        file_path = import_name.replace(".", "/") + ".java"

        # Standard library packages
        if import_name.startswith(("java.", "javax.", "sun.")):
            return ResolvedImport(
                original=import_name,
                resolved_path=None,
                is_external=True,
                is_relative=False,
                alias=None,
            )

        # Try to find in common source directories
        possible_paths = [
            file_path,
            f"src/{file_path}",
            f"src/main/java/{file_path}",
            f"app/src/main/java/{file_path}",
        ]

        resolved_path = self._find_file(possible_paths)

        return ResolvedImport(
            original=import_name,
            resolved_path=resolved_path,
            is_external=resolved_path is None,
            is_relative=False,
            alias=None,
        )


class CImportResolver(BaseImportResolver):
    """Import resolver for C/C++."""

    def resolve(self, import_name: str, context_file: str) -> ResolvedImport:
        """Resolve a C/C++ include.

        Handles:
        - System includes: <stdio.h>
        - Local includes: "myheader.h"
        """
        # Clean up the include path
        import_name = import_name.strip('"\'<>')

        # Check if it's a system include (angle brackets were used)
        is_system = not ('"' in import_name or import_name.endswith(".h"))

        if is_system:
            return ResolvedImport(
                original=import_name,
                resolved_path=None,
                is_external=True,
                is_relative=False,
                alias=None,
            )

        # Try to resolve local include
        context_dir = Path(context_file).parent

        possible_paths = [
            str(context_dir / import_name),
            import_name,
            f"include/{import_name}",
            f"src/{import_name}",
        ]

        resolved_path = self._find_file(possible_paths)

        return ResolvedImport(
            original=import_name,
            resolved_path=resolved_path,
            is_external=resolved_path is None,
            is_relative=True,
            alias=None,
        )


class ImportResolver:
    """Main import resolver that delegates to language-specific resolvers."""

    def __init__(self, repo_root: Path):
        """Initialize the import resolver.

        Args:
            repo_root: Root directory of the repository
        """
        self.repo_root = repo_root
        self.known_files: set[str] = set()
        self._resolvers: dict[str, BaseImportResolver] = {}

    def set_known_files(self, files: set[str]) -> None:
        """Set the known files for resolution.

        Args:
            files: Set of known file paths (relative to repo root)
        """
        self.known_files = files
        # Recreate resolvers with updated file set
        self._resolvers = {
            "python": PythonImportResolver(self.repo_root, self.known_files),
            "typescript": TypeScriptImportResolver(self.repo_root, self.known_files),
            "javascript": TypeScriptImportResolver(self.repo_root, self.known_files),
            "go": GoImportResolver(self.repo_root, self.known_files),
            "rust": RustImportResolver(self.repo_root, self.known_files),
            "java": JavaImportResolver(self.repo_root, self.known_files),
            "c": CImportResolver(self.repo_root, self.known_files),
            "cpp": CImportResolver(self.repo_root, self.known_files),
        }

    def resolve(
        self, import_name: str, context_file: str, language: str
    ) -> ResolvedImport:
        """Resolve an import for a specific language.

        Args:
            import_name: The import string
            context_file: The file containing the import
            language: Programming language

        Returns:
            ResolvedImport with resolution details
        """
        resolver = self._resolvers.get(language)
        if resolver:
            return resolver.resolve(import_name, context_file)

        # Default: treat as external
        return ResolvedImport(
            original=import_name,
            resolved_path=None,
            is_external=True,
            is_relative=False,
            alias=None,
        )
