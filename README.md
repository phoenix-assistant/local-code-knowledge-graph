# Local Code Knowledge Graph

> **One-liner:** `grep` that understands your code—locally, privately, in real-time.

## Problem

**Persona:** Marcus, staff engineer at a Series B startup with a 500k LOC monorepo

**Pain:**
- Onboards 2 new engineers/month who ask "where does X happen?" constantly
- Code search (grep, ripgrep) finds text but not relationships ("what calls this?", "what depends on this?")
- GitHub Copilot suggests patterns that don't match their codebase conventions
- Existing code intel tools (Sourcegraph) require server setup, are overkill for his 15-person team
- When he asks Claude about his code, he has to manually paste files—context window fills fast

**Quantified:**
- 2-3 hours/week answering "where is X?" questions from team
- New engineer ramp time: 3 months to "productive", 6 months to "autonomous"
- 40% of code review comments are about patterns/conventions that should be discoverable
- Average codebase query takes 5-10 minutes of manual file exploration

## Solution

**What:** CLI-first local code knowledge graph:
- **Real-time watching** — Index updates as you save files
- **Graph-aware queries** — "What calls getUserById?", "What modules depend on auth?"
- **Agent integration** — MCP server for Claude/agents to query your code
- **Incremental indexing** — Sub-second updates, not full re-index
- **100% local** — No cloud, no telemetry, runs on your laptop

**How:**
1. Language-aware parsing (Tree-sitter) extracts AST → symbols, calls, imports
2. Builds property graph: nodes (functions, classes, files) + edges (calls, imports, extends)
3. Embeds docstrings/comments for semantic search
4. Exposes CLI (`ckg query "what handles auth?"`) and MCP server
5. File watcher triggers incremental updates

**Why Us:**
- Deep experience with code analysis (built internal tools)
- Understand agent integration requirements (MCP, context budgets)
- Can make CLI UX excellent (see: OpenClaw CLI design)

## Why Now

1. **AI agents need code context** — Every coding agent is context-starved
2. **Sourcegraph pivoted to enterprise** — Left SMB/individual market underserved
3. **Tree-sitter is mature** — Language parsing is solved for 20+ languages
4. **MCP provides distribution** — Ship as MCP server, instant Claude Desktop integration
5. **Local-first movement** — Developers increasingly privacy-conscious about code

## Market Landscape

**TAM:** $15B (developer tools)
**SAM:** $3B (code intelligence/search)
**SOM:** $100M (local-first code knowledge, Year 3)

### Competitors & Gaps

| Competitor | What They Do | Gap |
|------------|--------------|-----|
| **Sourcegraph** | Enterprise code search | $$$, server-based, overkill for small teams |
| **GitHub Code Search** | Cloud code search | GitHub-only, no relationships, no local |
| **Cursor** | AI code editor | Editor-locked, no standalone query |
| **Codeium** | AI code assistant | Cloud-based, no graph queries |
| **ctags/cscope** | Symbol indexing | Ancient UX, no semantic, no graph |
| **LSP servers** | IDE code intel | Editor-specific, no cross-repo, no natural language |
| **grep/ripgrep** | Text search | No understanding, just string matching |

**White space:** Local graph-aware code search with agent integration.

## Competitive Advantages

1. **Local-first moat** — Privacy-conscious devs won't send code to cloud
2. **Real-time incremental** — Competitors batch-index, we're instant
3. **Agent-native** — MCP server makes us the default for Claude users
4. **CLI excellence** — Great UX for terminal-native developers
5. **Open source core** — Community contributions, trust, distribution

## Technical Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Query Layer                            │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐       │
│  │    CLI      │ │ MCP Server  │ │  HTTP API   │       │
│  │ ckg query   │ │ for Agents  │ │  (optional) │       │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘       │
└─────────┼───────────────┼───────────────┼───────────────┘
          │               │               │
┌─────────▼───────────────▼───────────────▼───────────────┐
│                   Query Engine                           │
│  • Natural language → graph query translation            │
│  • Cypher-like query language for power users           │
│  • Semantic search over embeddings                       │
│  • Result ranking and formatting                         │
└─────────────────────────────────────────────────────────┘
          │
