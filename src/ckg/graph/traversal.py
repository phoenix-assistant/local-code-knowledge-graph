"""Graph traversal algorithms for code knowledge graph."""

from collections import deque
from typing import Callable

import networkx as nx

from ckg.graph.models import BaseNode, EdgeType, NodeType
from ckg.graph.store import GraphStore


class GraphTraversal:
    """Graph traversal and analysis utilities."""

    def __init__(self, store: GraphStore):
        """Initialize with a graph store."""
        self.store = store

    def get_related_symbols(
        self,
        node_id: str,
        max_depth: int = 2,
        edge_types: list[EdgeType] | None = None,
    ) -> list[tuple[BaseNode, int]]:
        """Get symbols related to a node via graph traversal.

        Args:
            node_id: Starting node ID
            max_depth: Maximum traversal depth
            edge_types: Types of edges to follow (None = all)

        Returns:
            List of (node, depth) tuples
        """
        if node_id not in self.store.graph:
            return []

        visited: set[str] = {node_id}
        result: list[tuple[BaseNode, int]] = []
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])

        while queue:
            current_id, depth = queue.popleft()

            if depth > 0:
                node = self.store.get_node(current_id)
                if node:
                    result.append((node, depth))

            if depth >= max_depth:
                continue

            # Follow outgoing edges
            for _, neighbor_id, data in self.store.graph.out_edges(current_id, data=True):
                if neighbor_id in visited:
                    continue
                if edge_types and EdgeType(data["type"]) not in edge_types:
                    continue
                visited.add(neighbor_id)
                queue.append((neighbor_id, depth + 1))

            # Follow incoming edges
            for neighbor_id, _, data in self.store.graph.in_edges(current_id, data=True):
                if neighbor_id in visited:
                    continue
                if edge_types and EdgeType(data["type"]) not in edge_types:
                    continue
                visited.add(neighbor_id)
                queue.append((neighbor_id, depth + 1))

        return result

    def find_callers(self, function_id: str, max_depth: int = 3) -> list[BaseNode]:
        """Find all functions that call a given function."""
        callers = []
        visited: set[str] = {function_id}
        queue: deque[tuple[str, int]] = deque([(function_id, 0)])

        while queue:
            current_id, depth = queue.popleft()

            for source_id, _, data in self.store.graph.in_edges(current_id, data=True):
                if data.get("type") != EdgeType.CALLS.value:
                    continue
                if source_id in visited:
                    continue

                visited.add(source_id)
                node = self.store.get_node(source_id)
                if node:
                    callers.append(node)

                if depth < max_depth:
                    queue.append((source_id, depth + 1))

        return callers

    def find_callees(self, function_id: str, max_depth: int = 3) -> list[BaseNode]:
        """Find all functions called by a given function."""
        callees = []
        visited: set[str] = {function_id}
        queue: deque[tuple[str, int]] = deque([(function_id, 0)])

        while queue:
            current_id, depth = queue.popleft()

            for _, target_id, data in self.store.graph.out_edges(current_id, data=True):
                if data.get("type") != EdgeType.CALLS.value:
                    continue
                if target_id in visited:
                    continue

                visited.add(target_id)
                node = self.store.get_node(target_id)
                if node:
                    callees.append(node)

                if depth < max_depth:
                    queue.append((target_id, depth + 1))

        return callees

    def find_inheritance_chain(self, class_id: str) -> list[BaseNode]:
        """Find inheritance chain for a class."""
        chain = []
        current_id = class_id

        while True:
            edges = self.store.get_edges_from(current_id, EdgeType.INHERITS)
            if not edges:
                break

            parent_id = edges[0].target_id
            parent = self.store.get_node(parent_id)
            if parent:
                chain.append(parent)
                current_id = parent_id
            else:
                break

        return chain

    def find_subclasses(self, class_id: str, recursive: bool = True) -> list[BaseNode]:
        """Find all subclasses of a class."""
        subclasses = []
        visited: set[str] = {class_id}
        queue: deque[str] = deque([class_id])

        while queue:
            current_id = queue.popleft()

            for source_id, _, data in self.store.graph.in_edges(current_id, data=True):
                if data.get("type") != EdgeType.INHERITS.value:
                    continue
                if source_id in visited:
                    continue

                visited.add(source_id)
                node = self.store.get_node(source_id)
                if node:
                    subclasses.append(node)
                    if recursive:
                        queue.append(source_id)

        return subclasses

    def get_file_symbols(self, file_id: str) -> dict[str, list[BaseNode]]:
        """Get all symbols defined in a file."""
        symbols: dict[str, list[BaseNode]] = {
            "functions": [],
            "classes": [],
            "imports": [],
            "variables": [],
        }

        for _, target_id, data in self.store.graph.out_edges(file_id, data=True):
            node = self.store.get_node(target_id)
            if not node:
                continue

            if node.type == NodeType.FUNCTION:
                symbols["functions"].append(node)
            elif node.type == NodeType.CLASS:
                symbols["classes"].append(node)
            elif node.type == NodeType.IMPORT:
                symbols["imports"].append(node)
            elif node.type == NodeType.VARIABLE:
                symbols["variables"].append(node)

        return symbols

    def find_dependencies(self, file_id: str) -> list[str]:
        """Find modules that a file depends on (via imports)."""
        deps = set()
        for edge in self.store.get_edges_from(file_id, EdgeType.IMPORTS):
            import_node = self.store.get_node(edge.target_id)
            if import_node and hasattr(import_node, "module"):
                deps.add(import_node.module)  # type: ignore
        return sorted(deps)

    def find_dependents(self, module_name: str) -> list[BaseNode]:
        """Find files that import a given module."""
        files = []
        import_nodes = [
            n
            for n in self.store.get_nodes_by_type(NodeType.IMPORT)
            if hasattr(n, "module") and n.module == module_name  # type: ignore
        ]

        for import_node in import_nodes:
            if hasattr(import_node, "file_id"):
                file_node = self.store.get_node(import_node.file_id)  # type: ignore
                if file_node:
                    files.append(file_node)

        return files

    def get_complexity_score(self, node_id: str) -> float:
        """Calculate complexity score based on connections."""
        if node_id not in self.store.graph:
            return 0.0

        in_degree = self.store.graph.in_degree(node_id)
        out_degree = self.store.graph.out_degree(node_id)

        # Simple formula: more connections = more complexity
        return (in_degree + out_degree) / 2.0

    def find_central_nodes(self, top_k: int = 10) -> list[tuple[BaseNode, float]]:
        """Find most central nodes using PageRank."""
        if self.store.node_count() == 0:
            return []

        pagerank = nx.pagerank(self.store.graph)
        sorted_nodes = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)

        result = []
        for node_id, score in sorted_nodes[:top_k]:
            node = self.store.get_node(node_id)
            if node:
                result.append((node, score))

        return result

    def search_nodes(
        self,
        predicate: Callable[[BaseNode], bool],
        node_types: list[NodeType] | None = None,
    ) -> list[BaseNode]:
        """Search nodes matching a predicate."""
        results = []
        for node_id, data in self.store.graph.nodes(data=True):
            if node_types and data.get("type") not in [t.value for t in node_types]:
                continue
            node = self.store.get_node(node_id)
            if node and predicate(node):
                results.append(node)
        return results
