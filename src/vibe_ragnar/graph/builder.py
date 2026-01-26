"""Graph builder for constructing code dependency graphs from parsed entities."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..parser.entities import AnyEntity, Class, File, Function, TypeDefinition
from .import_resolver import ImportResolver
from .storage import EdgeType, GraphStorage

logger = logging.getLogger(__name__)


@dataclass
class ScopedSymbolTable:
    """Hierarchical symbol table with file-based scoping.

    Supports:
    - File-local symbols (functions/classes defined in a file)
    - Qualified names for methods (ClassName.method)
    - Global scope for exported/top-level symbols
    """

    # Global scope: simple name -> entity_id (for cross-file resolution)
    global_scope: dict[str, str] = field(default_factory=dict)

    # File-local scope: file_path -> (name -> entity_id)
    file_scopes: dict[str, dict[str, str]] = field(default_factory=dict)

    # Qualified names: qualified_name -> entity_id (e.g., "ClassName.method")
    qualified_names: dict[str, str] = field(default_factory=dict)

    # Reverse mapping for cleanup: entity_id -> list of registered names
    entity_to_names: dict[str, list[tuple[str, str]]] = field(default_factory=dict)

    def register(
        self,
        entity_id: str,
        name: str,
        file_path: str,
        qualified_name: str | None = None,
        is_exported: bool = True,
    ) -> None:
        """Register a symbol in the appropriate scopes.

        Args:
            entity_id: Unique entity identifier
            name: Simple name of the symbol
            file_path: File where the symbol is defined
            qualified_name: Qualified name (e.g., ClassName.method)
            is_exported: Whether the symbol is visible globally
        """
        registered_names: list[tuple[str, str]] = []

        # Always register in file-local scope
        if file_path not in self.file_scopes:
            self.file_scopes[file_path] = {}
        self.file_scopes[file_path][name] = entity_id
        registered_names.append(("file", name))

        # Register qualified name if provided
        if qualified_name:
            self.qualified_names[qualified_name] = entity_id
            registered_names.append(("qualified", qualified_name))
            # Also register in file scope with qualified name
            self.file_scopes[file_path][qualified_name] = entity_id
            registered_names.append(("file", qualified_name))

        # Register in global scope if exported
        if is_exported:
            self.global_scope[name] = entity_id
            registered_names.append(("global", name))
            if qualified_name:
                self.global_scope[qualified_name] = entity_id
                registered_names.append(("global", qualified_name))

        # Track for cleanup
        self.entity_to_names[entity_id] = registered_names

    def resolve(
        self,
        name: str,
        context_file: str | None = None,
    ) -> str | None:
        """Resolve a symbol name to an entity ID.

        Resolution order:
        1. Qualified names (ClassName.method)
        2. File-local scope (same file)
        3. Global scope

        Args:
            name: Symbol name to resolve
            context_file: File path for context (for local resolution)

        Returns:
            Entity ID or None if not found
        """
        # Try qualified names first (for method calls like ClassName.method)
        if name in self.qualified_names:
            return self.qualified_names[name]

        # Try file-local scope
        if context_file and context_file in self.file_scopes:
            local_scope = self.file_scopes[context_file]
            if name in local_scope:
                return local_scope[name]

        # Try global scope
        if name in self.global_scope:
            return self.global_scope[name]

        return None

    def unregister(self, entity_id: str) -> None:
        """Remove all registrations for an entity.

        Args:
            entity_id: Entity ID to unregister
        """
        if entity_id not in self.entity_to_names:
            return

        for scope_type, name in self.entity_to_names[entity_id]:
            if scope_type == "global":
                self.global_scope.pop(name, None)
            elif scope_type == "qualified":
                self.qualified_names.pop(name, None)
            elif scope_type == "file":
                # Find and remove from file scopes
                for file_scope in self.file_scopes.values():
                    file_scope.pop(name, None)

        del self.entity_to_names[entity_id]

    def unregister_file(self, file_path: str) -> None:
        """Remove all symbols from a file.

        Args:
            file_path: Path of the file to remove
        """
        if file_path in self.file_scopes:
            # Get all entity IDs from this file
            entity_ids = set(self.file_scopes[file_path].values())
            # Unregister each entity
            for entity_id in entity_ids:
                self.unregister(entity_id)
            # Remove file scope
            del self.file_scopes[file_path]

    def clear(self) -> None:
        """Clear all scopes."""
        self.global_scope.clear()
        self.file_scopes.clear()
        self.qualified_names.clear()
        self.entity_to_names.clear()

    def get_all_symbols_in_file(self, file_path: str) -> dict[str, str]:
        """Get all symbols defined in a file.

        Args:
            file_path: Path to the file

        Returns:
            Dictionary of name -> entity_id for symbols in the file
        """
        return self.file_scopes.get(file_path, {})


class GraphBuilder:
    """Builds and maintains the code dependency graph."""

    def __init__(self, storage: GraphStorage, repo_root: Path | None = None):
        """Initialize the graph builder.

        Args:
            storage: GraphStorage instance to build into
            repo_root: Root directory of the repository (for import resolution)
        """
        self._storage = storage
        self._symbol_table = ScopedSymbolTable()
        self._repo_root = repo_root or Path.cwd()
        self._import_resolver = ImportResolver(self._repo_root)

    @property
    def storage(self) -> GraphStorage:
        """Access the underlying graph storage."""
        return self._storage

    def build_from_entities(self, entities: list[AnyEntity]) -> None:
        """Build the graph from a list of entities.

        This is a two-pass process:
        1. First pass: Add all nodes and build symbol table
        2. Second pass: Resolve relationships and add edges

        Args:
            entities: List of code entities to add to the graph
        """
        logger.info(f"Building graph from {len(entities)} entities")

        # Collect all known file paths for import resolution
        known_files = {
            entity.file_path for entity in entities if isinstance(entity, File)
        }
        self._import_resolver.set_known_files(known_files)

        # First pass: add all nodes
        for entity in entities:
            self._storage.add_entity(entity)
            self._register_symbol(entity)

        # Second pass: build relationships
        for entity in entities:
            self._build_edges(entity)

        stats = self._storage.get_statistics()
        logger.info(
            f"Graph built: {stats['nodes']} nodes, {stats['edges']} edges, "
            f"{stats['functions']} functions, {stats['classes']} classes, "
            f"{stats['files']} files"
        )

    def _register_symbol(self, entity: AnyEntity) -> None:
        """Register an entity in the symbol table for later resolution.

        Args:
            entity: Entity to register
        """
        if isinstance(entity, Function):
            qualified_name = None
            if entity.class_name:
                qualified_name = f"{entity.class_name}.{entity.name}"

            self._symbol_table.register(
                entity_id=entity.id,
                name=entity.name,
                file_path=entity.file_path,
                qualified_name=qualified_name,
                is_exported=True,
            )

            # Resolve external references
            self._resolve_external_reference(entity.name, entity.id)
            if qualified_name:
                self._resolve_external_reference(qualified_name, entity.id)

        elif isinstance(entity, Class):
            self._symbol_table.register(
                entity_id=entity.id,
                name=entity.name,
                file_path=entity.file_path,
                is_exported=True,
            )
            self._resolve_external_reference(entity.name, entity.id)

        elif isinstance(entity, TypeDefinition):
            self._symbol_table.register(
                entity_id=entity.id,
                name=entity.name,
                file_path=entity.file_path,
                is_exported=True,
            )
            self._resolve_external_reference(entity.name, entity.id)

    def _resolve_external_reference(self, name: str, real_id: str) -> None:
        """Resolve external reference by redirecting edges to the real entity.

        When a new entity is added, check if there's an external placeholder
        with the same name and redirect all edges to point to the real entity.

        Args:
            name: Symbol name that was just registered
            real_id: The real entity ID
        """
        external_id = f"external:{name}"

        if not self._storage.has_entity(external_id):
            return

        # Get all incoming edges to the external node
        incoming = self._storage.get_predecessors(external_id)

        # Redirect edges to the real entity
        for source_id, edge_data in incoming:
            edge_type = EdgeType(edge_data.get("type", "calls"))
            self._storage.add_edge(source_id, real_id, edge_type)

        # Remove the external node (this also removes its edges)
        self._storage.remove_entity(external_id)

        if incoming:
            logger.debug(f"Resolved {len(incoming)} references from external:{name} to {real_id}")

    def _build_edges(self, entity: AnyEntity) -> None:
        """Build edges for an entity.

        Args:
            entity: Entity to process
        """
        if isinstance(entity, Function):
            self._build_function_edges(entity)
        elif isinstance(entity, Class):
            self._build_class_edges(entity)
        elif isinstance(entity, File):
            self._build_file_edges(entity)

    def _build_function_edges(self, func: Function) -> None:
        """Build edges for a function entity.

        Args:
            func: Function entity
        """
        # CALLS edges: function calls other functions
        for call_name in func.calls:
            target_id = self._resolve_symbol(call_name, func.file_path)
            if target_id:
                self._storage.add_edge(func.id, target_id, EdgeType.CALLS)
            else:
                # Create edge to external symbol
                self._storage.add_edge_by_name(
                    func.id, call_name, EdgeType.CALLS, create_if_missing=True
                )

        # If this is a method, add CONTAINS edge from class
        if func.class_name:
            class_id = self._resolve_symbol(func.class_name, func.file_path)
            if class_id:
                self._storage.add_edge(class_id, func.id, EdgeType.CONTAINS)

    def _build_class_edges(self, cls: Class) -> None:
        """Build edges for a class entity.

        Args:
            cls: Class entity
        """
        # INHERITS edges: class inherits from base classes
        for base_name in cls.bases:
            target_id = self._resolve_symbol(base_name, cls.file_path)
            if target_id:
                self._storage.add_edge(cls.id, target_id, EdgeType.INHERITS)
            else:
                # Create edge to external base class
                self._storage.add_edge_by_name(
                    cls.id, base_name, EdgeType.INHERITS, create_if_missing=True
                )

    def _build_file_edges(self, file: File) -> None:
        """Build edges for a file entity.

        Args:
            file: File entity
        """
        # DEFINES edges: file defines entities
        for entity_id in file.defines:
            if self._storage.has_entity(entity_id):
                self._storage.add_edge(file.id, entity_id, EdgeType.DEFINES)

        # IMPORTS edges: file imports modules
        for import_name in file.imports:
            # Try to resolve to internal file using the language-aware resolver
            target_id = self._resolve_import(import_name, file.file_path, file.language)
            if target_id:
                self._storage.add_edge(file.id, target_id, EdgeType.IMPORTS)
            else:
                # Create external module reference
                self._storage.add_edge_by_name(
                    file.id, import_name, EdgeType.IMPORTS, create_if_missing=True
                )

    def _resolve_symbol(self, name: str, context_file: str) -> str | None:
        """Resolve a symbol name to an entity ID.

        Args:
            name: Symbol name to resolve
            context_file: File path for context (for local resolution)

        Returns:
            Entity ID or None if not found
        """
        return self._symbol_table.resolve(name, context_file)

    def _resolve_import(
        self, import_name: str, context_file: str, language: str = "python"
    ) -> str | None:
        """Resolve an import to a file entity ID.

        Args:
            import_name: Import name (e.g., "os", "src.utils", "./utils")
            context_file: File path of the importing file
            language: Programming language for language-specific resolution

        Returns:
            File entity ID or None if not found (external module)
        """
        # Use the language-aware import resolver
        resolved = self._import_resolver.resolve(import_name, context_file, language)

        if resolved.is_external or resolved.resolved_path is None:
            return None

        # Find the file entity by path
        resolved_path = resolved.resolved_path
        for node_id, data in self._storage.graph.nodes(data=True):
            if data.get("type") == "file":
                file_path = data.get("file_path", "")
                if file_path == resolved_path or file_path.endswith(f"/{resolved_path}"):
                    return node_id

        return None

    def update_file(self, file_path: Path, entities: list[AnyEntity]) -> None:
        """Update the graph for a changed file.

        This removes existing entities for the file and adds new ones.

        Args:
            file_path: Path to the file that changed
            entities: New entities parsed from the file
        """
        file_path_str = str(file_path)

        # Remove old entities and symbols
        removed = self._storage.remove_file(file_path_str)
        logger.debug(f"Removed {len(removed)} entities from {file_path_str}")

        # Remove old symbols from symbol table
        for entity_id in removed:
            self._symbol_table.unregister(entity_id)

        # Add new entities
        for entity in entities:
            self._storage.add_entity(entity)
            self._register_symbol(entity)

        # Rebuild edges for new entities
        for entity in entities:
            self._build_edges(entity)

        logger.debug(f"Added {len(entities)} entities from {file_path_str}")

    def remove_file(self, file_path: Path) -> None:
        """Remove all entities from a file.

        Args:
            file_path: Path to the file to remove
        """
        file_path_str = str(file_path)
        removed = self._storage.remove_file(file_path_str)

        # Remove from symbol table
        for entity_id in removed:
            self._symbol_table.unregister(entity_id)

        logger.debug(f"Removed {len(removed)} entities from {file_path_str}")

    def clear(self) -> None:
        """Clear the graph and symbol table."""
        self._storage.clear()
        self._symbol_table.clear()

    @property
    def symbol_table(self) -> ScopedSymbolTable:
        """Access the symbol table for testing/debugging."""
        return self._symbol_table
