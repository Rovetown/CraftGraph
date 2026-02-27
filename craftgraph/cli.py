"""CLI entry points for CraftGraph."""

from pathlib import Path

import click
import networkx

from craftgraph import __version__
from craftgraph.graph import NodeType, build_graph, classify_nodes, find_cycles
from craftgraph.models import ParsedFile
from craftgraph.parser import MappingError, ParseError, parse_directory, parse_file
from craftgraph.visualizer import generate_html


@click.group()
@click.version_option(version=__version__, prog_name="craftgraph")
def main() -> None:
    """CraftGraph -- recipe dependency graphs for CustomCraft3."""


# -- Shared helpers ------------------------------------------------------------


def _parse_path(path_str: str) -> list[ParsedFile]:
    """Parse a file or directory path into a list of ParsedFile objects.

    Handles both single files and directories. Raises SystemExit on errors
    so callers don't need their own error handling for parse failures.
    """
    path = Path(path_str)

    if not path.exists():
        click.echo(f"Error: path not found: {path}", err=True)
        raise SystemExit(1)

    if path.is_file():
        try:
            result = parse_file(path)
        except (ParseError, MappingError) as exc:
            click.echo(f"Error: failed to parse {path}: {exc}", err=True)
            raise SystemExit(1) from exc
        return [result]

    try:
        return parse_directory(path)
    except (FileNotFoundError, NotADirectoryError) as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc


def _report_verbose_stats(
    parsed_files: list[ParsedFile],
    graph: networkx.DiGraph[str],
) -> None:
    """Print detailed statistics about the parsed files and graph."""
    total_recipes = sum(len(list(pf.all_recipes)) for pf in parsed_files)
    click.echo(f"  Files parsed: {len(parsed_files)}")
    click.echo(f"  Total recipes: {total_recipes}")
    click.echo(f"  Graph nodes: {graph.number_of_nodes()}")
    click.echo(f"  Graph edges: {graph.number_of_edges()}")

    classifications = classify_nodes(graph)
    raw_count = sum(1 for v in classifications.values() if v is NodeType.RAW_MATERIAL)
    inter_count = sum(1 for v in classifications.values() if v is NodeType.INTERMEDIATE)
    end_count = sum(1 for v in classifications.values() if v is NodeType.END_PRODUCT)
    click.echo(
        f"  Node types: {raw_count} raw materials, "
        f"{inter_count} intermediates, {end_count} end products"
    )


def _report_cycles(cycles: list[list[str]]) -> None:
    """Print cycle detection results."""
    if not cycles:
        click.echo(click.style("No circular dependencies found.", fg="green"))
        return

    click.echo(click.style(f"Found {len(cycles)} circular dependency(ies)!", fg="red", bold=True))
    for i, cycle in enumerate(cycles, 1):
        path_str = " -> ".join([*cycle, cycle[0]])
        click.echo(f"  {i}. {path_str}")


# -- Commands ------------------------------------------------------------------


@main.command()
@click.argument("path", type=click.Path())
@click.option("-v", "--verbose", is_flag=True, help="Show detailed output.")
def check(path: str, *, verbose: bool) -> None:
    """Check recipes for circular dependencies."""
    parsed_files = _parse_path(path)

    if not parsed_files:
        click.echo("No recipe files found.")
        return

    graph = build_graph(parsed_files)

    if verbose:
        _report_verbose_stats(parsed_files, graph)

    cycles = find_cycles(graph)
    _report_cycles(cycles)


@main.command()
@click.argument("path", type=click.Path())
@click.option("-o", "--output", type=click.Path(), default=None, help="Output HTML file path.")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed output.")
def view(path: str, output: str | None, *, verbose: bool) -> None:
    """Visualize the recipe dependency graph."""
    parsed_files = _parse_path(path)

    if not parsed_files:
        click.echo("No recipe files found.")
        return

    graph = build_graph(parsed_files)

    if verbose:
        _report_verbose_stats(parsed_files, graph)

    cycles = find_cycles(graph)
    _report_cycles(cycles)

    output_path = Path(output) if output else Path("craftgraph.html")
    result = generate_html(graph, output_path, cycles, open_browser=True)
    click.echo(f"Graph saved to {result}")


@main.command()
@click.argument("path", type=click.Path())
@click.option("-o", "--output", type=click.Path(), default=None, help="Output HTML file path.")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed output.")
def watch(path: str, output: str | None, *, verbose: bool) -> None:
    """Watch a recipe directory and rebuild on changes."""
    directory = Path(path)
    if not directory.is_dir():
        click.echo(f"Error: not a directory: {path}", err=True)
        raise SystemExit(1)

    output_path = Path(output) if output else Path("craftgraph.html")
    is_first_build = True

    def on_rebuild(
        parsed_files: list[ParsedFile],
        graph: networkx.DiGraph[str],
        cycles: list[list[str]],
    ) -> None:
        nonlocal is_first_build

        if verbose:
            _report_verbose_stats(parsed_files, graph)

        _report_cycles(cycles)

        open_browser = is_first_build
        result = generate_html(graph, output_path, cycles, open_browser=open_browser)
        click.echo(f"Graph updated: {result}")
        is_first_build = False

    click.echo(f"Watching {directory.resolve()} for changes (Ctrl+C to stop)...")

    from craftgraph.watcher import watch_directory

    watch_directory(directory, on_rebuild)


if __name__ == "__main__":
    main()
