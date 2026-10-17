# TODO

Remaining build plan. Completed work lives in `CHANGELOG.md` and git history; this
file tracks only what is left, plus a record of the performance techniques shipped.

---

## Test infrastructure

- [x] **Faster, nicer test runs.** `test_qt_gui`, `test_perf_stress`, `test_hwnd_stress`,
  and `test_incremental_rebuild_parity` are tagged `@pytest.mark.slow` at module level.
  `just test` excludes them (1490 passed / 5 skipped in ~10s); `just test-all` runs
  the full suite; `just test-slow` runs only the tagged set. The autouse
  `_reap_file_watchers` reaper was hoisted from `test_qt_gui.py` to `tests/conftest.py`
  so any test file that builds a `CraftGraphWindow` is still safe from the leaked
  Watchdog thread / heap-corruption regression once test_qt_gui is excluded. Later
  retired entirely at `f29057c` after sub-project 4 routed every construction
  through `make_test_window(qtbot)` and qtbot's lifecycle replaced the reaper.

- [x] **Defensive `save_project` / closeEvent on empty `project_path`.** Shipped:
  `closeEvent` (both fast path and DISCARD) now routes through a `_persist_project_state`
  helper that no-ops when `self._project is None or not self._project.project_path`.
  The two `TestProjectCustomIdPersistence` try/finally workarounds are gone; a new
  `test_close_with_empty_project_path_is_no_op` regression test guards the contract.

- [x] **Robust patch-script pattern for mass test-file refactors.** Recorded in
  the contributor notes: use ` *` (not `\s+`) for indent,
  handle multi-line `def test_x(...):` signatures across newlines, run the suite
  after each script.

> **Resolved knowledge -- headless test hangs.** Traced to three causes:
> (1) **Pipe buffering** -- `2>&1 | tail` only flushes the tail of stdout; redirect to
> a file with `>file 2>&1` and tail the file instead.
> (2) **Modal dialog stubs** -- production moved from `QDialog.exec_` to `QDialog.exec`
> (commit a46e127); test monkey-patches still on the underscore alias stopped
> intercepting the real modal and blocked the headless loop.
> (3) **Leaked watcher threads -> heap corruption** -- `test_qt_gui.py` windows that
> load a folder start a Watchdog observer thread; tests never closed their windows,
> so observer threads leaked and one racing main-thread GC corrupted the heap.
> Fixed by the autouse `_reap_file_watchers` teardown. Any future fixture that starts
> background threads must reap them on teardown.

---

## Pre-alpha

- [x] **TabID autocomplete in `Path` fields.** Shipped: `_update_path_completions`
  now mirrors `_path_targets_from_parsed_files` and adds `Fab/TabID` and
  `parent/TabID` composites to `_path_words` for every CraftingTab (both top-level
  `pf.crafting_tabs` and ones nested inside `pf.custom_fabricators`). Previously the
  validator accepted those paths but the autocomplete dropdown only suggested them
  after a recipe already used them once. Regression guard: `TestPathAutocompleteTabIDs`
  in `test_qt_gui.py` (2 tests).
- [x] **Unlock / UnlockedBy visualization + editing.** Shipped in three pieces:
  (1) `_ID_WIDGET_NAMES` extended with `unlocks`, `unlocked_by`, `linked_item_ids`
  so TechType autocomplete attaches to all three CSV fields on summon; (2) `build_graph`
  now emits unlock edges with an `edge_kind` attribute (`ingredient`/`unlocks`/
  `unlocked_by`), and ingredient takes precedence when a pair overlaps; (3)
  `visualizer.generate_html` reads `edge_kind` and styles `unlocks` solid green
  (`UNLOCKS_EDGE_COLOR`), `unlocked_by` dashed orange (`UNLOCKED_BY_EDGE_COLOR`);
  cycle red still overrides. Regression guards: `TestNodeAutocomplete` (+2 tests),
  `TestBuildGraphUnlocks` (5 tests in `test_graph.py`), `test_visualizer.py` (new file,
  4 tests). NOT shipped: in-Qt-node-editor visual overlay for unlock relationships --
  CSV-content-driven overlay edges between nodes were deferred as a separate sub-project.
- [x] **Full filename tooltip on tab hover.** Shipped: all 3 production
  `setTabToolTip` call sites in `qt_gui.py` (initial `_create_file_tab`, watcher
  diff add path, folder-load loop) now pass `pf.source_path.name` instead of
  `str(pf.source_path)`. Hover shows `MyRecipes.txt` instead of leaking the parent
  directory path. `TestTabBarTooltips::test_loaded_file_tab_tooltip_is_filename`
  guards both halves: filename is present, directory string is not.

