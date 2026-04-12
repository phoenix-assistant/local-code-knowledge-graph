"""Tests for graph store and traversal."""


import pytest

from ckg.graph.models import (
    ClassNode,
    Edge,
    EdgeType,
    FileNode,
    FunctionNode,
    NodeType,
)
from ckg.graph.store import GraphStore
from ckg.graph.traversal import GraphTraversal


class TestGraphStore:
    """Tests for GraphStore."""

    @pytest.fixture
    def store(self):
        return GraphStore()

    @pytest.fixture
    def persistent_store(self, tmp_path):
        db_path = tmp_path / "test.db"
        return GraphStore(db_path=db_path)

    def test_add_and_get_node(self, store):
        from datetime import datetime, timezone

        file_node = FileNode(
            id="file:test.py",
            name="test.py",
            path="test.py",
            language="python",
            last_modified=datetime.now(tz=timezone.utc),
        )
        store.add_node(file_node)

        retrieved = store.get_node("file:test.py")
        assert retrieved is not None
        assert retrieved.name == "test.py"
        assert retrieved.type == NodeType.FILE

    def test_add_and_get_edge(self, store):
        from datetime import datetime, timezone

        # Add nodes first
        file_node = FileNode(
            id="file:test.py",
            name="test.py",
            path="test.py",
            language="python",
            last_modified=datetime.now(tz=timezone.utc),
        )
        func_node = FunctionNode(
            id="func:test.py:module:hello",
            name="hello",
            file_id="file:test.py",
            start_line=1,
            end_line=3,
        )
        store.add_node(file_node)
        store.add_node(func_node)

        # Add edge
        edge = Edge(
            source_id="file:test.py",
            target_id="func:test.py:module:hello",
            type=EdgeType.DEFINES,
        )
        store.add_edge(edge)

        # Check edges
        edges = store.get_edges_from("file:test.py")
        assert len(edges) == 1
        assert edges[0].type == EdgeType.DEFINES

    def test_get_nodes_by_type(self, store):
        from datetime import datetime, timezone

        file_node = FileNode(
            id="file:test.py",
            name="test.py",
            path="test.py",
            language="python",
            last_modified=datetime.now(tz=timezone.utc),
        )
        func_node = FunctionNode(
            id="func:test.py:module:hello",
            name="hello",
            file_id="file:test.py",
            start_line=1,
            end_line=3,
        )
        store.add_node(file_node)
        store.add_node(func_node)

        files = store.get_nodes_by_type(NodeType.FILE)
        assert len(files) == 1
        assert files[0].name == "test.py"

        functions = store.get_nodes_by_type(NodeType.FUNCTION)
        assert len(functions) == 1

    def test_remove_node(self, store):
        from datetime import datetime, timezone

        file_node = FileNode(
            id="file:test.py",
            name="test.py",
            path="test.py",
            language="python",
            last_modified=datetime.now(tz=timezone.utc),
        )
        store.add_node(file_node)
        assert store.node_count() == 1

        store.remove_node("file:test.py")
        assert store.node_count() == 0

    def test_persistence(self, tmp_path):
        from datetime import datetime, timezone

        db_path = tmp_path / "test.db"

        # Create store and add data
        store1 = GraphStore(db_path=db_path)
        file_node = FileNode(
            id="file:test.py",
            name="test.py",
            path="test.py",
            language="python",
            last_modified=datetime.now(tz=timezone.utc),
        )
        store1.add_node(file_node)
        store1.close()

        # Reopen and check data persists
        store2 = GraphStore(db_path=db_path)
        assert store2.node_count() == 1
        retrieved = store2.get_node("file:test.py")
        assert retrieved is not None
        assert retrieved.name == "test.py"
        store2.close()


class TestGraphTraversal:
    """Tests for GraphTraversal."""

    @pytest.fixture
    def store_with_data(self):
        from datetime import datetime, timezone

        store = GraphStore()

        # Add file
        file_node = FileNode(
            id="file:test.py",
            name="test.py",
            path="test.py",
            language="python",
            last_modified=datetime.now(tz=timezone.utc),
        )
        store.add_node(file_node)

        # Add class
        class_node = ClassNode(
            id="class:test.py:MyClass",
            name="MyClass",
            file_id="file:test.py",
            start_line=1,
            end_line=20,
        )
        store.add_node(class_node)

        # Add functions
        func1 = FunctionNode(
            id="func:test.py:module:helper",
            name="helper",
            file_id="file:test.py",
            start_line=22,
            end_line=25,
        )
        func2 = FunctionNode(
            id="func:test.py:MyClass:method",
            name="method",
            file_id="file:test.py",
            class_id="class:test.py:MyClass",
            is_method=True,
            start_line=5,
            end_line=10,
        )
        store.add_node(func1)
        store.add_node(func2)

        # Add edges
        store.add_edge(Edge(
            source_id="file:test.py",
            target_id="class:test.py:MyClass",
            type=EdgeType.DEFINES,
        ))
        store.add_edge(Edge(
            source_id="file:test.py",
            target_id="func:test.py:module:helper",
            type=EdgeType.DEFINES,
        ))
        store.add_edge(Edge(
            source_id="class:test.py:MyClass",
            target_id="func:test.py:MyClass:method",
            type=EdgeType.CONTAINS,
        ))
        store.add_edge(Edge(
            source_id="func:test.py:MyClass:method",
            target_id="func:test.py:module:helper",
            type=EdgeType.CALLS,
        ))

        return store

    def test_get_related_symbols(self, store_with_data):
        traversal = GraphTraversal(store_with_data)

        related = traversal.get_related_symbols("func:test.py:MyClass:method", max_depth=2)
        assert len(related) > 0

        # Should include the helper function
        related_ids = {node.id for node, _ in related}
        assert "func:test.py:module:helper" in related_ids

    def test_find_callers(self, store_with_data):
        traversal = GraphTraversal(store_with_data)

        callers = traversal.find_callers("func:test.py:module:helper")
        assert len(callers) == 1
        assert callers[0].name == "method"

    def test_find_callees(self, store_with_data):
        traversal = GraphTraversal(store_with_data)

        callees = traversal.find_callees("func:test.py:MyClass:method")
        assert len(callees) == 1
        assert callees[0].name == "helper"

    def test_get_file_symbols(self, store_with_data):
        traversal = GraphTraversal(store_with_data)

        symbols = traversal.get_file_symbols("file:test.py")

        assert len(symbols["classes"]) == 1
        assert len(symbols["functions"]) == 1  # Only module-level function
        assert symbols["classes"][0].name == "MyClass"
