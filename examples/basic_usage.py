#!/usr/bin/env python3
"""Basic usage example for Local Code Knowledge Graph."""

from pathlib import Path

from ckg import CodeIndexer, GraphStore, QueryEngine
from ckg.graph.models import NodeType
from ckg.watch import FileWatcher


def main():
    # Set up paths
    repo_path = Path(".").resolve()
    data_dir = repo_path / ".ckg"

    print(f"Indexing repository: {repo_path}")

    # Initialize components
    store = GraphStore(db_path=data_dir / "graph.db")
    indexer = CodeIndexer(repo_path, store)
    query_engine = QueryEngine(store, vector_path=data_dir / "vectors")

    # Full index
    print("\n📦 Running full index...")
    stats = indexer.index_full(
        progress_callback=lambda path, i, total: print(f"  [{i}/{total}] {path}")
    )
    print(f"  Files: {stats['files_processed']}")
    print(f"  Functions: {stats['functions']}")
    print(f"  Classes: {stats['classes']}")

    # Resolve cross-references
    print("\n🔗 Resolving references...")
    resolved = indexer.resolve_references()
    print(f"  Resolved: {resolved}")

    # Build vector index
    print("\n🔢 Building vector index...")
    vector_count = query_engine.index_vectors()
    print(f"  Indexed: {vector_count} embeddings")

    # Show statistics
    print("\n📊 Graph Statistics:")
    graph_stats = store.get_stats()
    print(f"  Nodes: {graph_stats['total_nodes']}")
    print(f"  Edges: {graph_stats['total_edges']}")
    for node_type, count in graph_stats["node_types"].items():
        print(f"    {node_type}: {count}")

    # Example queries
    print("\n🔍 Example Queries:")

    # Natural language query
    print("\n  Query: 'parsing'")
    result = query_engine.query("parsing", max_results=5)
    for node in result.nodes:
        score = result.scores.get(node.id, 0)
        print(f"    [{score:.2f}] {node.type.value}: {node.name}")

    # Find specific symbol
    print("\n  Find: 'GraphStore'")
    result = query_engine.find_definition("GraphStore")
    for node in result.nodes:
        print(f"    {node.type.value}: {node.name}")
        if hasattr(node, "file_id"):
            print(f"      File: {node.file_id}")

    # Clean up
    store.close()
    print("\n✅ Done!")


if __name__ == "__main__":
    main()