- [x] **Project Issues window.** Shipped. Menu entry `Edit -> Find Issues...`
  opens a modeless QDialog with a `QTreeWidget` of 3 sections (Orphans / Cycles /
  Unresolved References) populated from the pure-Python
  `craftgraph.diagnostics.find_project_issues`. Click a row to jump to the
  defining tab + node via `_jump_to_id`. Auto-refreshes on model change and
  watcher diff via a 300 ms debounced `QTimer`. All 5 sub-tasks below complete.

  - [x] **(1) Issue-detection data layer.** Shipped: `craftgraph/diagnostics.py`
    is a pure-Python (no Qt) module exporting `OrphanIssue`, `CycleIssue`,
    `UnresolvedRefIssue`, `ProjectIssues`, and
    `find_project_issues(parsed_files, *, known_extra_ids=None) -> ProjectIssues`.
    Orphans = recipe items with in-degree 0 across ingredient + unlock edges;
    cycles delegate to `graph.find_cycles`; unresolved refs scan `ingredients`,
    `unlocks`, `unlocked_by`, and `linked_item_ids` against a case-insensitive
    known set (project-defined IDs + vanilla + mod-compat). `Path` validation is
    intentionally NOT covered yet -- requires moving `_path_targets_from_parsed_files`
    out of `qt_gui.py`; leave that for a follow-on. 18 tests in
    `tests/test_diagnostics.py`, including an integration test against the
    committed `tests/fixtures/mini_mod/`.
  - [x] **(2) Empty window scaffolding.** Shipped: `_ProjectIssuesDialog` is a
    modeless `QDialog` (does not block the main window). New menu entry
    `Edit -> Find &Issues...` sits next to `Find Node...`. `CraftGraphWindow`
    lazily creates the dialog on first trigger and stores it on
    `self._project_issues_window`; `_on_open_project_issues` raises and activates
    on every subsequent trigger so the action is idempotent. The dialog shows a
    centered placeholder QLabel: "No project loaded -- open a folder or file to
    scan for issues." 6 tests in `TestProjectIssuesWindow` cover: menu-action
    presence, first-trigger creation, second-trigger same-instance,
    placeholder-text visible, close-doesn't-unload-data, reopen-after-close.
  - [x] **(3) Render the data.** Shipped: `_ProjectIssuesDialog` now uses a
    `QTreeWidget` with 3 top-level sections (`Orphans`, `Cycles`,
    `Unresolved References`), counts in headers (`Orphans (3)`), empty sections
    show a single literal "None" child (visible, so users see the gate passed).
    Row formatting: orphans = `ItemID  -  filename.txt`, cycles =
    `A -> B -> A` (loop closed visually), unresolved = `Owner.ref_type -> Target  -  filename.txt`.
    `CraftGraphWindow._refresh_project_issues` collects parsed files from open
    tabs, runs `find_project_issues`, and calls `populate`. Refresh fires on
    every menu trigger (open or already-open) so the user always sees current
    state. NOT yet shipped: auto-refresh on save / file change -- sub-task (5).
    Line numbers in rows -- parser doesn't track line offsets in the model;
    deferred until that becomes a separate need. 5 new tests in
    `TestProjectIssuesWindow` (sections, empty-state, orphan row, cycle row,
    unresolved row); the placeholder-text test from sub-task (2) was replaced
    with `test_window_shows_section_headers` to track the new contract.
  - [x] **(4) Jump-to-tab/node on row click.** Shipped: extracted `_jump_to_id`
    from the existing `_go_to_definition` so the same plumbing accepts a bare
    item id (no source node needed). `_ProjectIssuesDialog` gained an
    `item_activated = Signal(str)` and stores per-row jump targets in
    `Qt.UserRole` data; double-click / Enter on a row emits the signal.
    `_on_open_project_issues` connects the signal to `_jump_to_id` on first
    creation. Target id per row: orphan -> the item itself; cycle -> the cycle's
    first item; unresolved -> the OWNER recipe (target doesn't exist by
    definition). Section headers and the "None" placeholder rows carry no
    target and are silently ignored. NOT shipped: auto-opening files that are
    in the project folder but not currently in any tab -- the issues window
    only sees data from open tabs, so the case doesn't arise yet. 4 new tests
    in `TestProjectIssuesWindow` (orphan / cycle / unresolved / none-row noop).
  - [x] **(5) Auto-refresh on change.** Shipped: `CraftGraphWindow` gained a
    single-shot 300 ms `QTimer` (`_project_issues_refresh_timer`) and a
    `_schedule_project_issues_refresh()` helper that restarts the timer on each
    call (multiple rapid edits collapse to one refresh). Hooked into
    `_on_model_changed` (covers EditHistory paths -- user edits, undo, redo,
    code-editor reparse) and `_apply_watcher_diff` (covers external file
    changes via Watchdog). Schedule is a no-op when the dialog has never been
    opened or is hidden -- no point scanning while nobody is looking. 4 new
    tests in `TestProjectIssuesWindow`: no-op when never opened, no-op when
    hidden, model-change starts the timer, end-to-end count update on refresh.

