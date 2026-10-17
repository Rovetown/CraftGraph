# Changelog

All notable changes to CraftGraph are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.1.0-alpha.1]

First public release. Early, rough in places, and source-install only: no packaged
installer is built yet.

### Added

- **Node based recipe editor** covering all 10 CustomCraft3 block types:
  ModifiedRecipes, AddedRecipes, AliasRecipes, CustomFabricators, CustomCraftingTabs,
  CustomFoods, CustomBioFuels, CustomSizes, CustomFragmentCounts and MovedRecipes.
  Ingredients are connections between nodes, and every field edits inline.
- **Bidirectional code editor.** A syntax-highlighted EasyMarkup view sits beside the
  graph; an edit in either view updates the other.
- **Live cycle detection.** Offending edges render red, and a link that would close a
  loop warns before it is made.
- **Project Issues window** (`Edit > Find Issues`) listing orphans, cycles and
  unresolved references, with click-to-jump to the owning node.
- **Autocomplete** on item IDs and paths, drawing on the vanilla TechType list, the
  mod-compat list and every ID the open mod folder defines.
- **Per-file tabs**, each with an independent graph, plus persistent node positions in
  `.craftgraph/layout.json` next to the mod.
- **Folder watching** that reparses on external saves.
- **What's New and Getting Started carousels**, shown on first run and from the Help
  menu.
- **CLI commands**: `check`, `view`, `watch`, `export`, `gui`, `register`,
  `unregister`. Unlock relationships render as distinct edges in the HTML graph:
  solid green for `Unlocks`, dashed orange for `UnlockedBy`.
- **Central logging** with a `--log-level` flag, a Settings control, and automatic
  pruning of log files older than 7 days.

### Changed

- **Dependencies split by role.** PySide6 is a hard runtime dependency, so the `qt`
  extra now only declares NodeGraphQt. `pyvis` moved behind a `visualizer` extra and
  `rich` behind a `pretty` extra, since the GUI needs neither and `log_setup` falls
  back to a standard library handler when `rich` is absent.
- **Dual executable split.** A dedicated GUI entry point lets the build produce a
  windowed binary and a console CLI binary without either dragging in the other.
- **Bundle trimmed** by stripping Qt translations, unused plugin backends and duplicate
  DLLs after the PyInstaller run.
- **Diagnostics are off in release builds** unless switched on in Settings, so a
  shipped binary stops paying for perf instrumentation.

### Fixed

- Pink checkbox and radio indicators on Windows 11, which inherited the OS accent color
  and hid the check glyph against the dark theme.
- Tab tooltips leaked the full filesystem path; they now show the file name only.
- Several ingredient-sync defects around orphan nodes, cross-file `Path` targets and
  field edits landing on the wrong node after a tab switch.

### Security

- `msgpack` raised to 1.2.3. Versions up to 1.2.0 read out of bounds when an `Unpacker`
  is reused after a caught error. CraftGraph uses the one-shot API and is not on that
  path, but project files are untrusted input.
- `setuptools` raised to 84.0.0 for the sdist MANIFEST.in exclusion bypass. Build-time
  and transitive only.

[Unreleased]: https://github.com/Rovetown/CraftGraph/compare/v0.1.0-alpha.1...HEAD
[0.1.0-alpha.1]: https://github.com/Rovetown/CraftGraph/releases/tag/v0.1.0-alpha.1
