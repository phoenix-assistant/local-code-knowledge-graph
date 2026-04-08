"""Graph RAG query engine combining graph traversal and vector search."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ckg.graph.models import BaseNode, NodeType
from ckg.graph.store import GraphStore
from ckg.graph.traversal import GraphTraversal
from ckg.query.vector_store import VectorStore


@dataclass
class QueryResult:
    """Result of a query."""

    nodes: list[BaseNode] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    context: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class QueryEngine:
    """Graph RAG query engine."""

    def __init__(
        self,
        store: GraphStore,
        vector_store: VectorStore | None = None,
        vector_path: Path | None = None,
    ):
        """Initialize query engine.

        Args:
            store: Graph store with indexed code
            vector_store: Optional pre-initialized vector store
            vector_path: Path for vector store persistence
        """
        self.store = store
        self.traversal = GraphTraversal(store)
        self.vector_store = vector_store or VectorStore(persist_path=vector_path)

        self._indexed_for_vectors = False

    def index_vectors(self) -> int:
        """Index all nodes into vector store for semantic search.

        Returns:
            Number of nodes indexed
        """
        ids = []
        documents = []
        metadatas = []

        for node_id, data in self.store.graph.nodes(data=True):
            node = self.store.get_node(node_id)
            if not node:
                continue

            # Create searchable document from node
            doc = self._node_to_document(node)
            if doc:
                ids.append(node_id)
                documents.append(doc)
                metadatas.append({
                    "type": node.type.value,
                    "name": node.name,
                })

        if ids:
            self.vector_store.add(ids=ids, documents=documents, metadatas=metadatas)

        self._indexed_for_vectors = True
        return len(ids)

    def _node_to_document(self, node: BaseNode) -> str:
        """Convert a node to a searchable document."""
        parts = [node.name]

        if node.type == NodeType.FUNCTION:
            if hasattr(node, "signature") and node.signature:  # type: ignore
                parts.append(node.signature)  # type: ignore
            if hasattr(node, "docstring") and node.docstring:  # type: ignore
                parts.append(node.docstring)  # type: ignore

        elif node.type == NodeType.CLASS:
            if hasattr(node, "docstring") and node.docstring:  # type: ignore
                parts.append(node.docstring)  # type: ignore

        elif node.type == NodeType.FILE:
            if hasattr(node, "path"):
                parts.append(node.path)  # type: ignore

        return " ".join(parts)

    def query(
        self,
        query_text: str,
        node_types: list[NodeType] | None = None,
        max_results: int = 10,
        expand_graph: bool = True,
        graph_depth: int = 1,
    ) -> QueryResult:
        """Execute a hybrid query combining vector search and graph traversal.

        Args:
            query_text: Natural language query
            node_types: Optional filter for node types
            max_results: Maximum number of results
            expand_graph: Whether to expand results via graph traversal
            graph_depth: Depth for graph expansion

        Returns:
            QueryResult with matching nodes and context
        """
        result = QueryResult()

        # Step 1: Vector search for semantic similarity
        where = None
        if node_types:
            where = {"type": {"$in": [t.value for t in node_types]}}

        vector_results = self.vector_store.search(
            query=query_text,
            n_results=max_results,
            where=where,
        )

        seen_ids: set[str] = set()

        for vr in vector_results:
            node = self.store.get_node(vr["id"])
            if node:
                result.nodes.append(node)
                # Convert distance to similarity score (cosine distance)
                result.scores[node.id] = 1.0 - (vr["distance"] or 0.0)
                seen_ids.add(node.id)

        # Step 2: Graph expansion
        if expand_graph and result.nodes:
            expanded_nodes = []
            for node in result.nodes[:5]:  # Expand top 5 results
                related = self.traversal.get_related_symbols(
                    node.id,
                    max_depth=graph_depth,
                )
                for related_node, depth in related:
                    if related_node.id not in seen_ids:
                        expanded_nodes.append(related_node)
                        # Score based on depth (closer = higher score)
                        base_score = result.scores.get(node.id, 0.5)
                        result.scores[related_node.id] = base_score * (0.5 ** depth)
                        seen_ids.add(related_node.id)

            result.nodes.extend(expanded_nodes)

        # Sort by score
        result.nodes.sort(key=lambda n: result.scores.get(n.id, 0), reverse=True)
        result.nodes = result.nodes[:max_results]

        # Generate context
        result.context = self._generate_context(result.nodes)
        result.metadata = {
            "query": query_text,
            "total_results": len(result.nodes),
            "vector_results": len(vector_results),
        }

        return result

    def find_symbol(self, name: str, exact: bool = False) -> QueryResult:
        """Find a symbol by name.

        Args:
            name: Symbol name to search for
            exact: Whether to require exact match

        Returns:
            QueryResult with matching nodes
        """
        result = QueryResult()
        nodes = self.store.get_nodes_by_name(name, exact=exact)

        for node in nodes:
            result.nodes.append(node)
            result.scores[node.id] = 1.0 if exact else 0.9

        result.context = self._generate_context(result.nodes)
        return result

    def find_definition(self, symbol_name: str) -> QueryResult:
        """Find the definition of a symbol.

        Args:
            symbol_name: Name of the symbol to find

        Returns:
            QueryResult with definition nodes
        """
        result = QueryResult()

        # Search for functions and classes with this name
        for node in self.store.get_nodes_by_name(symbol_name, exact=True):
            if node.type in (NodeType.FUNCTION, NodeType.CLASS):
                result.nodes.append(node)
                result.scores[node.id] = 1.0

        result.context = self._generate_context(result.nodes)
        return result

    def find_references(self, symbol_id: str, max_results: int = 20) -> QueryResult:
        """Find all references to a symbol.

        Args:
            symbol_id: ID of the symbol to find references to
            max_results: Maximum number of references

        Returns:
            QueryResult with referencing nodes
        """
        result = QueryResult()

        # Find callers for functions
        node = self.store.get_node(symbol_id)
        if not node:
            return result

        if node.type == NodeType.FUNCTION:
            callers = self.traversal.find_callers(symbol_id)
            for caller in callers[:max_results]:
                result.nodes.append(caller)
                result.scores[caller.id] = 0.8

        elif node.type == NodeType.CLASS:
            # Find subclasses and usages
            subclasses = self.traversal.find_subclasses(symbol_id)
            for subclass in subclasses[:max_results]:
                result.nodes.append(subclass)
                result.scores[subclass.id] = 0.8

        result.context = self._generate_context(result.nodes)
        return result

    def get_file_summary(self, file_path: str) -> QueryResult:
        """Get a summary of symbols in a file.

        Args:
            file_path: Path to the file

        Returns:
            QueryResult with file symbols
        """
        result = QueryResult()
        file_id = f"file:{file_path}"

        symbols = self.traversal.get_file_symbols(file_id)

        for category, nodes in symbols.items():
            for node in nodes:
                result.nodes.append(node)
                result.scores[node.id] = 1.0

        result.context = self._generate_context(result.nodes)
        result.metadata = {
            "file_path": file_path,
            "functions": len(symbols.get("functions", [])),
            "classes": len(symbols.get("classes", [])),
            "imports": len(symbols.get("imports", [])),
        }

        return result

    def _generate_context(self, nodes: list[BaseNode], max_length: int = 4000) -> str:
        """Generate context string from nodes for LLM consumption."""
        parts = []
        current_length = 0

        for node in nodes:
            node_text = self._format_node(node)
            if current_length + len(node_text) > max_length:
                break
            parts.append(node_text)
            current_length += len(node_text)

        return "\n\n".join(parts)

    def _format_node(self, node: BaseNode) -> str:
        """Format a node for context output."""
        lines = [f"# {node.type.value.upper()}: {node.name}"]

        if node.type == NodeType.FUNCTION:
            if hasattr(node, "signature"):
                lines.append(f"Signature: {node.signature}")  # type: ignore
            if hasattr(node, "file_id"):
                lines.append(f"File: {node.file_id}")  # type: ignore
            if hasattr(node, "start_line"):
                lines.append(f"Lines: {node.start_line}-{node.end_line}")  # type: ignore
            if hasattr(node, "docstring") and node.docstring:  # type: ignore
                lines.append(f"Docstring: {node.docstring}")  # type: ignore

        elif node.type == NodeType.CLASS:
            if hasattr(node, "file_id"):
                lines.append(f"File: {node.file_id}")  # type: ignore
            if hasattr(node, "bases") and node.bases:  # type: ignore
                lines.append(f"Bases: {', '.join(node.bases)}")  # type: ignore
            if hasattr(node, "docstring") and node.docstring:  # type: ignore
                lines.append(f"Docstring: {node.docstring}")  # type: ignore

        elif node.type == NodeType.FILE:
            if hasattr(node, "path"):
                lines.append(f"Path: {node.path}")  # type: ignore
            if hasattr(node, "language"):
                lines.append(f"Language: {node.language}")  # type: ignore

        return "\n".join(lines)
