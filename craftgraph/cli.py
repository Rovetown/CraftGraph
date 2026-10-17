"""CLI entry points for CraftGraph.

Diagnostic: set ``CRAFTGRAPH_DUMP_MODULES=1`` in the environment before
running any subcommand to dump every imported module name to
``modules-cli.txt`` in the working directory at process exit. Mirror of
the GUI-side dump in ``gui_entry.py``; together they feed Step 7 of the
bundle size reduction plan (see TODO).
"""

import atexit
import contextlib
import os
import sys
from collections.abc import Callable
from pathlib import Path

import click
import networkx


def _install_modules_dump() -> None:
    """Register a ``sys.modules`` dump on exit when ``CRAFTGRAPH_DUMP_MODULES`` is set.

    Writes one module name per line to ``modules-cli.txt`` in the current
    working directory. No-op when unset; OSError on write is swallowed.
    """
    if not os.environ.get("CRAFTGRAPH_DUMP_MODULES"):
        return

    def _dump() -> None:
        with contextlib.suppress(OSError):
            Path("modules-cli.txt").write_text(
                "\n".join(sorted(sys.modules)),
                encoding="utf-8",
            )

    atexit.register(_dump)


_install_modules_dump()

# Imports below the dump hook on purpose: the hook has to be registered before
# any craftgraph module lands in sys.modules, or the dump misses them.
from craftgraph import __version__  # noqa: E402
from craftgraph.graph import (  # noqa: E402
    NodeType,
    build_graph,
    classify_nodes,
    find_cycles,
)
from craftgraph.models import ParsedFile  # noqa: E402
from craftgraph.parser import (  # noqa: E402
    MappingError,
    ParseError,
    parse_directory,
    parse_file,
    validate_parsed_file,
)
from craftgraph.serializer import serialize_file  # noqa: E402


def _load_generate_html() -> Callable[..., Path]:
    """Import ``generate_html`` lazily so ``pyvis`` isn't required at CLI start.

    Returns ``generate_html`` on success. On failure prints an install hint
    via click and raises ``SystemExit(1)`` so callers can ``return`` after.

    ``visualizer.py`` itself does the actual ``pyvis`` import lazily
    inside ``generate_html()``, so importing the module never fails on
    a pyvis-less install. We trigger an upfront ``import pyvis`` here
    so the error lands in this friendly handler rather than as an
    uncaught ``PyvisNotInstalledError`` deep in the call stack.
    """
    try:
        import pyvis  # noqa: F401  -- existence check only

        from craftgraph.visualizer import generate_html
    except ImportError as exc:
        click.echo(
            f'Error: {exc}\nInstall with: pip install "craftgraph[visualizer]"',
            err=True,
        )
        raise SystemExit(1) from exc
    return generate_html


@click.group()
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default=None,
    help="Console log verbosity for this run (overrides the saved setting).",
)
@click.version_option(version=__version__, prog_name="craftgraph")
def main(log_level: str | None) -> None:
    """CraftGraph -- recipe dependency graphs for CustomCraft3."""
    import logging

    from craftgraph import app_dirs
    from craftgraph.log_setup import configure_logging

    name = log_level.upper() if log_level else str(app_dirs.load_setting("log_level", "INFO"))
    configure_logging(level=logging.getLevelNamesMapping().get(name, logging.INFO))


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


def _report_warnings(parsed_files: list[ParsedFile]) -> None:
    """Print ingredient validation warnings (if any) to stderr."""
    for pf in parsed_files:
        for warning in validate_parsed_file(pf):
            click.echo(click.style(f"  Warning: {warning}", fg="yellow"), err=True)


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

    _report_warnings(parsed_files)
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

    _report_warnings(parsed_files)
    graph = build_graph(parsed_files)

    if verbose:
        _report_verbose_stats(parsed_files, graph)

    cycles = find_cycles(graph)
    _report_cycles(cycles)

    output_path = Path(output) if output else Path("craftgraph.html")
    generate_html = _load_generate_html()
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
    generate_html = _load_generate_html()
    is_first_build = True

    def on_rebuild(
        parsed_files: list[ParsedFile],
        graph: networkx.DiGraph[str],
        cycles: list[list[str]],
    ) -> None:
        nonlocal is_first_build

        _report_warnings(parsed_files)

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


