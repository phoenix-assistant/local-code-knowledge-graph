# Local Code Knowledge Graph (CKG)

[![CI](https://github.com/phoenix-assistant/local-code-knowledge-graph/actions/workflows/ci.yml/badge.svg)](https://github.com/phoenix-assistant/local-code-knowledge-graph/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ckg)](https://pypi.org/project/ckg/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Privacy-first Graph RAG for codebases. Build a knowledge graph of your code with real-time watching, incremental indexing, and agent integration via MCP.

## Features

- 🌲 **Tree-sitter Parsing** — Accurate AST parsing for Python, TypeScript/JavaScript, Go, Rust, and more
- 🕸️ **Knowledge Graph** — Functions, classes, imports, and dependencies as nodes/edges
- ⚡ **Incremental Indexing** — Only re-index changed files (git diff aware)
- 👁️ **Real-time Watching** — Live updates as you code
- 🔍 **Graph RAG** — Query expansion via graph traversal before vector search
- 🤖 **MCP Server** — Integration with Claude Code and other agents
- 🖥️ **CLI** — Simple commands for indexing, querying, and watching

## Installation

```bash
pip install ckg
```

Or with Docker:

```bash
docker pull ghcr.io/phoenix-assistant/ckg
```

## Quick Start

```bash
# Index your codebase
ckg index

# Search for symbols
ckg query "authentication handler"

# Find a specific function
ckg find "process_payment"

# Watch for changes
ckg watch

# Start MCP server for Claude Code
ckg serve
```

## CLI Commands

### `ckg index`

Index the codebase into the knowledge graph.

```bash
ckg index              # Incremental index (default)
ckg index --full       # Force full re-index
ckg --repo /path/to/repo index  # Index specific repo
```

### `ckg query`

Search the knowledge graph using natural language.

```bash
ckg query "authentication"
ckg query "error handling" --type function
ckg query "database models" --limit 20
```

### `ckg find`

Find a specific symbol definition.

```bash
ckg find "UserService"
ckg find "handle_request"
```

### `ckg file`

Show all symbols in a file.

```bash
ckg file "src/auth/handler.py"
```

### `ckg stats`

Show graph statistics.

```bash
ckg stats
```

### `ckg watch`

Watch for file changes and update index in real-time.

```bash
ckg watch
ckg watch --verbose
```

### `ckg graph`

Export graph in DOT format for visualization.

```bash
ckg graph > codebase.dot
dot -Tpng codebase.dot -o codebase.png
```

### `ckg serve`

Start MCP server for agent integration.

```bash
ckg serve
```

## MCP Integration

CKG provides an MCP (Model Context Protocol) server for integration with AI agents like Claude Code.

### Available Tools

| Tool | Description |
|------|-------------|
| `ckg_query` | Search the code knowledge graph using natural language |
| `ckg_find_definition` | Find the definition of a symbol |
| `ckg_find_references` | Find all references to a symbol |
| `ckg_file_summary` | Get a summary of all symbols in a file |
| `ckg_graph_stats` | Get statistics about the knowledge graph |
| `ckg_index` | Index or re-index the codebase |

### Claude Code Configuration

Add to your Claude Code MCP config:

```json
{
  "mcpServers": {
    "ckg": {
      "command": "ckg",
      "args": ["--repo", "/path/to/your/repo", "serve"]
    }
  }
}
```

## Graph Schema

### Nodes

| Type | Description |
|------|-------------|
| `File` | Source file with path, language, modification time |
| `Function` | Function/method with signature, docstring, location |
| `Class` | Class with docstring, bases, decorators |
| `Import` | Import statement with module and items |
| `Variable` | Module/class-level variable with type hint |

### Edges

| Type | Description |
|------|-------------|
| `DEFINES` | File → Function/Class |
| `CONTAINS` | Class → Method |
| `IMPORTS` | File → Import |
| `CALLS` | Function → Function |
| `INHERITS` | Class → Class |
| `USES` | Function → Variable |

## Supported Languages

**Priority 0 (Full Support)**
- Python (.py, .pyw, .pyi)
- TypeScript (.ts, .tsx, .mts, .cts)
- JavaScript (.js, .jsx, .mjs, .cjs)
- Go (.go)
- Rust (.rs)

**Priority 1 (Coming Soon)**
- Java
- C/C++
- Ruby
- PHP

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 Local Code Knowledge Graph                   │
├─────────────────────────────────────────────────────────────┤
│  Interface Layer                                             │
│  ├── CLI (ckg index/query/watch/graph/stats)                │
│  ├── MCP Server (for Claude Code)                           │
│  └── Python SDK                                              │
├─────────────────────────────────────────────────────────────┤
│  Query Engine                                                │
│  ├── Graph traversal (find related symbols)                 │
│  ├── Vector search (semantic similarity)                    │
│  └── Hybrid ranking (graph + vector + recency)              │
├─────────────────────────────────────────────────────────────┤
│  Indexing Engine                                             │
│  ├── Tree-sitter parsing (20+ languages)                    │
│  ├── Incremental updates (git diff aware)                   │
│  └── Real-time watch (watchdog)                             │
├─────────────────────────────────────────────────────────────┤
│  Storage                                                     │
│  ├── Graph: NetworkX + SQLite                               │
│  └── Vectors: ChromaDB                                       │
└─────────────────────────────────────────────────────────────┘
```

## Python SDK

```python
from pathlib import Path
from ckg import CodeIndexer, GraphStore, QueryEngine

# Initialize
repo_path = Path("/path/to/repo")
store = GraphStore(db_path=repo_path / ".ckg" / "graph.db")
indexer = CodeIndexer(repo_path, store)
query_engine = QueryEngine(store)

# Index
indexer.index_full()
query_engine.index_vectors()

# Query
result = query_engine.query("authentication handler")
for node in result.nodes:
    print(f"{node.type}: {node.name}")

# Find definition
result = query_engine.find_definition("UserService")

# Get file summary
result = query_engine.get_file_summary("src/auth/handler.py")
```

## Docker

```bash
# Run with docker-compose
cd docker
REPO_PATH=/path/to/repo docker-compose up ckg

# Watch mode
REPO_PATH=/path/to/repo docker-compose up ckg-watch

# MCP server
REPO_PATH=/path/to/repo docker-compose up ckg-mcp
```

## Development

```bash
# Clone
git clone https://github.com/phoenix-assistant/local-code-knowledge-graph.git
cd local-code-knowledge-graph

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src tests

# Type check
mypy src
```

## How It Works

1. **Parsing**: Tree-sitter parses source files into ASTs, extracting functions, classes, imports, and their relationships.

2. **Graph Construction**: Symbols become nodes, relationships become edges. The graph is stored in SQLite for persistence.

3. **Vector Indexing**: Symbol names, signatures, and docstrings are embedded using sentence-transformers and stored in ChromaDB.

4. **Query Processing**: 
   - Natural language queries → vector search for semantic matching
   - Graph traversal expands results to related symbols
   - Hybrid ranking combines vector similarity, graph centrality, and recency

5. **Real-time Updates**: Watchdog monitors file changes, triggering incremental re-indexing only for modified files.

## Why CKG?

- **Privacy-first**: Everything runs locally. Your code never leaves your machine.
- **Fast**: Incremental indexing and efficient graph queries.
- **Accurate**: Tree-sitter provides precise AST parsing, not regex heuristics.
- **Agent-ready**: MCP integration for AI coding assistants.
- **Language-aware**: Proper understanding of each language's semantics.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please read our [contributing guidelines](CONTRIBUTING.md) first.
