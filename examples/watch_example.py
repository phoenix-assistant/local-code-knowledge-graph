#!/usr/bin/env python3
"""Example of real-time file watching with CKG."""

import time
from pathlib import Path

from ckg import CodeIndexer, GraphStore
from ckg.watch import FileWatcher


def main():
    repo_path = Path(".").resolve()
    data_dir = repo_path / ".ckg"

    print(f"Watching repository: {repo_path}")
    print("Press Ctrl+C to stop.\n")

    # Initialize
    store = GraphStore(db_path=data_dir / "graph.db")
    indexer = CodeIndexer(repo_path, store)

    # Initial index
    print("Running initial index...")
    stats = indexer.index_full()
    print(f"Indexed {stats['files_processed']} files\n")

    # Callback for file changes
    def on_change(path: str, event_type: str):
        emoji = {"created": "✨", "modified": "📝", "deleted": "🗑️"}.get(
            event_type, "❓"
        )
        print(f"{emoji} {event_type}: {path}")

        # Show updated stats
        graph_stats = store.get_stats()
        print(f"   Graph: {graph_stats['total_nodes']} nodes, {graph_stats['total_edges']} edges")

    # Start watching
    watcher = FileWatcher(indexer, on_change=on_change)

    try:
        with watcher:
            print("Watching for changes...")
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped watching.")
    finally:
        store.close()


if __name__ == "__main__":
    main()