@main.command()
@click.argument("path", type=click.Path())
@click.option("-o", "--output", type=click.Path(), default=None, help="Output file or directory.")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed output.")
def export(path: str, output: str | None, *, verbose: bool) -> None:
    """Export parsed recipes back to EasyMarkup text files."""
    parsed_files = _parse_path(path)

    if not parsed_files:
        click.echo("No recipe files found.")
        return

    _report_warnings(parsed_files)

    if verbose:
        total_recipes = sum(len(list(pf.all_recipes)) for pf in parsed_files)
        click.echo(f"  Files parsed: {len(parsed_files)}")
        click.echo(f"  Total recipes: {total_recipes}")

    input_path = Path(path)

    if input_path.is_file():
        # Single file: serialize to -o file or stdout
        text = serialize_file(parsed_files[0])
        if output:
            out_path = Path(output)
            out_path.write_text(text, encoding="utf-8")
            click.echo(f"Exported to {out_path}")
        else:
            # Write as UTF-8 bytes to avoid Windows cp1252 encoding errors
            sys.stdout.buffer.write(text.encode("utf-8"))
    else:
        # Directory: serialize each file
        if output:
            out_dir = Path(output)
            if not out_dir.exists():
                out_dir.mkdir(parents=True)
            for pf in parsed_files:
                text = serialize_file(pf)
                if not text:
                    continue
                out_file = out_dir / pf.source_path.name
                out_file.write_text(text, encoding="utf-8")
            click.echo(f"Exported {len(parsed_files)} files to {out_dir}")
        else:
            for pf in parsed_files:
                text = serialize_file(pf)
                if text:
                    header = f"# {pf.source_path.name}\n"
                    sys.stdout.buffer.write(header.encode("utf-8"))
                    sys.stdout.buffer.write(text.encode("utf-8"))
                    sys.stdout.buffer.write(b"\n")


@main.command()
@click.argument("path", type=click.Path(), required=False, default=None)
@click.option(
    "--trace-mem",
    is_flag=True,
    default=False,
    help="Start tracemalloc before the GUI launches so Help > Dump Memory "
    "Snapshot has data. Adds runtime overhead; for diagnostics only.",
)
def gui(path: str | None, trace_mem: bool) -> None:
    """Open the graphical recipe editor (PySide6 + NodeGraphQt)."""
    if trace_mem:
        # Start tracking AFTER the heavy import chain (pyvis -> IPython etc.)
        # has settled, so users do not pay tracemalloc cost during startup.
        import tracemalloc

        tracemalloc.start(25)

    try:
        from craftgraph.qt_gui import launch_qt_gui
    except ImportError as exc:
        click.echo(
            "Error: PySide6 or NodeGraphQt is not installed. "
            'Install with: uv sync --extra qt (or pip install "craftgraph[qt]")',
            err=True,
        )
        raise SystemExit(1) from exc

    recipe_path = Path(path) if path else None
    if recipe_path is not None and not recipe_path.exists():
        click.echo(f"Error: path not found: {recipe_path}", err=True)
        raise SystemExit(1)

    launch_qt_gui(recipe_path)


@main.command("register")
def register_file_assoc() -> None:
    """Register .craftgraph file association for the current user."""
    from craftgraph.file_assoc import is_registered, register

    if is_registered():
        click.echo("File association is already registered.")
        return

    result = register()
    click.echo(result)
    click.echo(click.style("Done.", fg="green"))


@main.command("unregister")
def unregister_file_assoc() -> None:
    """Remove the .craftgraph file association."""
    from craftgraph.file_assoc import is_registered, unregister

    if not is_registered():
        click.echo("File association is not registered. Nothing to do.")
        return

    result = unregister()
    click.echo(result)
    click.echo(click.style("Done.", fg="green"))


if __name__ == "__main__":
    main()
