"""Vector store for semantic search using ChromaDB."""

from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings


class VectorStore:
    """ChromaDB-based vector store for code embeddings."""

    def __init__(
        self,
        persist_path: Path | None = None,
        collection_name: str = "code_embeddings",
    ):
        """Initialize vector store.

        Args:
            persist_path: Path to persist the database. None for in-memory.
            collection_name: Name of the ChromaDB collection.
        """
        if persist_path:
            persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(persist_path),
                settings=Settings(anonymized_telemetry=False),
            )
        else:
            self._client = chromadb.Client(Settings(anonymized_telemetry=False))

        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        """Add documents to the vector store.

        Args:
            ids: Unique identifiers for each document
            documents: Document texts to embed
            metadatas: Optional metadata for each document
        """
        if not ids:
            return

        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    def search(
        self,
        query: str,
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar documents.

        Args:
            query: Search query text
            n_results: Maximum number of results
            where: Optional filter conditions

        Returns:
            List of results with id, document, metadata, and distance
        """
        results = self._collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        output = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                output.append({
                    "id": doc_id,
                    "document": results["documents"][0][i] if results["documents"] else None,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else None,
                    "distance": results["distances"][0][i] if results["distances"] else None,
                })

        return output

    def delete(self, ids: list[str]) -> None:
        """Delete documents by ID."""
        if ids:
            self._collection.delete(ids=ids)

    def delete_where(self, where: dict[str, Any]) -> None:
        """Delete documents matching a filter."""
        self._collection.delete(where=where)

    def count(self) -> int:
        """Get total number of documents."""
        return self._collection.count()

    def get(self, ids: list[str]) -> list[dict[str, Any]]:
        """Get documents by ID."""
        results = self._collection.get(
            ids=ids,
            include=["documents", "metadatas"],
        )

        output = []
        if results["ids"]:
            for i, doc_id in enumerate(results["ids"]):
                output.append({
                    "id": doc_id,
                    "document": results["documents"][i] if results["documents"] else None,
                    "metadata": results["metadatas"][i] if results["metadatas"] else None,
                })

        return output
