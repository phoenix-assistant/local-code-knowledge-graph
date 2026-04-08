"""MCP server for Code Knowledge Graph."""

import json
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
)

from ckg.graph.models import NodeType
from ckg.graph.store import GraphStore
from ckg.indexing.indexer import CodeIndexer
from ckg.parsing.manager import ParserManager
from ckg.query.engine import QueryEngine


class MCPServer:
    """MCP server for Code Knowledge Graph."""

    def __init__(
        self,
        repo_path: Path,
        db_path: Path | None = None,
    ):
        """Initialize MCP server.

        Args:
            repo_path: Path to the repository to index
            db_path: Path to SQLite database for persistence
        """
        self.repo_path = repo_path
        self.db_path = db_path or repo_path / ".ckg" / "graph.db"

        # Initialize components
        self.store = GraphStore(db_path=self.db_path)
        self.parser_manager = ParserManager()
        self.indexer = CodeIndexer(repo_path, self.store, self.parser_manager)
        self.query_engine = QueryEngine(
            self.store,
            vector_path=repo_path / ".ckg" / "vectors",
        )

        # Create MCP server
        self.server = Server("ckg")
        self._register_tools()

    def _register_tools(self) -> None:
        """Register MCP tools."""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="ckg_query",
                    description="Search the code knowledge graph using natural language",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Natural language query about the codebase",
                            },
                            "type": {
                                "type": "string",
                                "enum": ["function", "class", "file", "import", "any"],
                                "description": "Filter results by type",
                                "default": "any",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of results",
                                "default": 10,
                            },
                        },
                        "required": ["query"],
                    },
                ),
                Tool(
                    name="ckg_find_definition",
                    description="Find the definition of a symbol (function, class, etc.)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Name of the symbol to find",
                            },
                        },
                        "required": ["symbol"],
                    },
                ),
                Tool(
                    name="ckg_find_references",
                    description="Find all references to a symbol",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Name of the symbol to find references for",
                            },
                        },
                        "required": ["symbol"],
                    },
                ),
                Tool(
                    name="ckg_file_summary",
                    description="Get a summary of all symbols in a file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the file (relative to repo root)",
                            },
                        },
                        "required": ["file_path"],
                    },
                ),
                Tool(
                    name="ckg_graph_stats",
                    description="Get statistics about the code knowledge graph",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    },
                ),
                Tool(
                    name="ckg_index",
                    description="Index or re-index the codebase",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "incremental": {
                                "type": "boolean",
                                "description": "Perform incremental update instead of full re-index",
                                "default": True,
                            },
                        },
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            try:
                if name == "ckg_query":
                    return self._handle_query(arguments)
                elif name == "ckg_find_definition":
                    return self._handle_find_definition(arguments)
                elif name == "ckg_find_references":
                    return self._handle_find_references(arguments)
                elif name == "ckg_file_summary":
                    return self._handle_file_summary(arguments)
                elif name == "ckg_graph_stats":
                    return self._handle_graph_stats()
                elif name == "ckg_index":
                    return self._handle_index(arguments)
                else:
                    return [TextContent(type="text", text=f"Unknown tool: {name}")]
            except Exception as e:
                return [TextContent(type="text", text=f"Error: {str(e)}")]

    def _handle_query(self, args: dict[str, Any]) -> list[TextContent]:
        """Handle ckg_query tool."""
        query = args["query"]
        node_type = args.get("type", "any")
        max_results = args.get("max_results", 10)

        node_types = None
        if node_type != "any":
            type_map = {
                "function": NodeType.FUNCTION,
                "class": NodeType.CLASS,
                "file": NodeType.FILE,
                "import": NodeType.IMPORT,
            }
            if node_type in type_map:
                node_types = [type_map[node_type]]

        result = self.query_engine.query(
            query_text=query,
            node_types=node_types,
            max_results=max_results,
        )

        return [TextContent(type="text", text=result.context or "No results found")]

    def _handle_find_definition(self, args: dict[str, Any]) -> list[TextContent]:
        """Handle ckg_find_definition tool."""
        symbol = args["symbol"]
        result = self.query_engine.find_definition(symbol)
        return [TextContent(type="text", text=result.context or f"No definition found for '{symbol}'")]

    def _handle_find_references(self, args: dict[str, Any]) -> list[TextContent]:
        """Handle ckg_find_references tool."""
        symbol = args["symbol"]

        # First find the symbol
        definition = self.query_engine.find_definition(symbol)
        if not definition.nodes:
            return [TextContent(type="text", text=f"Symbol '{symbol}' not found")]

        # Find references to first result
        result = self.query_engine.find_references(definition.nodes[0].id)
        return [TextContent(type="text", text=result.context or f"No references found for '{symbol}'")]

    def _handle_file_summary(self, args: dict[str, Any]) -> list[TextContent]:
        """Handle ckg_file_summary tool."""
        file_path = args["file_path"]
        result = self.query_engine.get_file_summary(file_path)

        if not result.nodes:
            return [TextContent(type="text", text=f"No symbols found in '{file_path}'")]

        summary = f"File: {file_path}\n"
        summary += f"Functions: {result.metadata.get('functions', 0)}\n"
        summary += f"Classes: {result.metadata.get('classes', 0)}\n"
        summary += f"Imports: {result.metadata.get('imports', 0)}\n\n"
        summary += result.context

        return [TextContent(type="text", text=summary)]

    def _handle_graph_stats(self) -> list[TextContent]:
        """Handle ckg_graph_stats tool."""
        stats = self.store.get_stats()

        output = "# Code Knowledge Graph Statistics\n\n"
        output += f"Total Nodes: {stats['total_nodes']}\n"
        output += f"Total Edges: {stats['total_edges']}\n\n"
        output += "## Node Types:\n"
        for node_type, count in stats.get("node_types", {}).items():
            output += f"- {node_type}: {count}\n"
        output += "\n## Edge Types:\n"
        for edge_type, count in stats.get("edge_types", {}).items():
            output += f"- {edge_type}: {count}\n"

        return [TextContent(type="text", text=output)]

    def _handle_index(self, args: dict[str, Any]) -> list[TextContent]:
        """Handle ckg_index tool."""
        incremental = args.get("incremental", True)

        if incremental:
            stats = self.indexer.index_incremental()
            output = f"Incremental index complete:\n"
            output += f"- Files added: {stats.get('files_added', 0)}\n"
            output += f"- Files modified: {stats.get('files_modified', 0)}\n"
            output += f"- Files deleted: {stats.get('files_deleted', 0)}\n"
        else:
            stats = self.indexer.index_full()
            output = f"Full index complete:\n"
            output += f"- Files processed: {stats.get('files_processed', 0)}\n"
            output += f"- Functions: {stats.get('functions', 0)}\n"
            output += f"- Classes: {stats.get('classes', 0)}\n"

        # Re-index vectors
        vector_count = self.query_engine.index_vectors()
        output += f"- Vector embeddings: {vector_count}\n"

        return [TextContent(type="text", text=output)]

    async def run(self) -> None:
        """Run the MCP server."""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )


async def main() -> None:
    """Main entry point for MCP server."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m ckg.mcp.server <repo_path>", file=sys.stderr)
        sys.exit(1)

    repo_path = Path(sys.argv[1]).resolve()
    if not repo_path.exists():
        print(f"Repository path does not exist: {repo_path}", file=sys.stderr)
        sys.exit(1)

    server = MCPServer(repo_path)
    await server.run()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