- [x] **Welcome screen: clear recent list.** Shipped: `WelcomeWidget` now
  accepts an optional `on_clear_recent` callback and renders a flat "Clear"
  button in the Recent Projects header (disabled when the list is empty so
  the affordance stays visible without firing a no-op). `CraftGraphWindow`
  wires it to the existing `_on_clear_recent` handler, which now also calls
  `welcome.set_recent_entries([])` so both clear paths (welcome button +
  Open Recent menu's "Clear Recent" entry) keep the two views in sync.
  `WelcomeWidget.set_recent_entries` rebuilds the left column in place via
  `replaceWidget`, falling back to the existing empty-state message.
  Regression guard: `TestClearRecent` (4 tests in `test_welcome.py`).

- [x] **Welcome screen: clickable links.** Shipped: the right-column links
  were already real `QLabel`s with `setOpenExternalLinks(True)` and
  `<a href>` bodies; the URLs themselves were `"#"` placeholders. Now
  promoted to module-level constants in `welcome.py`: `GITHUB_URL`
  (Rovetown/CraftGraph repo placeholder, matches the About dialog's
  `_AboutDialog.GITHUB_URL`), and `CC3_WIKI_URL` (the real PrimeSonic
  CustomCraft3 source on GitHub). Formerly also
  `DISCORD_URL` (a clearly-fake `discord.gg/PLACEHOLDER` so a future
  search-and-replace finds it). Regression guard: `TestExternalLinks`
  in `test_welcome.py` (every link uses `setOpenExternalLinks(True)`,
  no leftover `href="#"`, each `_LINKS` entry renders exactly once).

- [x] **Widget pink-fill -> dark fill (project-wide, theme-driven).**
  Shipped (option 1 from the original spec). Root cause: unstyled
  `QCheckBox::indicator` / `QRadioButton::indicator` widgets fall back to
  the OS personalization accent color, which on Win11 reads as bright
  pink against the dark theme and hides the check glyph. Added
  `_indicator_qss(accent, *, light=False)` in `qt_gui.py` which produces
  rules for both indicator kinds (16x16, theme-driven unchecked + hover +
  disabled fills, solid accent-colored checked fill). Wired into both
  `_SettingsDialog.__init__` (overlays the dialog's `_STYLE`) and
  `_build_app_stylesheet` (covers welcome + main window). Qt's QSS
  `background:` rule erases the native check glyph, so the `:checked`
  state references SVG icons -- `indicator_check.svg` (white check
  stroke) and `indicator_radio_dot.svg` (white center dot) -- written
  to `<cache_dir>/icons/` on first call by `_indicator_glyph_paths()`
  and referenced via `image: url(<file path>)`. Qt 6.11's QSS parser
  does **not** accept `data:image/svg+xml;base64,...` URIs (verified
  empirically: indicator paints solid accent, glyph never renders); the
  on-disk files are the workaround. Regression guards in
  `test_qt_gui.py::TestIndicatorStyling` (5 tests): both rule kinds
  present in the QSS, accent passes through, `:checked` rule includes
  an `image: url(` clause, glyph files exist on disk as valid SVG, main
  window + settings dialog stylesheets both contain the indicator
  rules. Option 2 (user-configurable indicator color) was deferred --
  the helper is the natural hook point if it ever becomes wanted.

---

## Release-build dependency hygiene

Make sure the shipped binary only bundles packages that the runtime app
actually imports. Today the `[dependency-groups].dev` table in
`pyproject.toml` is a grab-bag and `[project].dependencies` has at least
one questionable entry (`types-networkx` is a stub-only package -- it
has no runtime code, so PyInstaller will pull it into the bundle for
nothing). Goal of this section: every runtime dep is in
`[project].dependencies`, every dev-only tool is in
`[dependency-groups].dev`, and the PyInstaller invocation explicitly
excludes the dev tools so a stray import path cannot drag them in.

- [x] **Audit current dep classification.** Shipped. Final layout:
  - `types-networkx` removed from `[project].dependencies` -- it's a
    PEP 561 `*-stubs` package with no runtime code; the dev copy is
    the only one needed.
  - `mypy` / `ruff` duplicate pins in `dev` collapsed to one entry
    each. Dev table now grouped + commented (type-checkers, optional
    UX deps, build/packaging, test suite).
  - `rich` kept in `dev` -- now genuinely optional at runtime
    (`log_setup.configure_logging` falls back to a stdlib
    `StreamHandler` when rich is missing, and skips
    `rich.traceback.install`). Also exposed as a `[pretty]` optional
    extra so end users who want colored CLI logs can opt in without
    pulling the rest of the dev toolchain.
  - `pyvis` kept in `dev` -- now lazy-imported inside
    `visualizer.generate_html` and surfaced as a new `[visualizer]`
    optional extra. CLI `view` / `watch` lazily import via
    `_load_generate_html` and print an install hint
    (`pip install "craftgraph[visualizer]"`) instead of failing at
    startup.
  - `craftgraph.app_dirs.is_dev()` added: returns False on
    `sys.frozen` PyInstaller bundles, True otherwise; overridable via
    `CRAFTGRAPH_DEV=1`. `perf_diag.report_frame` now early-returns
    when not dev, so the WARNING-level `frame_budget_violation` log
    never reaches `craftgraph.log` in a shipped binary.
  - All other `dev` entries (`mypy`, `pyrefly`, `ruff`, `ty`,
    `pytest*`, `hypothesis`, `pyinstaller`) confirmed not imported
    from `craftgraph/` and stay dev-only.

  Tests added (8): `TestIsDev` (4), `test_report_frame_is_noop_in_release_build`,
  `test_fallback_when_rich_is_missing`,
  `test_generate_html_raises_pyvis_not_installed_when_missing`,
  `test_visualizer_module_does_not_import_pyvis_at_top`.

- [x] **Diagnostics toggle, off by default in release.** Shipped.
  `app_dirs.perf_diagnostics_enabled()` returns True in dev builds and
  reads the `perf_diagnostics_enabled` setting (default False) in
  release builds. `perf_diag.report_frame`, `perf_diag.measure`, and
  the `hwnd_diag` / `perf_diag` `install_logger` calls in
  `launch_qt_gui` all consult the helper and no-op when off. The
  Settings dialog gained a Diagnostics group in the General tab with a
  single "Enable performance diagnostics" checkbox (tooltip explains
  the dev-build override + that it takes effect on next launch). End
  user impact in a shipped binary: no `perf.log` file, no
  frame-budget WARNING records in `craftgraph.log`, no HWND-spike
  status-bar messages, unless the user explicitly enables them.
  Regression guards: `TestPerfDiagnosticsEnabled` (3 tests in
  `test_app_dirs.py`), `test_measure_is_silent_in_release_build`,
  updated `test_report_frame_is_noop_in_release_build`.

- [x] **PyInstaller exclude list for dev-only modules.** Shipped.
  `just build` now passes `--exclude-module` for every dev tool plus the
  optional UX deps the GUI doesn't actually import: `pyvis`, `IPython`,
  `rich`, `hypothesis`, `mypy`, `pyrefly`, `ruff`, `ty`, `pytest`,
  `pytest_sugar`, `pytest_clarity`, `pytest_qt`, `pytest_benchmark`,
  `pytest_cov`, and `PyInstaller` itself. `rich` is safe to exclude
  because `log_setup` now falls back to a stdlib `StreamHandler` when
  the import fails. `--collect-data pyvis` was dropped from the build
  command since the GUI bundle no longer needs pyvis assets at all.
  Verify a fresh bundle still launches via `just build`; any
  `ImportError` at launch means a production path silently depended on
  one of the excluded modules and the relevant flag has to come back
  out.

- [x] **Verify with `uv sync` modes.** Shipped. The original entry
  proposed running `uv sync --no-dev` inside `just build`, but that
  fails because `pyinstaller` itself is a dev dep. Replaced by two
  separate verification recipes:
  - `just sync-prod` -- `uv sync --no-dev --extra qt`, the exact
    install path end users get from `pip install craftgraph[qt]`.
  - `just smoke-no-dev` -- now imports every `craftgraph.*` module
    via `scripts/smoke_imports.py` (42 modules walked), then parses a
    Tier A workload. Raises `ImportError` if any production code
    accidentally depends on a dev-only package. Currently green: all
    42 modules import cleanly under `--no-dev --extra qt`.

- [x] **Document the dependency rule.** Shipped. The contributor notes
  gained a `Dependency policy` section covering: which table to pick (`[project].dependencies` vs `dev`
  vs `[project.optional-dependencies]`), `uv add` flags for each,
  the verification recipes (`smoke-no-dev` / `sync-prod`), and the
  rule that type-stub packages always belong in `dev`.

- The previous `Cross-check against the module-usage dump` entry was
  folded into Step 7 of the `Bundle size reduction plan` under
  `## Distribution / installer`. It depends on the
  `CRAFTGRAPH_DUMP_MODULES` instrumentation landing first, so it
  lives there as part of that work rather than as a standalone
  hygiene item.

---

## Distribution / installer

Ships CraftGraph as a real Windows desktop app instead of a portable `--onefile`
binary. Solves the ~2.8 s PyInstaller bootloader cost on every launch by extracting
the bundle once at install time, then running directly from the installed location
on every subsequent launch (~250 ms cold start, dev parity).

- [x] **Switch PyInstaller from `--onefile` to `--onedir`.** Shipped: `just build`
  now invokes `pyinstaller --onedir --windowed --noconfirm` over
  `craftgraph/gui_entry.py` (a tiny module that calls `launch_qt_gui` directly,
  bypassing the Click CLI) and produces `dist/craftgraph/` (the exe + an
  `_internal/` deps folder). The bundled `craftgraph.exe` is a windowed GUI:
  double-clicking it opens the editor with no console flash. CLI subcommands
  (`check`, `view`, `watch`, `export`) remain available for source-install
  users via `uv run craftgraph ...` -- the bundled binary is GUI-only by design.
  `scripts/compare_dev_release.py` was calibrated against the old console build;
  re-running it against the windowed build hangs (the windowed exe ignores
  args and just opens the GUI). Either retire the script or have it build a
  separate `--console` companion bundle if the comparison ever matters again.
- [x] **Inno Setup installer.** Shipped: `craftgraph.iss` at repo root + `just
  installer` recipe (depends on `just build`). Wraps `dist/craftgraph/` into
  `dist/CraftGraph-Setup-<version>.exe` via lzma2/ultra64 compression. Per-user
  install by default with a "Install for all users" dialog override
  (`PrivilegesRequired=lowest` + `PrivilegesRequiredOverridesAllowed=dialog`).
  Per-user lands at `%LOCALAPPDATA%\Programs\CraftGraph\`; machine-wide lands
  at `C:\Program Files\CraftGraph\`. AppId UUID `B3A41E7F-2C5D-4F0A-8E91-7D3B6A2C5E4F`
  is **locked in for the life of the product** -- never regenerate, or Windows
  treats new versions as side-by-side installs instead of upgrades. License
  (MIT) shown on the welcome page and bundled as `LICENSE.txt` in the install
  dir so users can read it locally (also helps satisfy LGPL "license travels
  with distribution" for the bundled PySide6). Start Menu shortcut always
  created; desktop shortcut optional (unchecked by default). Requires Inno
  Setup 6 with `ISCC.exe` on PATH; no icon file yet (default Inno Setup icon).
- [x] **Bundle size reduction plan.** **Shipped end-to-end.** Final
  bundle: **110.8 MB unpacked** (down from 659.5 MB baseline, **-83.2%**).
  Beat the optimistic projection of 170-220 MB by a comfortable margin.
  All 8 numbered steps + the OS-aware refactor + the cc3-data
  micro-step landed; each step recorded its own measurement below.

  **Baseline (0.1.0-alpha.1, captured before any trim step):** **659.5 MB
  unpacked.** PySide6 alone is 588 MB (89% of total). Top offenders inside
  PySide6:

  | Component                        |    Size | Used? |
  |----------------------------------|--------:|-------|
  | `Qt6WebEngineCore.dll`           |  195 MB | No -- we never embed a browser |
  | `PySide6/resources/` (chromium)  |  101 MB | No -- pak files for WebEngine |
  | `PySide6/translations/` (*.qm)   |   57 MB | Only `_en.qm` strictly needed |
  | `PySide6/qml/`                   |   25 MB | No -- we use QGraphicsView, not Quick |
  | `opengl32sw.dll`                 |   20 MB | Maybe -- software OpenGL fallback |
  | `PySide6/plugins/`               |   15 MB | Mostly yes -- needs subdir audit |
  | `avcodec-61.dll`                 |   13 MB | No -- multimedia codec |
  | Qt3D / Quick3D / Designer DLLs   |  ~15 MB | No |
  | Core/Gui/Widgets/etc. DLLs       |  ~50 MB | Yes -- required |
  | `numpy` + `numpy.libs`           |   26 MB | Transitive -- needs verification |
  | `craftgraph/` package data       |   11 MB | Yes -- the cc3 reference files |
  | `shiboken6/`                     |    1 MB | Yes -- required runtime |

  Roughly 400+ MB is clearly unused content. Each step below records its
  post-build size + delta as it ships.

  Execute in this order (best ROI per minute of work first; verify with a
  full GUI smoke test after each step):

  1. **[SHIPPED] Exclude `PySide6.QtWebEngineCore` + `QtWebEngineWidgets`
     + `QtWebEngineQuick` + `QtWebChannel`.** Added to the
     `--exclude-module` list in `just build`. Also introduced a
     post-build cleanup helper (`scripts/postbuild_trim.py`) that
     deletes the matching `Qt6WebEngine*.dll` / `Qt6WebChannel*.dll` /
     `QtWebEngine*.pyd` binaries -- PyInstaller's `--exclude-module`
     filters Python modules only, not the binaries pulled by
     `--collect-submodules PySide6`. The helper runs from `just build`
     after pyinstaller and will grow to cover Step 3 (translation
     pruning) and Step 6 (plugin pruning) when those land.
     **Bundle: 659.5 MB -> 316.1 MB (-343.4 MB).** Verified by bundle
     launch smoke (process stays alive >5 s on cold start), 1563
     default tests green, 42 production modules import clean under
     `--no-dev --extra qt`.

  2. **[SHIPPED] Exclude `PySide6.QtQml` + `QtQuick` + `QtQuickWidgets`
     + `QtQuick3D` + `QtQuickControls2` + `Qt3DCore/Render/Input/Logic/
     Animation/Extras`.** Module exclusions in `just build` plus
     binary-side cleanup in `postbuild_trim.py` (Qt6Qml/Quick/3D DLLs +
     Qt6ShaderTools + Qt6Graphs). PyInstaller also auto-dropped the
     entire `PySide6/qml/` data tree once QtQml was excluded.
     **Bundle: 316.1 MB -> 219.1 MB (-97.0 MB, cumulative -440.4 MB
     from baseline).** Beat the 30-40 MB projection because PyInstaller
     pruned associated translations + plugins along with the modules.
     Verified: bundle launches >5 s smoke, 1563 default tests green,
     `smoke-no-dev` clean.

  3. **[SHIPPED] Strip non-English Qt translations.** Extended
     `postbuild_trim.py` with a `_KEEP_TRANSLATION_RE` filter
     (`r"_en(_[A-Z]{2})?\.qm$"`) that keeps `<module>_en.qm` and English
     regional variants (`_en_US`, etc.) and deletes every other `.qm`.
     Walks `_internal/PySide6/translations/` once -- 205 files removed,
     9 English `.qm` files kept (~4 KB total). Qt falls back to source
     strings when no locale match exists, so non-English Windows still
     gets a working English UI.
     **Bundle: 219.1 MB -> 207.5 MB (-11.6 MB, cumulative -452 MB from
     baseline).** Smaller than the 50 MB projection because PyInstaller
     already auto-pruned ~45 MB of translations during Steps 1 and 2
     (the excluded modules carried their translation files out with
     them). Verified: bundle launches >5 s, 1563 default tests green.

  4. **[SHIPPED] Exclude the remaining unused PySide6 modules.** Grepped
     `craftgraph/` for every candidate module name first; zero matches
     across the whole package. Excluded: `QtMultimedia`,
     `QtMultimediaWidgets`, `QtSpatialAudio`, `QtDesigner`, `QtUiTools`,
     `QtHelp`, `QtPdf`, `QtPdfWidgets`, `QtCharts`,
     `QtDataVisualization`, `QtLocation`, `QtPositioning`,
     `QtRemoteObjects`, `QtBluetooth`, `QtNfc`, `QtScxml`, `QtSensors`,
     `QtSerialPort`, `QtSerialBus`, `QtTextToSpeech`, `QtStateMachine`,
     `QtNetworkAuth`, `QtHttpServer`, `QtTest`, `QtVirtualKeyboard`,
     `QtWebSockets`, `QtWebView`, `QtCanvasPainter`. Binary cleanup in
     `postbuild_trim.py` for the matching DLLs + ffmpeg shipped with
     QtMultimedia (`avcodec*`, `avformat*`, `avutil*`, `swresample*`,
     `swscale*`). The post-build dump confirms only `QtCore`, `QtGui`,
     `QtWidgets`, `QtSvg`, `QtSvgWidgets`, `QtOpenGL`,
     `QtOpenGLWidgets`, `QtNetwork`, `QtPrintSupport`, `QtSql`,
     `QtXml`, `QtDBus` remain -- the bare minimum surface for a
     QtWidgets app + NodeGraphQt's Qt.py shim.
     **Bundle: 207.5 MB -> 155.0 MB (-52.5 MB, cumulative -504.5 MB
     from baseline).** Verified: bundle launches >5 s, 1563 default
     tests green, `smoke-no-dev` clean.

  5. **[SHIPPED] Audit and trim `numpy`.** Grepped our networkx usage:
     `nx.DiGraph`, `nx.simple_cycles`, `nx.descendants`/`ancestors`,
     `in_degree`/`out_degree`. All pure-Python; numpy is only needed for
     networkx's optional matrix-algebra paths (laplacian, spectral, etc.)
     which we never call. Added `--exclude-module numpy` (and
     `--exclude-module scipy` for the same reason) to `just build`.
     PyInstaller dropped both `numpy/` and `numpy.libs/` entirely at the
     analysis stage, so `postbuild_trim.py`'s defensive `numpy/` /
     `numpy.libs/` dir cleanup was a no-op this build (kept anyway as
     belt-and-braces for builds where module exclusion misses something).
     **Bundle: 155.0 MB -> 127.9 MB (-27.1 MB, cumulative -531.6 MB from
     baseline; PySide6 alone went from 588 MB to 83.8 MB).** Verified:
     bundle launches >5 s, 1563 default tests green (tests use the dev
     venv where numpy IS installed so dev-side import paths are
     unchanged; the bundle smoke is what confirms runtime doesn't
     need it).

  - **[SHIPPED, scope add-on] OS-aware `postbuild_trim.py` refactor.** Split the
     cleanup logic into platform-specific binary patterns vs. platform-
     agnostic data-tree / regex cleanups. Windows patterns now live in
     `_windows_binary_patterns()`; Linux + macOS get stub functions
     returning `{}` with TODO comments describing the filename
     conventions (Linux: `libQt6Foo.so.6.x.y` + OpenSSL-only TLS;
     macOS: `QtFoo.framework/` bundle dirs + native SecureTransport
     TLS). Platform-agnostic cleanups (qml/ dir, numpy/, translations
     regex, plugin dir prunes, cc3 reference data) run on every OS.
     `sys.platform` dispatch picks the right binary pattern dict so the
     script no-ops cleanly on macOS / Linux without accidentally
     matching the wrong files. No code change to `just build` needed --
     pyinstaller is platform-native and already produces OS-appropriate
     bundles.

  - **[SHIPPED, micro-step] cc3-data drop.** `--collect-data craftgraph`
     in `just build` pulls in the entire `craftgraph/cc3_reference_files/`
     tree (11.3 MB of CC3 mod samples + the original C# source). One
     grep confirmed the only production reference is a docstring in
     `highlighter.py`; nothing loads the tree at runtime. Added a
     dedicated post-build `remove_dir` for the tree.
     **Bundle: 125.1 MB -> 113.8 MB (-11.3 MB, cumulative -545.7 MB
     from baseline).** Verified: bundle launches >5 s, 1563 tests green.

  6. **[SHIPPED] Prune unused Qt plugin subdirs.** Inventoried
     `_internal/PySide6/plugins/` first; PyInstaller had already dropped
     `position/` and `multimedia/` subdirs (followed the excluded
     modules). Remaining waste in `postbuild_trim.py`:
     `plugins/sqldrivers/` (2.46 MB; no Qt SQL usage),
     `plugins/networkinformation/` (0.07 MB),
     `plugins/platforms/{qminimal.dll,qoffscreen.dll}` (test-only
     platform plugins), `plugins/imageformats/{qpdf.dll,qicns.dll}`
     (QtPdf is excluded; .icns is macOS-only). Kept conservative on the
     rest: `tls/` backends (all three; cheap), full `imageformats/`
     for sprite-loader robustness, `platforms/qwindows.dll` +
     `qdirect2d.dll`, `iconengines/` (SVG icons we ship), `styles/`,
     `generic/`, `platforminputcontexts/`.
     **Bundle: 127.9 MB -> 125.1 MB (-2.8 MB, cumulative -534.4 MB from
     baseline).** Verified: bundle launches >5 s, 1563 default tests
     green.

  7. **[SHIPPED] `CRAFTGRAPH_DUMP_MODULES` instrumentation.** Added
     env-gated `sys.modules` dumps to both `gui_entry.py` (writes
     `modules-gui.txt`) and `cli.py` (writes `modules-cli.txt`).
     Pattern: `atexit.register(...)` runs at process exit, OSError on
     write is swallowed so the diagnostic can't crash the GUI. No
     code path runs unless `CRAFTGRAPH_DUMP_MODULES=1` is set, so the
     bundle's release behavior is unchanged. `.gitignore` updated so
     the two dump files don't accidentally land in commits. Verified
     via `CRAFTGRAPH_DUMP_MODULES=1 just run --version` -- the dump
     wrote 489 modules to `modules-cli.txt`.

     **Manual follow-up the user runs (informs Step 8):**

     1. **GUI walkthrough.** Build the bundle, then launch with the
        env set:
        ```
        $env:CRAFTGRAPH_DUMP_MODULES=1
        dist/craftgraph/craftgraph.exe
        ```
        Exercise every feature: open a folder, create + connect nodes,
        edit recipe fields, save, watcher rebuild, open every dialog
        (Settings tabs, Project Issues, About), trigger autocomplete,
        undo/redo, copy/paste, close. The script in the working dir
        produces `modules-gui.txt`.
     2. **Optional dev-vs-prod diff.** Also run with `uv run` under
        `just sync-prod` (runtime-only venv) AND under the full dev
        venv. Diff the two `modules-gui.txt` files. Anything in the
        dev run but absent in the prod run that PyInstaller still
        bundles is exactly the thing to add to `--exclude-module`.
     3. **Cross-check against PyInstaller warnings.** Read
        `build/craftgraph/warn-craftgraph.txt` after each rebuild to
        catch modules PyInstaller could not trace statically;
        anything the runtime needs that lives there has to come back
        in via `--hidden-import`.

  8. **[SHIPPED] Curated `--hidden-import` allow-list.** Replaced
     `--collect-submodules PySide6` in `just build` with explicit
     `--hidden-import` flags for the exact 10 modules the
     `modules-gui.txt` walkthrough proved we load: `QtCore`, `QtGui`,
     `QtWidgets`, `QtOpenGL`, `QtSvg`, `QtSvgWidgets`, `QtNetwork`,
     `QtPrintSupport`, `QtSql`, `QtXml`. Deleted all the now-redundant
     per-module `--exclude-module PySide6.*` flags (`--hidden-import`
     replaces them; PyInstaller no longer pulls anything it isn't
     explicitly told to). Added two extra excludes the dump confirmed:
     `PySide6.QtDBus` and `PySide6.QtOpenGLWidgets` (no Python-side
     import, were still being dragged in as data deps). Postbuild
     trim got a defensive Step 8 group to delete `Qt6DBus*.dll` /
     `Qt6OpenGLWidgets*.dll` if a future PyInstaller drag re-pulls
     them. Verified: bundle launches >8 s cleanly, exit signal fires,
     1563 default tests green.
     **Bundle: 113.8 MB -> 110.8 MB (-3.0 MB, cumulative -548.7 MB
     from baseline).**

  **Future option (deferred):** Switch to Nuitka. Compiles Python to
  native code, sidesteps the Qt.py shim's dynamic-import problem, and
  bundles can be significantly smaller. Higher build complexity and
  slower compile -- not worth tackling now that we're at 110.8 MB.

- [x] **Dual exe: GUI + CLI install option.** Shipped (option 2 from
  the original sketch -- two separate pyinstaller invocations). New
  recipes in `justfile`:
  - `build` -- GUI only (unchanged; `--onedir --windowed`, 110.8 MB)
  - `build-cli` -- CLI as `--onefile --console`, name `craftgraph-cli`.
    Excludes PySide6 / NodeGraphQt / Qt.py shim / shiboken6 / pyvis /
    IPython / psutil / numpy + every dev-only package. `--add-data`
    pulls in just `craftgraph/config.toml` + `craftgraph/data/` (not
    the 11 MB `cc3_reference_files/` tree). **Final CLI bundle:
    13.3 MB** -- far below the 50-100 MB projection.
  - `build-all` -- runs `build` then `build-cli`
  - `installer-windows` -- GUI installer; picks up CLI automatically
    if `dist/craftgraph-cli.exe` exists (Inno Setup
    `skipifsourcedoesntexist` flag)
  - `installer-all-windows` -- builds both then runs Inno Setup

  `craftgraph.iss` gained a `[Components]` section: `gui` is fixed
  (always installed); `cli` is a user-toggleable checkbox on the
  components page (default-on for "Full" install type, can be
  unchecked for "Custom"). The Start Menu shortcut + post-install
  launch button stay GUI-only (no `cli` component tag).

  Smoke-tested CLI subcommands:
  - `craftgraph-cli --version` -- prints `craftgraph, version 0.1.0-alpha.1`
  - `craftgraph-cli check tests/fixtures/mini_mod/` -- "No circular
    dependencies found"
  - `craftgraph-cli check -v ...` -- prints files / recipes / graph
    stats correctly
  - `craftgraph-cli view ...` -- prints friendly install hint:
    "Error: No module named 'pyvis' / Install with:
    pip install craftgraph[visualizer]" (no Python traceback)
  - `craftgraph-cli gui` -- prints friendly install hint:
    "Error: PySide6 or NodeGraphQt is not installed."

  Bug fix as part of this work: the `view` / `watch` commands used to
  raise an uncaught `PyvisNotInstalledError` traceback because
  `_load_generate_html` only imported `craftgraph.visualizer` (which
  succeeds; pyvis is imported lazily inside `generate_html()`).
  Updated to do an explicit `import pyvis` upfront so the missing-dep
  detection lands in the friendly error handler. Default test sweep
  still 1563 / 6 green.

  **Combined install footprint:** GUI 110.8 MB + CLI 13.3 MB =
  ~124 MB. The Inno Setup installer compresses both with lzma2/ultra64
  into a single ~50-60 MB Setup.exe (estimated; final number lands
  once `just installer-all-windows` runs).

- [x] **Update story -- decided.** Two-phase plan:
  - **Now (alpha / 0.x.y): Option A -- Inno Setup native upgrade.** Users
    visit the GitHub Releases page, download the new
    `CraftGraph-Setup-<version>.exe`, run it; Inno Setup matches the
    locked `AppId` and performs an in-place upgrade. Zero in-app code,
    works today, no maintenance.
  - **Later (v1+): Option B -- in-app GitHub release check.** The
    Post-alpha `Version check + update prompt` entry already covers
    this: ping `api.github.com/repos/.../releases/latest`, compare
    against `__version__`, show a non-blocking "newer release
    available" notification with a button that opens the releases page
    in the default browser. ~50 lines of code via `urllib.request`,
    no new deps; the `check_for_updates` setting + `craftgraph/updater.py`
    stub are already wired.

  Evaluated and **rejected for now: WinSparkle.** Windows-only, would
  add ~2 MB to the bundle + an `appcast.xml` hosting + maintenance
  burden, and without code signing it still triggers SmartScreen on
  every auto-downloaded installer -- so the headline benefit (one-click
  in-app update) is mostly lost. Option B gives ~80% of the UX for
  ~10% of the work. Revisit only if alpha gets enough Windows users
  that manual-update friction becomes the dominant complaint.

  **macOS / Linux story:** out of scope until we cut bundles for those
  OSes. Linux apps typically don't ship their own updaters (distro
  package manager / AppImage built-in / Flatpak handle it); macOS has
  Sparkle (the framework WinSparkle was ported from). Pick when those
  bundles exist.

---

## Release readiness (0.1.0-alpha.1)

The dependency hygiene + bundle trim + dual-exe + carousel work is all
shipped; the build chain produces a working GUI + CLI bundle and an
Inno Setup wrapper recipe. What remains is the content / asset / repo
work that has to happen outside the code itself before the release
button gets pressed. Execute in roughly this order.

### Hard blockers (release will not ship cleanly without these)

- [ ] **Create the public GitHub repo.** Replaces the
  `Rovetown/CraftGraph` placeholder URL hard-coded in
  `craftgraph/welcome.py` (`GITHUB_URL`) and `craftgraph/qt_gui.py`
  (`_AboutDialog.GITHUB_URL`). Also where the Setup.exe and CLI exe
  attach to a release tag. Manual step (account / repo creation).

- [ ] **Patch placeholder URLs once the repo URL is final.**
  `craftgraph/welcome.py:GITHUB_URL`,
  `craftgraph/qt_gui.py:_AboutDialog.GITHUB_URL`. `DISCORD_URL` and its
  `_LINKS` entry are gone -- a fake `discord.gg/PLACEHOLDER` invite must
  not ship in a public build; re-add a real invite when a channel exists.
  Optional:
  `craftgraph/welcome.py:CC3_WIKI_URL` (currently points to the
  PrimeSonic CC3 source on GitHub, which is fine as-is, but swap if
  a dedicated wiki ever exists).

- [ ] **App icon (`.ico`).** Source a 256x256 (with multi-resolution
  embedded sizes) icon, drop it at
  `craftgraph/data/icons/craftgraph.ico`. Then:
  - Set `SetupIconFile=craftgraph\data\icons\craftgraph.ico` in
    `craftgraph.iss` so the installer + Add/Remove Programs entry
    get a real icon
  - PyInstaller's `--icon=craftgraph/data/icons/craftgraph.ico` flag
    in `just build` (currently missing) so the bundled exe stops
    using the default bootloader icon
  - `craftgraph/app_dirs.py:bundled_icon_path()` already resolves to
    this path, so the GUI's window/taskbar icon picks it up
    automatically once the file exists

- [ ] **Rewrite `README.md` for the GUI release.** Current README is
  from Phase 1 (CLI-only, source-install via `uv`). Needs to cover:
  - One-paragraph what-it-is + a screenshot of the node editor
  - **Download + install** flow (release page -> Setup.exe -> run)
  - Optional source-install path (`uv sync --extra qt && uv run craftgraph gui`)
  - CLI commands (`check`, `view`, `watch`, `export`) with one-line
    descriptions each
  - Tech-stack block (PySide6 + NodeGraphQt + uv)
  - License + contributing pointers
  - Drop the Phase 1 / Pyvis-CLI emphasis -- those are still
    available but no longer the headline

- [ ] **`CHANGELOG.md` for the alpha.** Either a top-level file
  following Keep-a-Changelog format or just GitHub release notes for
  the tag. Include: dependency hygiene, 83% bundle size reduction,
  dual-exe split, diagnostics toggle, carousel dialogs, log
  retention. The in-app What's New carousel covers the same ground
  for end users; external CHANGELOG.md is for consumers reading the
  repo directly.

- [ ] **Produce a real Setup.exe via `just installer-all-windows`.**
  Recipe exists but has never actually run end-to-end; the first
  invocation may surface latent issues (LZMA compressor timing,
  missing files the Components page expects, etc.). After it
  succeeds, the artifact at
  `dist/CraftGraph-Setup-0.1.0-alpha.1.exe` is what gets uploaded
  to the GitHub release.

### Soft polish (worth doing before publish but not blocking)

- [ ] **Drop the real roadmap image into the What's New carousel.**
  Place at `craftgraph/data/slides/whats-new/v0.1.0a1/roadmap.png`
  and set ``image_path`` on the matching slide in
  `craftgraph/whats_new.py`. `PyInstaller --collect-data craftgraph`
  + the targeted `--add-data` paths already bundle this tree, so no
  build-flag change is needed.

- [ ] **Smoke-test the installer.** After step "Produce a real
  Setup.exe" above, run it on a clean Windows user account (or a
  fresh VM if available) to verify: install path defaults sensibly,
  Start Menu shortcut appears + launches, GUI starts without an
  ImportError, uninstall removes the install dir cleanly, second
  install over the first triggers the in-place upgrade (locked AppId
  match).

- [ ] **Add at least one screenshot to README.** Hero shot of the
  node editor with a real mod loaded -- adoption driver. Even better
  if there is also a smaller cycle-detection screenshot.

- [ ] **Optional: Getting Started carousel real screenshots.** Same
  treatment as the roadmap image -- place PNGs under
  `craftgraph/data/slides/getting-started/`, set ``image_path`` on
  each slide in `craftgraph/getting_started.py`. Placeholder
  gradients are fine if there is not time.

---

## Post-alpha

- [ ] **Interactive guide / tutorial.** A first-run / on-demand walkthrough teaching the
  core workflow (open folder, create + connect nodes, edit fields, save, watcher).
  Two options on the table -- pick later, keep both open:
    - **Carousel screenshots (likely easier).** Reuse `CarouselDialog` from
      `craftgraph/carousel.py` with a dedicated `tutorial.py` slide list. Each slide is
      a captioned screenshot of the next step. Cheapest to author (just add PNGs +
      copy), already supports lightbox / dot-nav / arrow keys, and shares the styling
      with What's New / Getting Started. Tradeoff: passive -- the user reads, then
      tries on their own. Likely the right call for the alpha-era tutorial.
    - **In-app interactive tour (UE4/5-style).** A real coachmark / spotlight system
      that highlights the actual menu / button / node the step refers to (dim
      everything else, draw a rounded cutout + an arrow + a tip bubble), advances on
      user action ("now click File -> Open Folder"). Higher-fidelity, teaches by
      doing, but it is a real feature: needs a step DSL, a `QWidget` overlay that
      tracks target widget geometry across resizes, hit-test passthrough, and per-
      step "did the user actually do the thing" detection wired into the relevant
      signals. Worth the budget only if the carousel version proves insufficient.

- [ ] **Recipe Import / Snippet Paste.** Context menu to import a recipe from known IDs
  (vanilla 498 + mod-compat 120) as a fully-wired node with ingredients pre-linked;
  batch-import related recipes at once as a connected subgraph; user-defined template
  recipes saved to file and offered in the context menu.
- [ ] **Welcome screen polish.** Full-path tooltip on recent entries; visual separation
  of projects vs folders (headers / dividers / grouped sections); fix non-C: drive
  paths wrapping wrong (drive letter splits onto its own line).
- [ ] **Load-path frame jank.** Loading a real mod project janks: `perf_diag` logs a
  burst of `frame_budget_violation` warnings, individual frames 178-294 ms against the
  33 ms budget, during the `load_recipes` window (~1148 ms total, which is NOT a
  regression -- it matches the baseline). Profile the load path as thoroughly as
  possible (the in-app harness or an external profiler, manual work acceptable) to
  attribute the spikes -- `_maybe_build_widgets` bursts, layout solve, or scene
  populate. Leading hypothesis: the `app.processEvents()` paint pump force-builds every
  visible node's widgets during load (~9.4 ms each); the fix may be finer time-slicing
  (yield on an elapsed-time budget, not a node count) or building only viewport-visible
  nodes and letting pan reveal the rest lazily.

- [ ] **Version check + update prompt.** On startup (or on a user-triggered
  "Check for updates" menu action), ping the GitHub Releases API for the
  project's latest tag and compare against `craftgraph.__version__`. If a
  newer version is available, show a non-blocking notification (status bar
  message or modal dialog -- pick later) with a button that opens the
  releases page in the default browser so the user can download the new
  installer. Implementation hooks:
    - `https://api.github.com/repos/<owner>/<repo>/releases/latest` returns
      JSON with a `tag_name` field. Strip a leading `v` if present, parse
      with `packaging.version.Version` for proper semver comparison.
    - Existing `check_for_updates` setting already exists on the window
      (constructor + persisted in settings); the actual check logic is the
      missing piece. Wire it to a `craftgraph/updater.py`-style helper that
      makes the HTTPS request via `urllib.request` (no new dep).
    - The releases URL is `https://github.com/<owner>/<repo>/releases/latest`
      -- same placeholder as the About dialog's GITHUB_URL constant.
    - Failure modes (no internet, rate-limited, repo private): silently
      noop. Don't pop an error dialog at every cold start because Wi-Fi
      was off.
    - Settings panel already has a "Check for updates on launch" checkbox
      (`_check_for_updates`); wiring this end-to-end is part of the task.

- [ ] **Code signing decision** (deferred to release-readiness).
  Unsigned installers trigger Windows SmartScreen ("unrecognized app")
  on first run; some users will bounce. Options:
    a. **Accept it.** Ship a README note explaining "More info -> Run
       anyway". Free, zero friction for us; some users churn out.
    b. **Free open-source signing via SignPath.io** -- this project is
       not currently eligible (SignPath requires the project to be on
       a curated open-source list / OSI-approved structure /
       reproducible builds; revisit when CraftGraph has a public repo
       + a track record).
    c. **Buy a code-signing cert** -- ~$100-300/yr for an OV cert,
       ~$400+/yr for an EV cert that bypasses SmartScreen immediately.
       Not paying for this at the alpha stage.

  Decision today: ship unsigned through 0.x.y. Revisit when CraftGraph
  is closer to a real public release AND either (a) SignPath
  eligibility becomes practical or (b) the project's userbase justifies
  paying for a cert. Self-signed certs do not help -- Windows
  SmartScreen ignores them.

---

## Performance techniques shipped

Optimizations already landed and profiler-verified, kept as a record so the techniques
are not lost. Acceptance target was tier A (~50-recipe real-mod set); tier C (the
894-node worst case) was informational only.

- **Incremental graph rebuild on watcher save** -- model diff instead of full reload
  (~337x: ~5067 ms -> ~15 ms).
- **`setStyleSheet` cache on `_NodeGroupBox`** -- short-circuits NodeGraphQt's ~15.8k
  redundant identical QSS re-applies per load (~3.3 s saved on tier A).
- **Lazy widget allocation** -- defer node widget construction to first paint.
- **Painted-fields architecture** -- painted text plus a shared floating-editor pool
  replace per-node embedded widgets (HWND ~74% down, widget count ~52% down).
- **Cooperative time-slicing during folder load** -- yield to the UI every 50 nodes on
  a 10 ms budget.
- **Bulk node creation under a `QSignalBlocker`.**
- **Hash-based file-change detection** (`st_ino` / `st_mtime_ns` / `st_size`) before
  reparse.
- **Cycle-detection memoization** keyed by `(n_nodes, n_edges)`.
- **Watcher event coalescing** (cancel-and-restart debounce timer).
- **Minimap static-layer `QPixmap` cache** (~13x cut on minimap paint).
- **Tiled `QBrush(QPixmap)` background grid** -- one cached blit replaces thousands of
  per-frame `drawLines` calls.
- **`PortItem.boundingRect` cached on the instance** (~3x per call).
- **`cached_bounding_rect` lookup via `__dict__.get`** (skips the descriptor protocol).
- **Per-node paint instrumentation gated behind an opt-in flag** (zero overhead when
  not recording).
- **`ItemCoordinateCache` on warning-overlay decoration items.**
- **Pre-rendered node-icon `QPixmap` LRU cache.**
- **Settings dialog lazy tab construction** -- each tab builds on first view.
- **Read-through layout cache** plus `msgspec` for the JSON layout cache.
- **Code-edit -> reparse debounce** (400 ms).
- **`PYTHONOPTIMIZE=2` for release builds.**

---

## Deferred / tier-C performance

Out of scope unless profiler data proves the need. Tier C = the 894-node worst-case
set; v1 acceptance was tier A only.

**Parser native-compile ladder:** mypyc, Cython, Rust (PyO3), and C++ (pybind11) all
target the same parser CPU time -- pick at most one rung, escalate to the next only if
the previous proved insufficient, and replace rather than stack.

| Item | Where | Trigger to revisit |
|---|---|---|
| Port-topology surgery without node rebuild | `sync.apply_file_diff` | incremental rebuild's delete-and-re-add dominates watcher cost on tier C, or edge-loss is reported |
| Lazy parse -- background prefetch | tab open hook | tier-C parse cost becomes a real fraction of folder-load wall-clock |
| QThread worker for parser signals | `_open_folder`, watcher | profiler justifies it; NodeGraphQt is main-thread-only, so the post-parse populate cannot move off-thread |
| QThreadPool parallel parse | `parser.py` | tier-C parse cost justifies the pool overhead |
| ProcessPoolExecutor worker pool | parser orchestrator | tier-C parse cost exceeds ~500 ms |
| Python 3.14 free-threaded (no-GIL) build | runtime selection | track only -- gated on PySide6 wheel compatibility |
| mypyc-compile parser + serializer (ladder rung 1) | `parser.py`, `serializer.py` | tier C becomes a real acceptance gate |
| `QOpenGLWidget` viewport | NodeGraphQt viewer | tier-C pan/zoom degrades; risky with `QGraphicsProxyWidget` embedded widgets |
| Serializer on a worker thread | `_on_save_*` actions | a workload appears where serialize wall-clock shows up at all (currently 0.3 ms on tier A) |
| Spatial index (R-tree) for node hit-testing | NodeGraphQt scene | Qt's built-in `BspTreeIndex` proves insufficient at tier C |
| Async / threaded file reads | parser entry | file I/O dominates parse cost at tier C (>50 files) |
| Cython annotation of parser hot loops (ladder rung 2) | `parser.parse_blocks` | escalate from mypyc only if it rejects code or measurable time remains |
| Rust parser via PyO3 + maturin (ladder rung 3) | new crate | parser still >50% of tier-C folder-load wall-clock after rungs 1-2 |
| C++ extension via pybind11 (last resort) | parser hot path | every other parser rung is blocked |
| Diff-based code-edit reapply | parser | full reparse exceeds 50 ms on tier-C typing after debounce + time-slicing |
| Background pre-build of inactive tab graphs | tab manager | tab switches still hitch; NodeGraphQt main-thread constraint applies |
| Replace NetworkX with rustworkx | `graph.py` | graph algorithms become a meaningful fraction of wall-clock, or tier C becomes a gate |
| Level-of-detail: hide widgets when zoomed out | `qt_nodes.py` `paint()` | frame-time log shows pan/zoom over budget at tier A, or tier C becomes a gate |
| Real GPU usage queries (D3D / Vulkan / Metal) | new `gpu_diag.py` | frame-time overlay shows steady >budget frames AND CPU profile rules out widget cost |
| Warm carousel lightbox pixmap on `showEvent` + clear cache pre-`accept` | `carousel.py` `CarouselDialog` | `frame_budget_violation` on first lightbox open (~70 ms) and on whats-new close (~150 ms) becomes a noticeable hitch -- options: `QTimer.singleShot(0, ...)` after show preloads the scaled-for-screen pixmap so the click is free, and clearing `_source_cache` / `_scaled_cache` before `accept()` spreads teardown across a couple of frames |
