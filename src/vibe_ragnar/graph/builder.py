"""Graph builder for constructing code dependency graphs from parsed entities."""

import logging
from pathlib import Path

from ..parser.entities import AnyEntity, Class, File, Function, TypeDefinition
from .storage import EdgeType, GraphStorage

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Builds and maintains the code dependency graph."""

    def __init__(self, storage: GraphStorage):
        """Initialize the graph builder.

        Args:
            storage: GraphStorage instance to build into
        """
        self._storage = storage
        self._symbol_table: dict[str, str] = {}  # name -> entity_id mapping

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
        names_to_register: list[str] = []

        if isinstance(entity, Function):
            # Register by simple name
            names_to_register.append(entity.name)
            # Also register qualified name for methods
            if entity.class_name:
                qualified = f"{entity.class_name}.{entity.name}"
                names_to_register.append(qualified)

        elif isinstance(entity, Class):
            names_to_register.append(entity.name)

        elif isinstance(entity, TypeDefinition):
            names_to_register.append(entity.name)

        # Register all names and resolve external references
        for name in names_to_register:
            self._symbol_table[name] = entity.id
            self._resolve_external_reference(name, entity.id)

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
            # Try to resolve to internal file
            target_id = self._resolve_import(import_name, file.file_path)
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
        # Try exact match first
        if name in self._symbol_table:
            return self._symbol_table[name]

        # Try file-qualified name
        # e.g., for "process" in "src/utils.py", try "src/utils.py:process"
        file_qualified = f"{context_file}:{name}"
        if file_qualified in self._symbol_table:
            return self._symbol_table[file_qualified]

        return None

    def _resolve_import(self, import_name: str, context_file: str) -> str | None:
        """Resolve an import to a file entity ID.

        Args:
            import_name: Import name (e.g., "os", "src.utils", "./utils")
            context_file: File path of the importing file

        Returns:
            File entity ID or None if not found (external module)
        """
        # For now, just try to find a file with matching name
        # This is simplified - a full implementation would handle:
        # - Relative imports
        # - Package resolution
        # - Module search paths

        # Try direct match (Python module style: src.utils -> src/utils.py)
        module_path = import_name.replace(".", "/")
        possible_paths = [
            f"{module_path}.py",
            f"{module_path}/__init__.py",
            f"{module_path}.ts",
            f"{module_path}.js",
            f"{module_path}/index.ts",
            f"{module_path}/index.js",
        ]

        for path in possible_paths:
            # Look for file entity with this path
            for node_id, data in self._storage.graph.nodes(data=True):
                if data.get("type") == "file" and data.get("file_path", "").endswith(path):
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

        # Remove old entities
        removed = self._storage.remove_file(file_path_str)
        logger.debug(f"Removed {len(removed)} entities from {file_path_str}")

        # Remove old symbols from symbol table
        for entity_id in removed:
            # Find and remove from symbol table
            to_remove = [k for k, v in self._symbol_table.items() if v == entity_id]
            for key in to_remove:
                del self._symbol_table[key]

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
            to_remove = [k for k, v in self._symbol_table.items() if v == entity_id]
            for key in to_remove:
                del self._symbol_table[key]

        logger.debug(f"Removed {len(removed)} entities from {file_path_str}")

    def clear(self) -> None:
        """Clear the graph and symbol table."""
        self._storage.clear()
        self._symbol_table.clear()
