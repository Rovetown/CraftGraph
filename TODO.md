# CraftGraph -- TODO

> Priority-ordered, step-by-step build plan.
> Each step lists what it depends on so nothing is started out of order.
> Checkboxes track completion; update as we go.

---

## Step 0 -- Project Scaffolding

**Priority:** Highest (everything depends on this)
**Depends on:** Nothing

- [x] Create the `craftgraph/` package directory with `__init__.py`
- [x] Update `pyproject.toml`:
  - Add runtime dependencies: `networkx`, `watchdog`, `pyvis`, `click`
  - Add dev dependencies: `pytest`, `ruff`, `mypy`
  - Add `[project.scripts]` entry point: `craftgraph = "craftgraph.cli:main"`
  - Kept `requires-python = ">=3.14"` (matches `.python-version`)
- [x] Run `uv sync` to install all dependencies and lock them (33 packages)
- [x] Create placeholder module files: `cli.py`, `parser.py`, `graph.py`, `watcher.py`, `visualizer.py`, `models.py`
- [x] Create `tests/` directory with `__init__.py` and placeholder test files: `test_parser.py`, `test_graph.py`
- [x] Verify the project runs: `just run --help` shows all 4 subcommands, `just run --version` shows 0.1.0
- [x] `just qa` passes: ruff lint clean, ruff format clean, mypy strict clean (8 source files)

---

## Step 1 -- Data Model

**Priority:** Highest (parser, graph, visualizer all consume these)
**Depends on:** Step 0

