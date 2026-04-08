"""Code indexer with full and incremental support."""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ckg.graph.models import Edge, EdgeType, FileNode
from ckg.graph.store import GraphStore
from ckg.indexing.git_tracker import GitTracker
from ckg.parsing.manager import ParserManager


class CodeIndexer:
    """Index code files into the knowledge graph."""

    def __init__(
        self,
        repo_path: Path,
        store: GraphStore,
        parser_manager: ParserManager | None = None,
    ):
        """Initialize the indexer.

        Args:
            repo_path: Path to the repository root
            store: Graph store for persistence
            parser_manager: Parser manager (created if not provided)
        """
        self.repo_path = repo_path
        self.store = store
        self.parser_manager = parser_manager or ParserManager()
        self.git_tracker = GitTracker(repo_path)

        # Default ignore patterns
        self._ignore_patterns = {
            ".git",
            ".hg",
            ".svn",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "node_modules",
            "venv",
            ".venv",
            "env",
            ".env",
            "dist",
            "build",
            ".egg-info",
            ".tox",
            ".nox",
            "target",  # Rust
            "vendor",  # Go
        }

    def add_ignore_pattern(self, pattern: str) -> None:
        """Add a pattern to ignore during indexing."""
        self._ignore_patterns.add(pattern)

    def should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored."""
        # Check against ignore patterns
        for part in path.parts:
            if part in self._ignore_patterns:
                return True

        # Check gitignore
        if self.git_tracker.is_git_repo():
            rel_path = str(path.relative_to(self.repo_path))
            if self.git_tracker.is_ignored(rel_path):
                return True

        return False

    def index_full(
        self,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> dict[str, int]:
        """Perform full indexing of the repository.

        Args:
            progress_callback: Optional callback(file_path, current, total)

        Returns:
            Statistics about the indexing operation
        """
        stats = {
            "files_processed": 0,
            "files_skipped": 0,
            "errors": 0,
            "functions": 0,
            "classes": 0,
            "imports": 0,
        }

        # Find all indexable files
        files_to_index = []
        supported_exts = set(self.parser_manager.supported_extensions())

        for root, dirs, files in os.walk(self.repo_path):
            # Filter directories in-place
            dirs[:] = [d for d in dirs if d not in self._ignore_patterns]

            for filename in files:
                file_path = Path(root) / filename
                if file_path.suffix.lower() in supported_exts:
                    if not self.should_ignore(file_path):
                        files_to_index.append(file_path)

        total = len(files_to_index)

        for i, file_path in enumerate(files_to_index):
            if progress_callback:
                progress_callback(str(file_path), i + 1, total)

            result = self._index_file(file_path)
            if result:
                stats["files_processed"] += 1
                stats["functions"] += result.get("functions", 0)
                stats["classes"] += result.get("classes", 0)
                stats["imports"] += result.get("imports", 0)
                if result.get("errors"):
                    stats["errors"] += len(result["errors"])
            else:
                stats["files_skipped"] += 1

        return stats

    def index_incremental(
        self,
        since_commit: str | None = None,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> dict[str, int]:
        """Perform incremental indexing based on git changes.

        Args:
            since_commit: Commit hash to diff against (uses stored if None)
            progress_callback: Optional callback(file_path, current, total)

        Returns:
            Statistics about the indexing operation
        """
        stats = {
            "files_added": 0,
            "files_modified": 0,
            "files_deleted": 0,
            "errors": 0,
        }

        if not self.git_tracker.is_git_repo():
            # Fall back to full index
            return self.index_full(progress_callback)

        # Get changes
        changes = []
        if since_commit:
            changes = self.git_tracker.get_changes_since(since_commit)
        else:
            # Get both staged and unstaged changes
            changes.extend(self.git_tracker.get_staged_changes())
            changes.extend(self.git_tracker.get_unstaged_changes())

        # Add untracked files as additions
        for untracked in self.git_tracker.get_untracked_files():
            if not any(c.path == untracked for c in changes):
                from ckg.indexing.git_tracker import FileChange
                changes.append(FileChange(path=untracked, status="A"))

        total = len(changes)

        for i, change in enumerate(changes):
            file_path = self.repo_path / change.path

            if progress_callback:
                progress_callback(change.path, i + 1, total)

            if change.status == "D":
                # Deleted file - remove from graph
                file_id = f"file:{change.path}"
                self.store.remove_file_nodes(change.path)
                stats["files_deleted"] += 1

            elif change.status in ("A", "M", "R"):
                # Added, modified, or renamed - (re)index
                if change.status == "R" and change.old_path:
                    # Remove old file nodes for rename
                    self.store.remove_file_nodes(change.old_path)

                if file_path.exists() and not self.should_ignore(file_path):
                    result = self._index_file(file_path)
                    if result:
                        if change.status == "A":
                            stats["files_added"] += 1
                        else:
                            stats["files_modified"] += 1
                        if result.get("errors"):
                            stats["errors"] += len(result["errors"])

        return stats

    def _index_file(self, file_path: Path) -> dict[str, int] | None:
        """Index a single file.

        Returns:
            Statistics dict or None if file couldn't be indexed
        """
        rel_path = str(file_path.relative_to(self.repo_path))
        file_id = f"file:{rel_path}"

        # Remove existing nodes for this file
        self.store.remove_file_nodes(rel_path)

        # Create file node
        stat = file_path.stat()
        file_node = FileNode(
            id=file_id,
            name=file_path.name,
            path=rel_path,
            language=self._detect_language(file_path),
            last_modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            size_bytes=stat.st_size,
            line_count=self._count_lines(file_path),
        )
        self.store.add_node(file_node)

        # Parse the file
        parse_result = self.parser_manager.parse_file(file_path, file_id)
        if not parse_result:
            return None

        stats = {
            "functions": 0,
            "classes": 0,
            "imports": 0,
            "errors": parse_result.errors,
        }

        # Add nodes and edges from parse result
        for func in parse_result.functions:
            self.store.add_node(func)
            stats["functions"] += 1

        for cls in parse_result.classes:
            self.store.add_node(cls)
            stats["classes"] += 1

        for imp in parse_result.imports:
            self.store.add_node(imp)
            stats["imports"] += 1

        for var in parse_result.variables:
            self.store.add_node(var)

        for edge in parse_result.edges:
            # Skip unresolved edges (will be resolved later)
            if not edge.metadata.get("unresolved"):
                self.store.add_edge(edge)

        return stats

    def _detect_language(self, file_path: Path) -> str:
        """Detect programming language from file extension."""
        ext_map = {
            ".py": "python",
            ".pyw": "python",
            ".pyi": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".rb": "ruby",
            ".php": "php",
        }
        return ext_map.get(file_path.suffix.lower(), "unknown")

    def _count_lines(self, file_path: Path) -> int:
        """Count lines in a file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0

    def resolve_references(self) -> int:
        """Resolve unresolved references between symbols.

        Returns:
            Number of references resolved
        """
        resolved = 0

        # Get all functions and classes for lookup
        from ckg.graph.models import NodeType

        functions = {n.name: n for n in self.store.get_nodes_by_type(NodeType.FUNCTION)}
        classes = {n.name: n for n in self.store.get_nodes_by_type(NodeType.CLASS)}

        # Iterate through all edges and resolve unresolved ones
        for source_id, target_id, data in list(self.store.graph.edges(data=True)):
            if not data.get("unresolved"):
                continue

            edge_type = EdgeType(data["type"])

            # Extract name from placeholder target
            if target_id.startswith("func:*:*:"):
                func_name = target_id.split(":")[-1]
                if func_name in functions:
                    # Create resolved edge
                    self.store.add_edge(
                        Edge(
                            source_id=source_id,
                            target_id=functions[func_name].id,
                            type=edge_type,
                        )
                    )
                    resolved += 1

            elif target_id.startswith("class:*:"):
                class_name = target_id.split(":")[-1]
                if class_name in classes:
                    self.store.add_edge(
                        Edge(
                            source_id=source_id,
                            target_id=classes[class_name].id,
                            type=edge_type,
                        )
                    )
                    resolved += 1

            # Remove placeholder edge
            if self.store.graph.has_edge(source_id, target_id):
                self.store.graph.remove_edge(source_id, target_id)

        return resolved
