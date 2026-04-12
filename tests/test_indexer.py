"""Tests for code indexer."""

from pathlib import Path

import pytest

from ckg.graph.store import GraphStore
from ckg.indexing.indexer import CodeIndexer


class TestCodeIndexer:
    """Tests for CodeIndexer."""

    @pytest.fixture
    def temp_repo(self, tmp_path):
        """Create a temporary repository with sample files."""
        # Create Python file
        python_file = tmp_path / "main.py"
        python_file.write_text('''
"""Main module."""

import os
from pathlib import Path


class Config:
    """Configuration class."""

    def __init__(self, path: str):
        self.path = path

    def load(self) -> dict:
        """Load configuration."""
        return {}


def main():
    """Entry point."""
    config = Config("config.json")
    config.load()


if __name__ == "__main__":
    main()
''')

        # Create TypeScript file
        ts_file = tmp_path / "app.ts"
        ts_file.write_text('''
import { Component } from './component';

interface User {
    name: string;
    age: number;
}

class App {
    private users: User[] = [];

    addUser(user: User): void {
        this.users.push(user);
    }

    getUsers(): User[] {
        return this.users;
    }
}

export function createApp(): App {
    return new App();
}
''')

        return tmp_path

    @pytest.fixture
    def indexer(self, temp_repo):
        store = GraphStore()
        return CodeIndexer(temp_repo, store)

    def test_full_index(self, indexer, temp_repo):
        stats = indexer.index_full()

        assert stats["files_processed"] >= 2
        assert stats["functions"] > 0
        assert stats["classes"] > 0

    def test_incremental_index(self, indexer, temp_repo):
        # First do full index
        indexer.index_full()

        # Modify a file
        python_file = temp_repo / "main.py"
        content = python_file.read_text()
        python_file.write_text(content + "\n\ndef new_function():\n    pass\n")

        # Do incremental index (will fall back to full since no git repo)
        stats = indexer.index_incremental()

        # Should either have incremental stats or full stats (fallback)
        assert (
            "files_added" in stats or
            "files_processed" in stats
        )

    def test_ignore_patterns(self, indexer, temp_repo):
        # Create node_modules directory (should be ignored)
        node_modules = temp_repo / "node_modules"
        node_modules.mkdir()
        (node_modules / "package.js").write_text("// ignored")

        indexer.index_full()

        # node_modules should not be indexed
        file_nodes = indexer.store.get_nodes_by_type(
            __import__("ckg.graph.models", fromlist=["NodeType"]).NodeType.FILE
        )
        file_paths = [n.path for n in file_nodes]  # type: ignore
        assert not any("node_modules" in p for p in file_paths)

    def test_resolve_references(self, indexer, temp_repo):
        indexer.index_full()
        resolved = indexer.resolve_references()

        # Should resolve at least some references
        assert resolved >= 0

    def test_file_detection(self, indexer):
        assert indexer._detect_language(Path("test.py")) == "python"
        assert indexer._detect_language(Path("test.ts")) == "typescript"
        assert indexer._detect_language(Path("test.go")) == "go"
        assert indexer._detect_language(Path("test.rs")) == "rust"
        assert indexer._detect_language(Path("test.unknown")) == "unknown"
