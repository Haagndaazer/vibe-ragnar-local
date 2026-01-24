"""File watcher with debouncing for real-time code indexing updates."""

import logging
import threading
from pathlib import Path
from typing import Callable

from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from ..parser.languages import IGNORED_DIRECTORIES, is_supported_file

logger = logging.getLogger(__name__)


class DebouncedFileHandler(FileSystemEventHandler):
    """File system event handler with debouncing.

    Accumulates file changes and triggers a callback after a quiet period.
    This prevents excessive processing when many files change rapidly
    (e.g., git checkout, IDE auto-save, code formatters).
    """

    def __init__(
        self,
        on_changes_callback: Callable[[dict[str, str]], None],
        debounce_seconds: float = 5.0,
        supported_extensions: set[str] | None = None,
    ):
        """Initialize the debounced handler.

        Args:
            on_changes_callback: Function called with accumulated changes
                                 Dict maps file path to change type ("upsert" or "delete")
            debounce_seconds: Seconds to wait for quiet period before processing
            supported_extensions: File extensions to monitor (default: all supported)
        """
        super().__init__()
        self._callback = on_changes_callback
        self._debounce_seconds = debounce_seconds
        self._supported_extensions = supported_extensions

        self._pending_changes: dict[str, str] = {}  # path -> change_type
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def _should_process(self, path: str) -> bool:
        """Check if a file should be processed.

        Args:
            path: File path to check

        Returns:
            True if the file should be monitored
        """
        path_obj = Path(path)

        # Check if path is in an ignored directory
        for part in path_obj.parts:
            if part in IGNORED_DIRECTORIES:
                return False
            # Also ignore hidden directories
            if part.startswith(".") and part not in {".github", ".gitlab"}:
                return False

        # Check file extension
        if self._supported_extensions:
            return path_obj.suffix.lower() in self._supported_extensions

        return is_supported_file(path)

    def on_created(self, event: FileCreatedEvent | DirCreatedEvent) -> None:
        """Handle file/directory creation."""
        if isinstance(event, DirCreatedEvent):
            return
        self._handle_change(event.src_path, "upsert")

    def on_modified(self, event: FileModifiedEvent | DirModifiedEvent) -> None:
        """Handle file/directory modification."""
        if isinstance(event, DirModifiedEvent):
            return
        self._handle_change(event.src_path, "upsert")

    def on_deleted(self, event: FileDeletedEvent | DirDeletedEvent) -> None:
        """Handle file/directory deletion."""
        if isinstance(event, DirDeletedEvent):
            return
        self._handle_change(event.src_path, "delete")

    def on_moved(self, event: FileMovedEvent | DirMovedEvent) -> None:
        """Handle file/directory move/rename."""
        if isinstance(event, DirMovedEvent):
            return
        # Treat as delete of old path and create of new path
        self._handle_change(event.src_path, "delete")
        self._handle_change(event.dest_path, "upsert")

    def _handle_change(self, path: str, change_type: str) -> None:
        """Handle a file change event.

        Args:
            path: Path to the changed file
            change_type: Type of change ("upsert" or "delete")
        """
        if not self._should_process(path):
            return

        with self._lock:
            # Record the change
            self._pending_changes[path] = change_type

            # Reset the debounce timer
            if self._timer is not None:
                self._timer.cancel()

            self._timer = threading.Timer(
                self._debounce_seconds,
                self._flush_changes,
            )
            self._timer.daemon = True
            self._timer.start()

            logger.debug(
                f"File change queued: {path} ({change_type}), "
                f"pending: {len(self._pending_changes)}"
            )

    def _flush_changes(self) -> None:
        """Flush accumulated changes to the callback."""
        with self._lock:
            if not self._pending_changes:
                return

            changes = dict(self._pending_changes)
            self._pending_changes.clear()
            self._timer = None

        # Fix change types based on actual file existence
        # Some editors do atomic saves (delete + create), so we check if file exists
        corrected_changes: dict[str, str] = {}
        for path, change_type in changes.items():
            path_obj = Path(path)
            if path_obj.exists():
                # File exists -> it's an upsert regardless of recorded events
                corrected_changes[path] = "upsert"
            else:
                # File doesn't exist -> it's a delete
                corrected_changes[path] = "delete"

        logger.info(f"Processing {len(corrected_changes)} file changes")

        try:
            self._callback(corrected_changes)
        except Exception as e:
            logger.error(f"Error processing file changes: {e}")

    def stop(self) -> None:
        """Stop any pending timer."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None


class FileWatcher:
    """Watch a directory for file changes and trigger reindexing."""

    def __init__(
        self,
        repo_path: Path,
        on_changes: Callable[[dict[str, str]], None],
        debounce_seconds: float = 5.0,
    ):
        """Initialize the file watcher.

        Args:
            repo_path: Root directory to watch
            on_changes: Callback for file changes
            debounce_seconds: Debounce delay in seconds
        """
        self._repo_path = repo_path
        self._debounce_seconds = debounce_seconds

        self._handler = DebouncedFileHandler(
            on_changes_callback=on_changes,
            debounce_seconds=debounce_seconds,
        )
        self._observer = Observer()
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if the watcher is running."""
        return self._running

    def start(self) -> None:
        """Start watching for file changes."""
        if self._running:
            logger.warning("FileWatcher is already running")
            return

        self._observer.schedule(
            self._handler,
            str(self._repo_path),
            recursive=True,
        )
        self._observer.start()
        self._running = True

        logger.info(f"FileWatcher started for {self._repo_path}")

    def stop(self) -> None:
        """Stop watching for file changes."""
        if not self._running:
            return

        self._handler.stop()
        self._observer.stop()
        self._observer.join(timeout=5.0)
        self._running = False

        logger.info("FileWatcher stopped")

    def __enter__(self) -> "FileWatcher":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop()
