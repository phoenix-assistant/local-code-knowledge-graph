"""CLI commands for Code Knowledge Graph."""

import sys
import time
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ckg.graph.store import GraphStore
from ckg.indexing.indexer import CodeIndexer
from ckg.parsing.manager import ParserManager
from ckg.query.engine import QueryEngine
from ckg.watch.watcher import FileWatcher

console = Console()


def get_data_dir(repo_path: Path) -> Path:
    """Get the data directory for a repository."""
    return repo_path / ".ckg"


def get_store(repo_path: Path) -> GraphStore:
    """Get or create graph store for a repository."""
    data_dir = get_data_dir(repo_path)
    return GraphStore(db_path=data_dir / "graph.db")


def get_indexer(repo_path: Path, store: GraphStore) -> CodeIndexer:
    """Get or create indexer for a repository."""
    return CodeIndexer(repo_path, store)


def get_query_engine(repo_path: Path, store: GraphStore) -> QueryEngine:
    """Get or create query engine for a repository."""
    data_dir = get_data_dir(repo_path)
    return QueryEngine(store, vector_path=data_dir / "vectors")


@click.group()
@click.option(
    "--repo",
    "-r",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
    help="Repository path (default: current directory)",
)
@click.pass_context
def cli(ctx: click.Context, repo: Path) -> None:
    """Local Code Knowledge Graph - Graph RAG for codebases."""
    ctx.ensure_object(dict)
    ctx.obj["repo_path"] = repo.resolve()


@cli.command()
@click.option("--full", is_flag=True, help="Force full re-index")
@click.option("--resolve", is_flag=True, default=True, help="Resolve cross-references")
@click.option("--vectors", is_flag=True, default=True, help="Build vector embeddings")
@click.pass_context
def index(ctx: click.Context, full: bool, resolve: bool, vectors: bool) -> None:
    """Index the codebase into the knowledge graph."""
    repo_path = ctx.obj["repo_path"]
    console.print(f"[bold]Indexing[/bold] {repo_path}")

    store = get_store(repo_path)
    indexer = get_indexer(repo_path, store)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        if full or store.node_count() == 0:
            task = progress.add_task("Full indexing...", total=None)

            def on_progress(path: str, current: int, total: int) -> None:
                progress.update(task, description=f"Indexing {path} ({current}/{total})")

            stats = indexer.index_full(progress_callback=on_progress)
            progress.update(task, description="Full indexing complete")

            console.print(f"  Files processed: [green]{stats['files_processed']}[/green]")
            console.print(f"  Functions: [cyan]{stats['functions']}[/cyan]")
            console.print(f"  Classes: [cyan]{stats['classes']}[/cyan]")
            console.print(f"  Imports: [cyan]{stats['imports']}[/cyan]")
        else:
            task = progress.add_task("Incremental indexing...", total=None)

            def on_progress(path: str, current: int, total: int) -> None:
                progress.update(task, description=f"Processing {path} ({current}/{total})")

            stats = indexer.index_incremental(progress_callback=on_progress)
            progress.update(task, description="Incremental indexing complete")

            console.print(f"  Files added: [green]{stats['files_added']}[/green]")
            console.print(f"  Files modified: [yellow]{stats['files_modified']}[/yellow]")
            console.print(f"  Files deleted: [red]{stats['files_deleted']}[/red]")

        if resolve:
            task = progress.add_task("Resolving references...", total=None)
            resolved = indexer.resolve_references()
            progress.update(task, description=f"Resolved {resolved} references")

        if vectors:
            task = progress.add_task("Building vector embeddings...", total=None)
            query_engine = get_query_engine(repo_path, store)
            count = query_engine.index_vectors()
            progress.update(task, description=f"Indexed {count} embeddings")

    store.close()
    console.print("[bold green]✓[/bold green] Indexing complete")


@cli.command()
@click.argument("query_text")
@click.option("--type", "-t", "node_type", type=click.Choice(["function", "class", "file", "any"]), default="any")
@click.option("--limit", "-n", default=10, help="Maximum results")
@click.option("--no-expand", is_flag=True, help="Don't expand via graph traversal")
@click.pass_context
def query(ctx: click.Context, query_text: str, node_type: str, limit: int, no_expand: bool) -> None:
    """Search the knowledge graph."""
    repo_path = ctx.obj["repo_path"]
    store = get_store(repo_path)
    query_engine = get_query_engine(repo_path, store)

    from ckg.graph.models import NodeType

    node_types = None
    if node_type != "any":
        type_map = {
            "function": NodeType.FUNCTION,
            "class": NodeType.CLASS,
            "file": NodeType.FILE,
        }
        node_types = [type_map[node_type]]

    result = query_engine.query(
        query_text=query_text,
        node_types=node_types,
        max_results=limit,
        expand_graph=not no_expand,
    )

    if not result.nodes:
        console.print("[yellow]No results found[/yellow]")
        return

    table = Table(title=f"Results for '{query_text}'")
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Score", style="yellow")
    table.add_column("Location")

    for node in result.nodes:
        score = result.scores.get(node.id, 0)
        location = ""
        if hasattr(node, "file_id"):
            location = node.file_id.replace("file:", "")  # type: ignore
            if hasattr(node, "start_line"):
                location += f":{node.start_line}"  # type: ignore

        table.add_row(
            node.type.value,
            node.name,
            f"{score:.2f}",
            location,
        )

    console.print(table)
    store.close()