- [x] Define core dataclasses in `craftgraph/models.py`:
  - `Ingredient` (frozen) -- `item_id: str`, `required: int`
  - `BlockType` enum -- all 10 CC3 block type keywords
  - Recipe hierarchy using dataclass inheritance (mirrors CC3's C# classes):
    - `ModifiedRecipe` -- base recipe with ingredients, linked items, unlocks
    - `AddedRecipe(ModifiedRecipe)` -- adds path, pda_group, pda_category
    - `AliasRecipe(AddedRecipe)` -- adds display_name, tooltip, functional_id, sprite_item_id
    - `CustomFood(AliasRecipe)` -- adds food/water/oxygen/health values, decay_rate_mod
  - `CraftingTab` -- `tab_id: str`, `display_name: str`, `parent_tab_path: str`, `sprite_item_id: str | None`
  - `CustomFabricator` -- with nested tabs, added_recipes, alias_recipes, moved_recipes, custom_foods
  - `CustomSize` -- `item_id: str`, `width: int`, `height: int`
  - `CustomBioFuel` -- `item_id: str`, `energy: float`
  - `CustomFragmentCount` -- `item_id: str`, `fragments_to_scan: int`
  - `MovedRecipe` -- `item_id: str`, `old_path: str | None`, `new_path: str | None`, `copied: bool`, `hidden: bool`
  - `ParsedFile` -- container with `source_path`, per-type lists, `all_recipes` property traversing fabricator-nested recipes
- [x] Write basic unit tests for model construction and validation (35 tests in `tests/test_models.py`)

---

## Step 2 -- EasyMarkup Parser (Core)

**Priority:** Highest (the central piece -- graph, visualizer, CLI all need parsed data)
**Depends on:** Step 1

This is the most complex module. Build it in sub-steps.

### 2a -- Low-level EasyMarkup tokenizer

- [x] Implement comment stripping: remove content between `#` delimiters (paired block comments, not line comments)
- [x] Implement escape sequence handling: `\:`, `\,`, `\;`, `\#`, `\\`, `\(`, `\)` preserve the literal character
- [x] Implement quoted string handling: content inside `"..."` preserves spaces and special chars
- [x] Implement whitespace stripping: ALL whitespace removed outside quotes/escapes (matches CC3's `CleanValue()`)
- [x] Implement `unescape_value()`: resolves `\X` to literal `X` and strips `"..."` delimiters (matches CC3's `ReadUntilDelimiter()`)
- [x] Write thorough tests for each of the above with edge cases (56 tests in `tests/test_parser.py`)

### 2b -- Block-level parser

- [x] Parse top-level block type from the first non-comment token (e.g. `ModifiedRecipes:`, `AddedRecipes:`, `CustomFabricators:`, etc.)
- [x] Parse parenthesis-delimited entry blocks `( ... )` with proper nesting depth tracking
- [x] Parse key-value pairs: `Key: Value;` and `Key:Value;` (with and without spaces)
- [x] Parse nested collection lists (e.g. `Ingredients:` containing multiple `( ItemID: X; Required: N; )` blocks separated by commas)
- [x] Parse simple comma-separated value lists (e.g. `LinkedItemIDs: A,B,C;`)
- [x] Handle case-insensitive key matching
- [x] Handle semicolons being optional in some positions (observed in real files)
- [x] Write tests using snippets from reference files (40 tests across 10 test classes)

### 2c -- CC3 entry mapping

- [x] Map parsed blocks to data model types (36 unit tests, 132 parser tests total):
  - `ModifiedRecipes:` entries -> `ModifiedRecipe`
  - `AddedRecipes:` entries -> `AddedRecipe`
  - `AliasRecipes:` entries -> `AliasRecipe`
  - `CustomCraftingTabs:` entries -> `CraftingTab`
  - `CustomFabricators:` entries -> `CustomFabricator` (with nested tabs and recipes)
  - `MovedRecipes:` entries -> `MovedRecipe`
  - `CustomSizes:` entries -> `CustomSize`
  - `CustomBioFuels:` entries -> `CustomBioFuel`
  - `CustomFragmentCounts:` entries -> `CustomFragmentCount`
  - `CustomFoods:` entries -> `CustomFood`
- [x] Implement `parse_file(path: Path) -> ParsedFile` top-level function (13 tests, 180 total)
- [x] Implement `parse_directory(path: Path) -> list[ParsedFile]` to walk a directory tree and parse all `.txt` files (13 tests, 193 total)
- [x] Write integration tests that parse the actual reference files in `cc3_reference_files/` (46 tests, 239 total)
  - Parse `Resources_BasicMaterials.txt` and verify 76 recipes, ingredient details, LinkedItemIDs
  - Parse `__Alch_NEW_CustomFAB__.txt` and verify the custom fabricator, 30 tabs, nested paths, special-char tooltip
  - Parse `BigFilteredWater.txt` and verify the AddedRecipe with Path and UnlockedBy
  - Parse `customfab3.txt` and verify 5 tabs, 17 nested AliasRecipes inside a CustomFabricator
  - Parse `customsizze.txt` and verify 17 CustomSize entries
  - Fixed BOM handling: `parse_file` now uses `utf-8-sig` encoding to strip Windows BOM prefix

---

## Step 3 -- Graph Builder

**Priority:** High (core feature -- cycle detection and dependency mapping)
**Depends on:** Step 2

- [x] Create `craftgraph/graph.py` with:
  - `build_graph(parsed_files: list[ParsedFile]) -> nx.DiGraph[str]`
  - Nodes = unique ItemIDs across all parsed files
  - Edges = dependency relationships (recipe A requires ingredient B -> edge A -> B)
  - Node metadata: `recipe_type`, `source_file`, `is_crafted`; ingredient-only nodes get `is_crafted=False`
- [x] Implement cycle detection: `find_cycles(graph: nx.DiGraph[str]) -> list[list[str]]`
  - Uses `networkx.simple_cycles()` (avoids EAFP pattern of `find_cycle` which raises on acyclic graphs)
  - Returns list of cycle paths (empty list if acyclic)
- [x] Implement dependency query helpers:
  - `get_dependencies(graph, item_id) -> set[str]` -- successors (what does this item need?)
  - `get_dependents(graph, item_id) -> set[str]` -- predecessors (what uses this item?)
  - `classify_nodes(graph) -> dict[str, NodeType]` -- RAW_MATERIAL (out-degree 0), END_PRODUCT (in-degree 0, out-degree > 0), INTERMEDIATE (both > 0)
- [x] Write tests (34 tests across 6 classes, 273 total):
  - `TestBuildGraphBasic` (6): empty input, single/multiple recipes, shared ingredients, no-ingredient recipe
  - `TestBuildGraphMetadata` (7): crafted metadata, ingredient-only nodes, upgrade to crafted, recipe type labels, edge required count
  - `TestBuildGraphCrossFile` (1): cross-file references unified into single graph
  - `TestFindCycles` (7): acyclic, simple/3-node cycles, self-loop, multiple independent cycles, cycle with branches
  - `TestDependencyQueries` (7): dependencies/dependents for various topologies, unknown nodes
  - `TestClassifyNodes` (6): simple chain, all raw, isolated, diamond, empty, cyclic nodes

---

## Step 4 -- CLI (Basic)

**Priority:** High (user-facing entry point for Phase 1)
**Depends on:** Step 2, Step 3

- [x] Implement `craftgraph/cli.py` using Click:
  - `craftgraph check <path>` -- parses recipes, builds graph, reports circular dependencies
  - `craftgraph view <path>` -- parses, builds graph, reports cycles (visualization placeholder until Step 5)
  - `craftgraph watch <path>` -- placeholder until Step 6
  - Removed scrapped `convert` command and its justfile recipe
- [x] Add `--verbose` / `-v` flag for detailed output (file count, recipe count, node/edge counts, node type breakdown)
- [x] Add `--output` / `-o` flag for specifying output file location (on `view` command, wired in Step 5)
- [x] Wire up error handling: file-not-found, parse errors, `MappingError` -- all caught at CLI boundary with `click.echo(err=True)` + `SystemExit(1)`
- [x] Test that `just check ./craftgraph/cc3_reference_files/` works end-to-end (58 files, 762 recipes, 894 nodes, 2179 edges, no cycles)

---

## Step 5 -- Visualizer (Pyvis)

**Priority:** Medium (important for usability but not blocking other work)
**Depends on:** Step 3, Step 4

- [x] Implement `craftgraph/visualizer.py`:
  - `generate_html(graph, output_path, cycles, *, open_browser) -> Path`
  - Renders interactive HTML via Pyvis with Barnes-Hut physics, dark background, inline CDN
  - Fixed Windows encoding: writes HTML with UTF-8 instead of Pyvis's default cp1252
  - Added mypy overrides for untyped pyvis module in `pyproject.toml`
- [x] Node styling:
  - Color by node type: raw materials (#2ecc71 green), intermediates (#3498db blue), end products (#f1c40f gold)
  - Size = base 10 + degree * 3 (proportional to connections)
  - Label = ItemID
  - Tooltip = HTML with recipe type, source file, ingredients (with amounts), used-by list
- [x] Edge styling:
  - Normal edges: grey (#888888), width 1
  - Circular dependency edges: red (#e74c3c), width 3
- [x] Auto-open the output HTML in the default browser via `webbrowser.open(path.as_uri())`
- [x] Wire into `craftgraph view` CLI command (default output: `craftgraph.html`, `-o` to override)
- [x] Manual testing with reference files:
  - Full reference dir: 894 nodes, 2179 edges, 1.3 MB HTML
  - Single file (BasicMaterials): 63 raw + 28 intermediate + 48 end = 139 nodes, 202 edges
  - Custom fabricator: 17 AliasRecipes rendered correctly
  - Verified: node colors, edge colors, tooltips, dark background, directed arrows all present
  - Fixed layout bug: changed graph container height from `100%` to `100vh` (viewport height)
- [x] Improve graph layout: switched from Barnes-Hut force-directed physics to vis.js hierarchical layout with `sortMethod: "directed"` and `direction: "UD"` (top-down). End products render at top, raw materials at bottom, with cubicBezier edge curves following the vertical flow. Uses `hierarchicalRepulsion` physics solver for interactive dragging.

---

## Step 6 -- File Watcher

**Priority:** Medium (quality-of-life feature for modders)
**Depends on:** Step 2, Step 3, Step 5

- [x] Implement `craftgraph/watcher.py` using Watchdog:
  - Watch a directory tree for `.txt` file changes (create, modify, delete)
  - Debounce rapid saves (300ms delay before triggering rebuild)
  - On change: re-parse only the changed file, rebuild the full graph, regenerate visualization
- [x] Track per-file parse state so only the changed file is re-parsed (keep a dict of `path -> ParsedFile`)
- [x] Wire into `craftgraph watch` CLI command (with `-o`/`--output` option, opens browser on first build)
- [x] Handle errors gracefully: if a file is mid-save and unparseable, warn but don't crash (keeps cached version)
- [x] 20 unit/integration tests covering: event filtering, file cache, debouncing, error handling, rebuild pipeline
- [x] Manual testing: edit a reference file, verify the graph rebuilds

---

## Step 7 -- Testing and Polish (Phase 1 Gate)

**Priority:** Medium (Phase 1 gate)
**Depends on:** Steps 0-6

- [x] Achieve reasonable test coverage for parser, graph, models, and watcher (293 tests)
- [x] Run `just lint` and fix all linting issues
- [x] Run `just typecheck` and fix type errors
- [x] `--version` flag on the CLI (done in Step 0: `craftgraph, version 0.1.0`)
- [x] Verify the full end-to-end workflow:
  1. [x] `just check ./recipes/` reports cycles (or "no cycles found")
  2. [x] `just view ./recipes/` opens a browser with the dependency graph
  3. [x] `just watch ./recipes/` watches for changes and auto-rebuilds
- [x] Update README.md with usage instructions (screenshots deferred until Phase 2 GUI)

---

## Step 8 -- Distribution

**Priority:** Lower (final polish)
**Depends on:** Steps 0-7 (Phase 1 complete)

- [x] Test PyInstaller bundling: `just build` (fixed: `--collect-data pyvis` for Jinja2 templates, explicit `__version__` for Click)
- [x] Verify the resulting binary works standalone: `--version`, `check -v`, `view -o` all work
- [x] Add a GitHub Actions workflow for CI (lint, test, build on push/PR; binary build on tags)
- [x] Tag a v0.1.0 release
- [ ] Stage project files properly, do not stage or commit the .claude/ folder nor the CLAUDE.md nor the PLAN.md

---

## Cross-Platform Distribution Notes

> Reference for Step 8 and Phase 2 planning.

### Platform compatibility

| Dependency | Windows | Linux | macOS | Type |
|---|---|---|---|---|
| Python 3.14 | Yes | Yes | Yes | Runtime |
| NetworkX | Yes | Yes | Yes | Pure Python |
| Click | Yes | Yes | Yes | Pure Python |
| Watchdog | Yes | Yes | Yes | Platform-specific backends (ReadDirectoryChangesW / inotify / FSEvents) |
| Pyvis | Yes | Yes | Yes | Generates static HTML |
| Dear PyGui | Yes | Yes | Yes | Pre-built wheels; OpenGL on Win/Linux, Metal on macOS |
| PyInstaller | Yes | Yes | Yes | **Cannot cross-compile** (see below) |

### PyInstaller limitation: no cross-compilation

PyInstaller bundles the Python interpreter into the binary, so it must run
on the target OS. Build on Windows to get `.exe`, on Linux to get a Linux
binary, on macOS to get a macOS binary. You cannot build a Linux binary
from a Windows machine (or vice versa).

**Solution:** GitHub Actions matrix build (`windows-latest`, `ubuntu-latest`,
`macos-latest`). Each runner builds for its OS and attaches the artifact to
a GitHub Release. This is standard practice for Python desktop tools.

### Nuitka as a possible alternative

Nuitka compiles Python to C, then to native machine code. Produces smaller,
faster binaries. Same cross-compile limitation applies. Worth evaluating if
binary size or cold-start time becomes an issue.

### CLI + GUI coexistence

The architecture supports both in a single binary:
- `craftgraph check|view|watch` -- CLI commands, no GUI window
- `craftgraph gui` (Phase 2) -- native Dear PyGui window via OpenGL/Metal

Dear PyGui is an optional dependency (`pip install craftgraph[gui]`), so
the CLI-only binary stays small. The GUI binary includes the extra dependency.

---

## Phase 2 -- GUI Editor (Future)

> Broken into sub-steps by complexity. Each sub-step is a meaningful
> release on its own. Later sub-steps build on earlier ones but are
> significantly more complex.

### Step 9 -- Read-Only Node Viewer (Low complexity)

**Priority:** Deferred
**Depends on:** Steps 0-7
**Effort:** Small -- builds directly on existing parser + graph code

This is the "quick win" that replaces the Pyvis browser visualization with
a native Dear PyGui window. No editing, just viewing.

- [ ] Set up Dear PyGui application window with basic menu bar
- [ ] Load parsed recipes into Dear PyGui's node editor widget (read-only)
- [ ] Each recipe = a visual node displaying ItemID, recipe type, ingredient count
- [ ] Ingredient connections rendered as links between nodes
- [ ] Color nodes by type (raw material / intermediate / end product) -- reuse existing `classify_nodes()`
- [ ] Live cycle detection highlighting -- reuse existing `find_cycles()`
- [ ] Wire into CLI: `craftgraph gui <path>` opens the viewer

### Step 10 -- EasyMarkup Serializer (Low-medium complexity)

**Priority:** Deferred
**Depends on:** Step 9
**Effort:** Medium -- inverse of the parser, but the data model is well-defined

The serializer is a prerequisite for all editing features. It converts the
in-memory data model back to valid EasyMarkup `.txt` files. This is the
inverse of `parser.py` and should produce output that round-trips cleanly
(parse -> serialize -> parse gives the same result).

- [ ] Implement `craftgraph/serializer.py`:
  - `serialize_file(parsed_file: ParsedFile) -> str` -- converts a ParsedFile back to EasyMarkup text
  - Handle all 10 block types (ModifiedRecipes, AddedRecipes, AliasRecipes, etc.)
  - Proper indentation, quoting of display names/tooltips, escape sequences
  - Nested blocks for CustomFabricators (tabs + recipes inside)
- [ ] Round-trip tests: parse reference files, serialize, re-parse, assert equal
- [ ] Wire into CLI: `craftgraph export <path> -o <output>` serializes parsed recipes

### Step 11 -- Interactive Node Editor (Medium complexity)

**Priority:** Deferred
**Depends on:** Step 10 (needs serializer for saving)
**Effort:** Medium-large -- Dear PyGui node editor interactions + state management

This is where the viewer becomes an editor. Requires careful state management
to keep the data model, visual nodes, and file output in sync.

- [ ] Drag-and-drop ingredient connections between nodes
- [ ] Inline editing of recipe fields (amounts, item IDs, crafting station)
- [ ] Add new recipe nodes (right-click context menu)
- [ ] Delete nodes and connections
- [ ] Undo/redo stack
- [ ] Save to `.txt` files via the serializer
- [ ] Live cycle detection on every edit (flag new cycles immediately)

### Step 12 -- Multi-Panel Layout + Bidirectional Code Editor (High complexity)

**Priority:** Deferred
**Depends on:** Step 11
**Effort:** Large -- this is a major feature and likely its own release

This is the most ambitious step. It adds the full IDE-like layout with
bidirectional sync between visual editing and code editing. Each panel
needs to stay in sync with the others in real time.

- [ ] **Multi-panel layout** -- 1x2 split (or 2x2 grid):
  - **Left panel (large):** Node-based editor from Step 11
  - **Top-right panel:** EasyMarkup code editor (bidirectional)
  - **Bottom-right panel:** Mini dependency graph overview
  - Alternative: 1x2 where right side is a vertical split (code on top, mini graph on bottom)
- [ ] **Bidirectional code editor:**
  - Editable text area showing live EasyMarkup output
  - Node changes serialize to code in real time (model -> text via serializer)
  - Code changes parse back to nodes in real time (text -> model via parser)
  - Debounced re-parsing (don't parse on every keystroke, wait for pause)
  - Error-tolerant parsing mode: keep last valid state when code is mid-edit, show parse errors inline without breaking the editor
- [ ] **Mini dependency graph:**
  - Small auto-updating overview of the full dependency tree
  - Highlights the currently selected node/recipe
  - Click-to-navigate: clicking a node in the mini graph selects it in the main editor
  - Helps orient the user in large mod projects with hundreds of recipes

---

## Quick Reference: Dependency Graph

```
Step 0 (Scaffolding)
  |
  v
Step 1 (Data Model)
  |
  v
Step 2 (Parser)
  |       \
  v        \
Step 3      \
(Graph)      \
  |    \      \
  v     v      v
Step 4  Step 5  Step 6
(CLI)   (Viz)   (Watcher)
  |       |       |
  v       v       v
      Step 7 (Polish)
          |
          v
      Step 8 (Distribution)
          |
          v
  Phase 2 -- GUI Editor
          |
    Step 9  (Node Viewer)       -- Low complexity, quick win
          |
    Step 10 (Serializer)        -- Low-medium, prerequisite for editing
          |
    Step 11 (Interactive Editor) -- Medium, core editing features
          |
    Step 12 (Multi-Panel + Bidir) -- High, IDE-like experience
```