┌─────────▼───────────────────────────────────────────────┐
│                   Index Layer                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │              Graph Database                      │   │
│  │  Nodes: files, functions, classes, variables    │   │
│  │  Edges: calls, imports, extends, implements     │   │
│  │  Store: SQLite + custom graph indexes           │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────┐   │
│  │              Vector Index                        │   │
│  │  Embeddings for docstrings, comments, names     │   │
│  │  Store: SQLite-vss or Qdrant local              │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
          │
┌─────────▼───────────────────────────────────────────────┐
│                   Indexing Pipeline                      │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐       │
│  │ File Watcher│ │ Tree-sitter │ │  Embedding  │       │
│  │  (notify)   │ │   Parser    │ │  Generator  │       │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘       │
└─────────┼───────────────┼───────────────┼───────────────┘
          │               │               │
          ▼               ▼               ▼
    ┌──────────────────────────────────────┐
    │            Source Files               │
    │        (your local codebase)          │
    └──────────────────────────────────────┘
```

**Stack:**
- Language: Rust (performance, single binary distribution)
- Parsing: Tree-sitter (20+ language grammars)
- Graph storage: SQLite + custom adjacency indexes
- Vector search: SQLite-vss (built-in) or optional Qdrant
- Embeddings: Ollama (local) or OpenAI (optional, user's key)
- File watching: notify-rs (cross-platform)
- CLI: clap + ratatui for interactive mode
- MCP: TypeScript wrapper or Rust native

## Build Plan

| Week | Milestone |
|------|-----------|
| 1-2 | Rust project scaffold, Tree-sitter integration for JS/TS/Python |
| 3-4 | Graph schema, SQLite storage, basic symbol extraction |
| 5-6 | Call graph extraction, import resolution, relationship indexing |
| 7-8 | CLI query interface, natural language → graph query |
| 9-10 | File watcher, incremental indexing, embedding integration |
| 11-12 | MCP server, Claude Desktop testing, documentation |
| 13-14 | Additional languages (Go, Rust, Java), performance optimization |
| 15-16 | Public release, HN launch, community feedback |

**Team:** 1 dev (you), Rust experience required

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Tree-sitter parsing incomplete | Medium | Medium | Start with JS/TS/Python (best grammars), expand carefully |
| Performance issues at scale | Medium | Medium | Profile early, SQLite is fast, cache hot paths |
| Natural language queries disappoint | High | Medium | Power user query language fallback, improve with usage data |
| Cursor/Codeium ship similar | High | High | Local-first differentiation, open source, move fast |
| Rust slows development velocity | Medium | Low | Worth it for distribution (single binary) |

## Monetization

**Model:** Open core + paid features

| Tier | Price | Includes |
|------|-------|----------|
| Core | Free | CLI, graph queries, JS/TS/Python, 1 repo |
| Pro | $20/mo | All languages, multi-repo, team sharing, priority support |
| Team | $15/user/mo | Shared indexes, org-wide search, admin dashboard |
| Enterprise | Custom | On-prem server mode, SSO, SLA |

**Path to $1M ARR:**

- **Target:** 
  - 2,500 Pro users @ $20/mo = $600k ARR
  - 40 teams × 10 users @ $15/mo = $400k ARR (bonus if hits)
  
- **Funnel:**
  - 100,000 free users (GitHub stars → downloads)
  - 5% power users try Pro = 5,000 trials
  - 50% convert = 2,500 Pro users

- **Timeline:** 18-24 months post-launch

**Expansion:** Enterprise deals, Cursor/VS Code plugin marketplace

## Verdict

### 🟢 BUILD

**Reasoning:**
1. **Clear pain point** — Every developer who's used an AI coding tool has hit this
2. **Differentiated angle** — Local + graph + real-time + MCP is unique combination
3. **Distribution path clear** — Open source + MCP registry + HN = organic growth
4. **Technical feasibility** — Tree-sitter, SQLite, Rust all proven; no research risk
5. **Compounds with other tools** — Integrates with agent memory, token budgeting

**Caveats:**
- Rust development is slower; plan for it
- Natural language queries are hard—consider starting with structured queries
- Cursor is well-funded and moving fast; speed matters

**First step:** Build MVP for TypeScript only (our main language), test on OpenClaw codebase. If we love it, proceed to full build.