@cli.command()
@click.argument("symbol_name")
@click.pass_context
def find(ctx: click.Context, symbol_name: str) -> None:
    """Find a symbol definition."""
    repo_path = ctx.obj["repo_path"]
    store = get_store(repo_path)
    query_engine = get_query_engine(repo_path, store)

    result = query_engine.find_definition(symbol_name)

    if not result.nodes:
        console.print(f"[yellow]No definition found for '{symbol_name}'[/yellow]")
        return

    for node in result.nodes:
        console.print(f"\n[bold cyan]{node.type.value.upper()}[/bold cyan]: [green]{node.name}[/green]")

        if hasattr(node, "signature"):
            console.print(f"  Signature: {node.signature}")  # type: ignore
        if hasattr(node, "file_id"):
            location = node.file_id.replace("file:", "")  # type: ignore
            if hasattr(node, "start_line"):
                location += f":{node.start_line}-{node.end_line}"  # type: ignore
            console.print(f"  Location: {location}")
        if hasattr(node, "docstring") and node.docstring:  # type: ignore
            console.print(f"  Docstring: {node.docstring}")  # type: ignore

    store.close()


@cli.command()
@click.argument("file_path")
@click.pass_context
def file(ctx: click.Context, file_path: str) -> None:
    """Show symbols in a file."""
    repo_path = ctx.obj["repo_path"]
    store = get_store(repo_path)
    query_engine = get_query_engine(repo_path, store)

    result = query_engine.get_file_summary(file_path)

    if not result.nodes:
        console.print(f"[yellow]No symbols found in '{file_path}'[/yellow]")
        return

    console.print(f"\n[bold]File:[/bold] {file_path}")
    console.print(f"Functions: {result.metadata.get('functions', 0)}")
    console.print(f"Classes: {result.metadata.get('classes', 0)}")
    console.print(f"Imports: {result.metadata.get('imports', 0)}")

    table = Table()
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Line")

    for node in result.nodes:
        line = ""
        if hasattr(node, "start_line"):
            line = str(node.start_line)  # type: ignore
        elif hasattr(node, "line"):
            line = str(node.line)  # type: ignore

        table.add_row(node.type.value, node.name, line)

    console.print(table)
    store.close()


@cli.command()
@click.pass_context
def stats(ctx: click.Context) -> None:
    """Show graph statistics."""
    repo_path = ctx.obj["repo_path"]
    store = get_store(repo_path)

    graph_stats = store.get_stats()

    console.print("\n[bold]Code Knowledge Graph Statistics[/bold]\n")
    console.print(f"Total Nodes: [cyan]{graph_stats['total_nodes']}[/cyan]")
    console.print(f"Total Edges: [cyan]{graph_stats['total_edges']}[/cyan]")

    if graph_stats["node_types"]:
        console.print("\n[bold]Node Types:[/bold]")
        for node_type, count in graph_stats["node_types"].items():
            console.print(f"  {node_type}: [green]{count}[/green]")

    if graph_stats["edge_types"]:
        console.print("\n[bold]Edge Types:[/bold]")
        for edge_type, count in graph_stats["edge_types"].items():
            console.print(f"  {edge_type}: [yellow]{count}[/yellow]")

    store.close()


@cli.command()
@click.option("--verbose", "-v", is_flag=True, help="Show changed files")
@click.pass_context
def watch(ctx: click.Context, verbose: bool) -> None:
    """Watch for changes and update index in real-time."""
    repo_path = ctx.obj["repo_path"]
    console.print(f"[bold]Watching[/bold] {repo_path} for changes...")
    console.print("Press Ctrl+C to stop.\n")

    store = get_store(repo_path)
    indexer = get_indexer(repo_path, store)

    def on_change(path: str, event_type: str) -> None:
        if verbose:
            emoji = {"created": "✨", "modified": "📝", "deleted": "🗑️"}.get(event_type, "❓")
            console.print(f"  {emoji} {event_type}: {path}")

    watcher = FileWatcher(indexer, on_change=on_change)

    try:
        with watcher:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[bold]Stopped watching[/bold]")
    finally:
        store.close()


@cli.command()
@click.pass_context
def graph(ctx: click.Context) -> None:
    """Export graph in DOT format for visualization."""
    repo_path = ctx.obj["repo_path"]
    store = get_store(repo_path)

    console.print("digraph CodeKnowledgeGraph {")
    console.print("  rankdir=LR;")
    console.print("  node [shape=box];")

    # Output nodes
    for node_id, data in store.graph.nodes(data=True):
        label = f"{data.get('type', 'unknown')}\\n{data.get('name', node_id)}"
        console.print(f'  "{node_id}" [label="{label}"];')

    # Output edges
    for source_id, target_id, data in store.graph.edges(data=True):
        edge_type = data.get("type", "")
        console.print(f'  "{source_id}" -> "{target_id}" [label="{edge_type}"];')

    console.print("}")
    store.close()


@cli.command()
@click.pass_context
def serve(ctx: click.Context) -> None:
    """Start MCP server for agent integration."""
    repo_path = ctx.obj["repo_path"]
    console.print(f"[bold]Starting MCP server[/bold] for {repo_path}")

    from ckg.mcp.server import MCPServer
    import asyncio

    server = MCPServer(repo_path)
    asyncio.run(server.run())


if __name__ == "__main__":
    cli()
