"""File watcher for automatic recipe graph rebuilds.

Uses Watchdog to monitor a directory tree for .txt file changes and
triggers a rebuild pipeline: re-parse changed files, rebuild the
dependency graph, detect cycles, and invoke a callback.

This is a library component (not CLI-specific) so the future Dear PyGui
GUI can reuse it with its own callback.
"""

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

import networkx
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from craftgraph.config import get_config
from craftgraph.graph import build_graph, find_cycles
from craftgraph.models import ParsedFile
from craftgraph.parser import MappingError, ParseError, parse_directory, parse_file

logger = logging.getLogger(__name__)

# Public type alias for the rebuild callback signature.
# Receives: (all parsed files, dependency graph, detected cycles)
# Note: DiGraph is not generic-subscriptable at runtime, so we omit [str].
RebuildCallback = Callable[
    [list[ParsedFile], networkx.DiGraph, list[list[str]]],  # type: ignore[type-arg]
    None,
]


class _RecipeEventHandler(FileSystemEventHandler):
    """Watchdog event handler that debounces .txt changes and rebuilds the graph.

    Maintains a per-file cache of successful parse results. On each
    rebuild, the full graph is reconstructed from all cached files.
    """

    def __init__(
        self,
        directory: Path,
        on_rebuild: RebuildCallback,
        *,
        debounce_seconds: float | None = None,
    ) -> None:
        super().__init__()
        self._directory = directory
        self._on_rebuild = on_rebuild
        if debounce_seconds is None:
            debounce_seconds = get_config().timings.watcher_debounce_sec
        self._debounce_seconds = debounce_seconds
        self._cache: dict[Path, ParsedFile] = {}
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    # -- Public API ------------------------------------------------------------

    def set_debounce_seconds(self, seconds: float) -> None:
        """Update the debounce interval for future rebuilds."""
        self._debounce_seconds = seconds

    def initial_parse(self) -> None:
        """Walk the directory, populate the cache, and trigger the first rebuild."""
        parsed_files = parse_directory(self._directory)
        with self._lock:
            for pf in parsed_files:
                self._cache[pf.source_path] = pf
        self._rebuild()

    # -- Watchdog event handlers -----------------------------------------------

    def on_modified(self, event: FileSystemEvent) -> None:
        if not self._is_relevant(event):
            return
        self._reparse_file(Path(str(event.src_path)))
        self._schedule_rebuild()

    def on_created(self, event: FileSystemEvent) -> None:
        if not self._is_relevant(event):
            return
        self._reparse_file(Path(str(event.src_path)))
        self._schedule_rebuild()

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not self._is_relevant(event):
            return
        path = Path(str(event.src_path))
        with self._lock:
            self._cache.pop(path, None)
        self._schedule_rebuild()

    # -- Internal helpers ------------------------------------------------------

    def _is_relevant(self, event: FileSystemEvent) -> bool:
        """Return True only for non-directory events on .txt files."""
        if event.is_directory:
            return False
        return Path(str(event.src_path)).suffix.lower() == ".txt"

    def _reparse_file(self, path: Path) -> None:
        """Re-parse a single file and update the cache.

        If parsing fails (mid-save, syntax error), the previous cached
        version is kept and a warning is logged.
        """
        if not path.exists():
            return
        try:
            parsed = parse_file(path)
        except (ParseError, MappingError, OSError) as exc:
            logger.warning("Failed to parse %s (keeping cached version): %s", path, exc)
            return

        if parsed.block_type is None:
            # File is empty or comment-only; remove from cache
            with self._lock:
                self._cache.pop(path, None)
            return

        with self._lock:
            self._cache[path] = parsed

    def _schedule_rebuild(self) -> None:
        """Cancel any pending rebuild timer and start a new one."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce_seconds, self._rebuild)
            self._timer.daemon = True
            self._timer.start()

    def _rebuild(self) -> None:
        """Build graph from all cached files and invoke the callback."""
        with self._lock:
            parsed_files = list(self._cache.values())

        graph = build_graph(parsed_files)
        cycles = find_cycles(graph)
        self._on_rebuild(parsed_files, graph, cycles)


class RecipeWatcher:
    """Non-blocking wrapper around Watchdog for GUI integration.

    Call :meth:`start` to begin watching and :meth:`stop` to tear down.
    The *on_rebuild* callback fires from the Watchdog thread, so GUI
    callers must marshal into their event loop.
    """

    def __init__(
        self,
        directory: Path,
        on_rebuild: RebuildCallback,
        *,
        debounce_seconds: float | None = None,
    ) -> None:
        self._handler = _RecipeEventHandler(
            directory, on_rebuild, debounce_seconds=debounce_seconds,
        )
        self._observer = Observer()
        self._observer.schedule(self._handler, str(directory), recursive=True)

    def start(self) -> None:
        """Run the initial parse and start the background observer."""
        self._handler.initial_parse()
        self._observer.start()

    def stop(self) -> None:
        """Stop the observer and wait for its thread to finish."""
        self._observer.stop()
        self._observer.join()

    def set_debounce_seconds(self, seconds: float) -> None:
        """Update the debounce interval for future change events."""
        self._handler.set_debounce_seconds(seconds)

    @property
    def running(self) -> bool:
        return self._observer.is_alive()


def watch_directory(
    directory: Path,
    on_rebuild: RebuildCallback,
    *,
    debounce_seconds: float | None = None,
) -> None:
    """Watch a directory tree for .txt changes and rebuild on each change.

    Performs an initial parse and rebuild, then blocks until
    KeyboardInterrupt. The *on_rebuild* callback fires on the initial
    build and again after each debounced change.
    """
    handler = _RecipeEventHandler(directory, on_rebuild, debounce_seconds=debounce_seconds)
    handler.initial_parse()

    observer = Observer()
    observer.schedule(handler, str(directory), recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
