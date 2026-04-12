"""File system watcher for real-time code indexing."""

import time
from collections.abc import Callable
from pathlib import Path
from threading import Event, Thread

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from ckg.indexing.indexer import CodeIndexer
from ckg.parsing.manager import ParserManager


class CodeEventHandler(FileSystemEventHandler):
    """Handle file system events for code files."""

    def __init__(
        self,
        indexer: CodeIndexer,
        parser_manager: ParserManager,
        on_change: Callable[[str, str], None] | None = None,
        debounce_seconds: float = 0.5,
    ):
        """Initialize event handler.

        Args:
            indexer: Code indexer instance
            parser_manager: Parser manager for file type detection
            on_change: Optional callback(path, event_type) for changes
            debounce_seconds: Time to wait before processing changes
        """
        self.indexer = indexer
        self.parser_manager = parser_manager
        self.on_change = on_change
        self.debounce_seconds = debounce_seconds

        self._supported_exts = set(parser_manager.supported_extensions())
        self._pending_changes: dict[str, tuple[str, float]] = {}
        self._process_thread: Thread | None = None
        self._stop_event = Event()

    def _is_supported_file(self, path: str) -> bool:
        """Check if file is a supported code file."""
        return Path(path).suffix.lower() in self._supported_exts

    def _schedule_change(self, path: str, event_type: str) -> None:
        """Schedule a change for processing after debounce period."""
        self._pending_changes[path] = (event_type, time.time())

        # Start processor thread if not running
        if self._process_thread is None or not self._process_thread.is_alive():
            self._process_thread = Thread(target=self._process_changes, daemon=True)
            self._process_thread.start()

    def _process_changes(self) -> None:
        """Process pending changes after debounce period."""
        while not self._stop_event.is_set():
            current_time = time.time()
            to_process = []

            # Find changes ready to process
            for path, (event_type, timestamp) in list(self._pending_changes.items()):
                if current_time - timestamp >= self.debounce_seconds:
                    to_process.append((path, event_type))
                    del self._pending_changes[path]

            # Process ready changes
            for path, event_type in to_process:
                try:
                    self._handle_change(path, event_type)
                except Exception as e:
                    print(f"Error processing {path}: {e}")

            if not self._pending_changes:
                break

            time.sleep(0.1)

    def _handle_change(self, path: str, event_type: str) -> None:
        """Handle a file change."""
        file_path = Path(path)

        if event_type == "deleted":
            # Remove from graph
            rel_path = str(file_path.relative_to(self.indexer.repo_path))
            self.indexer.store.remove_file_nodes(rel_path)
        else:
            # Index the file
            if file_path.exists():
                self.indexer._index_file(file_path)

        if self.on_change:
            self.on_change(path, event_type)

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation."""
        if not event.is_directory and self._is_supported_file(event.src_path):
            self._schedule_change(event.src_path, "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification."""
        if not event.is_directory and self._is_supported_file(event.src_path):
            self._schedule_change(event.src_path, "modified")

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion."""
        if not event.is_directory and self._is_supported_file(event.src_path):
            self._schedule_change(event.src_path, "deleted")

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file move/rename."""
        if not event.is_directory:
            if self._is_supported_file(event.src_path):
                self._schedule_change(event.src_path, "deleted")
            if self._is_supported_file(event.dest_path):
                self._schedule_change(event.dest_path, "created")

    def stop(self) -> None:
        """Stop the processor thread."""
        self._stop_event.set()
        if self._process_thread:
            self._process_thread.join(timeout=2)


class FileWatcher:
    """Watch a directory for code changes and update the index."""

    def __init__(
        self,
        indexer: CodeIndexer,
        parser_manager: ParserManager | None = None,
        on_change: Callable[[str, str], None] | None = None,
    ):
        """Initialize file watcher.

        Args:
            indexer: Code indexer instance
            parser_manager: Optional parser manager (uses indexer's if not provided)
            on_change: Optional callback(path, event_type) for changes
        """
        self.indexer = indexer
        self.parser_manager = parser_manager or indexer.parser_manager

        self._observer = Observer()
        self._handler = CodeEventHandler(
            indexer=indexer,
            parser_manager=self.parser_manager,
            on_change=on_change,
        )
        self._running = False

    def start(self) -> None:
        """Start watching for changes."""
        if self._running:
            return

        self._observer.schedule(
            self._handler,
            str(self.indexer.repo_path),
            recursive=True,
        )
        self._observer.start()
        self._running = True

    def stop(self) -> None:
        """Stop watching for changes."""
        if not self._running:
            return

        self._handler.stop()
        self._observer.stop()
        self._observer.join(timeout=5)
        self._running = False

    def is_running(self) -> bool:
        """Check if watcher is running."""
        return self._running

    def __enter__(self) -> "FileWatcher":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, *args) -> None:
        """Context manager exit."""
        self.stop()
