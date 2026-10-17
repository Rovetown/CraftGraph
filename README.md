# CraftGraph

Recipe dependency graphs for [CustomCraft3](https://github.com/MrPurple6411/PrimeSonicSubnauticaMods/tree/master/CustomCraft3) (Subnautica).

Parses CC3's EasyMarkup `.txt` recipe files, builds dependency graph, detects circular dependencies, visualizes as interactive HTML graph. Watches mod folder for changes, rebuilds automatically.

<p align="center">
  <sub>&darr; <i>Click to view full resolution</i> &darr;</sub>
  <br><br>
  <a href="craftgraph/data/assets/roadmap-vertical@4x.png">
    <img src="craftgraph/data/assets/roadmap-vertical@4x.png" width="900"
         alt="CraftGraph roadmap -- click for full resolution">
  </a>
</p>

## Features

- **Parse** all 10 CC3 block types (ModifiedRecipes, AddedRecipes, AliasRecipes, CustomFabricators, etc.)
- **Detect** circular dependencies, report full cycle path
- **Visualize** dependency graph as interactive HTML page with color-coded nodes
- **Watch** recipe directory, auto-rebuild on every save

## Installation

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14+.

```bash
git clone https://github.com/you/craftgraph
cd craftgraph
uv sync
```

## Usage

### Check for circular dependencies

```bash
craftgraph check ./my-mod/WorkingFiles/
```

Reports circular dependencies found, or prints "No circular dependencies found."
Add `-v` for detailed stats (file count, recipe count, node types).

```bash
craftgraph check ./my-mod/WorkingFiles/ -v
```

### Visualize dependency graph

```bash
craftgraph view ./my-mod/WorkingFiles/
```

Generates `craftgraph.html` and opens in browser. Use `-o` to change output path:

```bash
craftgraph view ./my-mod/WorkingFiles/ -o my-graph.html
```

Graph uses hierarchical top-down layout:

- **Green nodes** = raw materials (not crafted from anything)
- **Blue nodes** = intermediates (crafted and used as ingredients)
- **Gold nodes** = end products (crafted but not used by anything else)
- **Red edges** = circular dependencies

Hover over any node to see recipe type, source file, ingredients, and what uses it.

### Watch for changes

```bash
craftgraph watch ./my-mod/WorkingFiles/
```

Opens graph in browser, watches directory for `.txt` changes. On recipe file save, graph rebuilds automatically within ~1 second. Refresh browser tab to see updates. `Ctrl+C` to stop.

```bash
craftgraph watch ./my-mod/WorkingFiles/ -o live-graph.html -v
```

## Development

All commands go through [justfile](https://github.com/casey/just):

```bash
just --list          # Show all available commands
just sync            # Install/sync dependencies
just test            # Run the test suite (293 tests)
just test-v          # Run tests with verbose output
just qa              # Run all quality checks (lint + format + typecheck)
just lint-fix        # Auto-fix lint issues
just fmt             # Auto-format code
just build           # Bundle into a standalone binary
```

### Running from source

```bash
uv run craftgraph check ./recipes/
uv run craftgraph view ./recipes/
uv run craftgraph watch ./recipes/
```

### Tech stack

| Layer           | Choice     | Why                                                  |
|-----------------|------------|------------------------------------------------------|
| Language        | Python 3.14| Strong ecosystem, great for scripts and GUIs         |
| Graph logic     | NetworkX   | Cycle detection, topological sort, all graph algos   |
| File watching   | Watchdog   | Cross-platform directory/file watcher                |
| Visualization   | Pyvis      | Interactive HTML graph, zero GUI dependencies        |
| CLI             | Click      | Clean argument parsing with subcommands              |
| Package manager | uv         | Fast, lockfile-based, `uv run` = no manual venv      |
| Distribution    | PyInstaller| Single portable binary, no Python install needed     |

## License

See [LICENSE](LICENSE).
