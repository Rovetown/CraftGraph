# Changelog

All notable changes to CraftGraph are documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [0.1.0-alpha] -- Unreleased

First working release. Covers the full Phase 1 CLI pipeline (parse, graph,
visualize, watch, export) and the Phase 2 interactive GUI node editor with
editing, undo/redo, serialization, and autocomplete.

### Added

#### Project Scaffolding
- Python 3.14 project with uv package management and lockfile
- `justfile` with recipes for run, test, lint, format, typecheck, build, clean
- GitHub Actions CI workflow (lint, test, build on push/PR; binary on tags)
- PyInstaller bundling into standalone binary (`just build`)

#### Data Model (`models.py`)
- Core dataclasses: `Ingredient` (frozen), `BlockType` enum (all 10 CC3 types)
- Recipe hierarchy via dataclass inheritance mirroring CC3's C# classes:
  `ModifiedRecipe` -> `AddedRecipe` -> `AliasRecipe` -> `CustomFood`
- Supporting types: `CraftingTab`, `CustomFabricator` (with nested tabs/recipes),
  `CustomSize`, `CustomBioFuel`, `CustomFragmentCount`, `MovedRecipe`
- `ParsedFile` container with `all_recipes` property traversing fabricator nesting

#### EasyMarkup Parser (`parser.py`)
- Full EasyMarkup tokenizer: comment stripping (`#...#`), escape sequences,
  quoted strings, whitespace normalization (matches CC3's `CleanValue()`)
- Block-level parser: top-level block type detection, parenthesis nesting,
  key-value pairs, nested ingredient lists, comma-separated value lists
- Case-insensitive key matching, optional semicolons
- CC3 entry mapping for all 10 block types including `CustomFabricator`
  with nested `CustomCraftingTabs` and recipes
- `parse_file()` and `parse_directory()` top-level functions
- BOM handling (`utf-8-sig` encoding) for Windows-generated files

#### Graph Builder (`graph.py`)
- `build_graph()`: NetworkX DiGraph from parsed files (nodes = ItemIDs,
  edges = dependency relationships, metadata: recipe_type, source_file, is_crafted)
- `find_cycles()`: cycle detection via `networkx.simple_cycles()`
- Query helpers: `get_dependencies()`, `get_dependents()`, `classify_nodes()`
  (RAW_MATERIAL / INTERMEDIATE / END_PRODUCT classification)

#### CLI (`cli.py`)
- `craftgraph check <path>` -- parse and report circular dependencies
- `craftgraph view <path>` -- parse, build graph, generate Pyvis HTML visualization
- `craftgraph watch <path>` -- watch directory for changes, auto-rebuild
- `craftgraph export <path>` -- serialize parsed recipes back to EasyMarkup
- `craftgraph gui <path>` -- open interactive Qt node editor (PySide6 + NodeGraphQt)
- `--verbose` / `-v` flag for detailed output
- `--output` / `-o` flag for output file location
- `--version` flag
- Error handling at CLI boundary: file-not-found, parse errors, `MappingError`

#### Pyvis Visualizer (`visualizer.py`)
- Interactive HTML graph via Pyvis with dark background, inline CDN
- Nodes colored by type: raw materials (green), intermediates (blue),
  end products (gold). Size proportional to degree.
- Tooltips with recipe type, source file, ingredients, used-by list
- Circular dependency edges highlighted in red (width 3)
- Hierarchical layout with `sortMethod: "directed"`, top-down flow
- Auto-open in default browser

#### File Watcher (`watcher.py`)
- Watchdog-based directory tree watcher for `.txt` file changes
- 300ms debounce for rapid saves
- Incremental re-parse: only changed file re-parsed, full graph rebuilt
- Error-tolerant: unparseable mid-save files warn but keep cached version

#### EasyMarkup Serializer (`serializer.py`)
- `serialize_file()`: converts `ParsedFile` back to valid EasyMarkup text
- Handles all 10 block types including nested `CustomFabricator` structures
- Proper indentation, quoting, escape sequences
- Default-value omission for clean output (matches modder conventions)
- Round-trip verified: parse -> serialize -> parse produces identical results
- UTF-8 output on Windows (avoids cp1252 encoding errors)

#### GUI Node Editor (PySide6 + NodeGraphQt)
- **Qt application shell** (`qt_gui.py`):
  QMainWindow with horizontal splitter (70/30), NodeGraphQt graph widget (left),
  QPlainTextEdit code editor (right), per-file tabs with independent node graphs,
  menu bar (File/Edit/View), status bar with undo/redo descriptions.
- **Node subclasses** (`qt_nodes.py`):
  10 node classes for all CC3 block types, `NodeKind` enum, `NODE_REGISTRY`,
  `CraftGraphBaseNode(BaseNode)` with `model_ref` property, recipe inheritance
  chain (Modified -> Added -> Alias -> CustomFood), custom widgets
  (`NodeIntEdit`, `NodeFloatEdit`), dynamic ingredient slots, port constraints.
- **Model-to-node sync** (`sync.py`):
  `populate_graph()`, `connect_ingredients()`, `connect_hierarchy()`,
  `compute_hierarchy_layout()`, `highlight_cycle_edges()`, `UIToModelHandler`,
  `SyncGuard` for bidirectional sync without feedback loops.
- **Code editor** (`code_editor.py`):
  QPlainTextEdit with line number gutter, QCompleter autocomplete.
  EasyMarkup syntax highlighting via `highlighter.py`.
- **Autocomplete** (`vanilla_ids.py`, `NodeCompletionPopup` in `qt_gui.py`):
  TechType ID completion from vanilla (498 IDs) + mod-compat (120 IDs) static
  lists. IDE-style popup for node widgets (avoids QGraphicsProxyWidget focus
  issues). QCompleter for code editor. Path completions from parsed recipes.
- **Persistent node positions** (`layout_store.py`):
  Sidecar `.craftgraph/layout.json` file next to recipe files, positions
  restored on reload, updated on node drag.
- **Sprite support** (`sprite_loader.py`):
  Asset PNG scanning, case-insensitive ItemID-to-path lookup, wired into
  node creation paths.

#### Parser/Serializer Refinements (Step 11e)
- Serializer escape strategy aligned with CC3's `EscapeSpecialCharacters()` quoting behavior
- Line endings: serializer uses `\r\n` on Windows for better round-trip compatibility
- Integration tests for all 10 block types via `original-source/CustomCraft3/SampleFiles/`
- Ingredient validation: `validate_parsed_file()` warns when `Required` is outside CC3's 1-25 range
  (non-blocking -- parser still accepts any value, warnings displayed in CLI commands)

### Changed

- **GUI migration: Dear PyGui -> PySide6 + NodeGraphQt** (Steps M1-M8):
  Replaced the entire DPG-based GUI with a Qt retained-mode stack. Removed
  `gui.py`, `gui_nodes.py`, `gui_editor.py`, `gui_autocomplete.py` and their
  DPG-specific tests/scripts. Dropped `dearpygui` and `scipy` dependencies.
  Renamed CLI command `qt-gui` to `gui`. All GUI functionality preserved and
  improved in the new stack (qt_gui.py, qt_nodes.py, code_editor.py,
  highlighter.py, sync.py).
- Removed `[project.optional-dependencies] gui` group (DPG). Qt deps are now
  under `[project.optional-dependencies] qt`.

### Fixed

- Windows BOM prefix in parsed files (`utf-8-sig` encoding)
- Pyvis HTML layout height (`100%` -> `100vh`)
- Windows UTF-8 output encoding for serializer CLI
