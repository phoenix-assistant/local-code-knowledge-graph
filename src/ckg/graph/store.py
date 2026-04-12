"""Graph storage with NetworkX and SQLite persistence."""

import json
import sqlite3
from pathlib import Path
from typing import Any

import networkx as nx

from ckg.graph.models import (
    BaseNode,
    ClassNode,
    Edge,
    EdgeType,
    FileNode,
    FunctionNode,
    ImportNode,
    NodeType,
    VariableNode,
)


class GraphStore:
    """In-memory graph with SQLite persistence."""

    def __init__(self, db_path: Path | None = None):
        """Initialize graph store.

        Args:
            db_path: Path to SQLite database. If None, in-memory only.
        """
        self.graph = nx.DiGraph()
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

        if db_path:
            self._init_db()
            self._load_from_db()

    def _init_db(self) -> None:
        """Initialize SQLite database schema."""
        if not self.db_path:
            return

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                data JSON NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS edges (
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                type TEXT NOT NULL,
                data JSON,
                PRIMARY KEY (source_id, target_id, type),
                FOREIGN KEY (source_id) REFERENCES nodes(id) ON DELETE CASCADE,
                FOREIGN KEY (target_id) REFERENCES nodes(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
            CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type);
        """)
        self._conn.commit()

    def _load_from_db(self) -> None:
        """Load graph from SQLite database."""
        if not self._conn:
            return

        # Load nodes
        for row in self._conn.execute("SELECT * FROM nodes"):
            data = json.loads(row["data"])
            node = self._deserialize_node(row["type"], data)
            self.graph.add_node(node.id, **node.model_dump())

        # Load edges
        for row in self._conn.execute("SELECT * FROM edges"):
            metadata = json.loads(row["data"]) if row["data"] else {}
            self.graph.add_edge(
                row["source_id"],
                row["target_id"],
                type=row["type"],
                **metadata,
            )

    def _deserialize_node(self, node_type: str, data: dict[str, Any]) -> BaseNode:
        """Deserialize node from stored data."""
        type_map = {
            NodeType.FILE.value: FileNode,
            NodeType.FUNCTION.value: FunctionNode,
            NodeType.CLASS.value: ClassNode,
            NodeType.IMPORT.value: ImportNode,
            NodeType.VARIABLE.value: VariableNode,
        }
        cls = type_map.get(node_type, BaseNode)
        return cls(**data)

    def add_node(self, node: BaseNode) -> None:
        """Add or update a node."""
        self.graph.add_node(node.id, **node.model_dump())

        if self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO nodes (id, type, name, data, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (node.id, node.type.value, node.name, node.model_dump_json()),
            )
            self._conn.commit()

    def add_edge(self, edge: Edge) -> None:
        """Add or update an edge."""
        self.graph.add_edge(
            edge.source_id,
            edge.target_id,
            type=edge.type.value,
            **edge.metadata,
        )

        if self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO edges (source_id, target_id, type, data)
                VALUES (?, ?, ?, ?)
                """,
                (
                    edge.source_id,
                    edge.target_id,
                    edge.type.value,
                    json.dumps(edge.metadata) if edge.metadata else None,
                ),
            )
            self._conn.commit()

    def get_node(self, node_id: str) -> BaseNode | None:
        """Get a node by ID."""
        if node_id not in self.graph:
            return None
        data = dict(self.graph.nodes[node_id])
        return self._deserialize_node(data["type"], data)

    def get_nodes_by_type(self, node_type: NodeType) -> list[BaseNode]:
        """Get all nodes of a specific type."""
        nodes = []
        for _node_id, data in self.graph.nodes(data=True):
            if data.get("type") == node_type.value:
                nodes.append(self._deserialize_node(data["type"], data))
        return nodes

    def get_nodes_by_name(self, name: str, exact: bool = True) -> list[BaseNode]:
        """Get nodes by name."""
        nodes = []
        for _node_id, data in self.graph.nodes(data=True):
            if exact and data.get("name") == name or not exact and name.lower() in data.get("name", "").lower():
                nodes.append(self._deserialize_node(data["type"], data))
        return nodes

    def get_edges_from(self, node_id: str, edge_type: EdgeType | None = None) -> list[Edge]:
        """Get outgoing edges from a node."""
        edges = []
        for _, target_id, data in self.graph.out_edges(node_id, data=True):
            if edge_type is None or data.get("type") == edge_type.value:
                edges.append(
                    Edge(
                        source_id=node_id,
                        target_id=target_id,
                        type=EdgeType(data["type"]),
                        metadata={k: v for k, v in data.items() if k != "type"},
                    )
                )
        return edges

    def get_edges_to(self, node_id: str, edge_type: EdgeType | None = None) -> list[Edge]:
        """Get incoming edges to a node."""
        edges = []
        for source_id, _, data in self.graph.in_edges(node_id, data=True):
            if edge_type is None or data.get("type") == edge_type.value:
                edges.append(
                    Edge(
                        source_id=source_id,
                        target_id=node_id,
                        type=EdgeType(data["type"]),
                        metadata={k: v for k, v in data.items() if k != "type"},
                    )
                )
        return edges

    def remove_node(self, node_id: str) -> None:
        """Remove a node and its edges."""
        if node_id in self.graph:
            self.graph.remove_node(node_id)

        if self._conn:
            self._conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
            self._conn.execute(
                "DELETE FROM edges WHERE source_id = ? OR target_id = ?",
                (node_id, node_id),
            )
            self._conn.commit()

    def remove_file_nodes(self, file_path: str) -> None:
        """Remove all nodes associated with a file."""
        file_id = f"file:{file_path}"
        nodes_to_remove = [file_id]

        # Find all nodes belonging to this file
        for node_id, data in list(self.graph.nodes(data=True)):
            if data.get("file_id") == file_id:
                nodes_to_remove.append(node_id)

        for node_id in nodes_to_remove:
            self.remove_node(node_id)

    def node_count(self) -> int:
        """Get total number of nodes."""
        return self.graph.number_of_nodes()

    def edge_count(self) -> int:
        """Get total number of edges."""
        return self.graph.number_of_edges()

    def get_stats(self) -> dict[str, Any]:
        """Get graph statistics."""
        type_counts: dict[str, int] = {}
        for _, data in self.graph.nodes(data=True):
            t = data.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        edge_type_counts: dict[str, int] = {}
        for _, _, data in self.graph.edges(data=True):
            t = data.get("type", "unknown")
            edge_type_counts[t] = edge_type_counts.get(t, 0) + 1

        return {
            "total_nodes": self.node_count(),
            "total_edges": self.edge_count(),
            "node_types": type_counts,
            "edge_types": edge_type_counts,
        }

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
