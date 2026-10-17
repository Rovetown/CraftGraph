# CraftGraph -- project commands
# Run any command with: just <recipe>
# List all commands with: just --list
#
# Platform suffix convention:
#   <name>             -- portable; works on Windows, macOS, Linux
#   <name>-windows     -- needs PowerShell syntax (Inno Setup discovery, $env:VAR, etc.)
#   <name>-linux       -- bash/POSIX equivalent (also works on macOS)
#
# Shell selection: on Windows we keep PowerShell as the default because that
# is the standard CraftGraph dev shell and several portable recipes assume
# its quoting rules; on Linux/macOS just uses sh. Recipes that need a
# different shell on a given platform declare it locally via a shebang.

set windows-shell := ["powershell.exe", "-c"]
set dotenv-load := false

# Default recipe: show available commands
default:
    @just --list

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

# Run the craftgraph CLI (shows help when called with no args)
run *ARGS:
    uv run craftgraph {{ if ARGS == "" { "--help" } else { ARGS } }}

# Check recipes for circular dependencies
check PATH:
    uv run craftgraph check {{PATH}}

# Visualize recipe dependency graph (requires the visualizer extra)
view PATH:
    uv run --extra visualizer craftgraph view {{PATH}}

# Watch a recipe directory for changes (requires the visualizer extra)
watch PATH:
    uv run --extra visualizer craftgraph watch {{PATH}}

# Export parsed recipes back to EasyMarkup text
export PATH *ARGS:
    uv run craftgraph export {{PATH}} {{ARGS}}

# Open the graphical recipe editor (PySide6 + NodeGraphQt)
gui *PATH:
    uv run --extra qt craftgraph gui {{ if PATH == "" { "" } else { PATH } }}

# Tracemalloc is started AFTER imports settle, so startup is not slowed
# by the pyvis/IPython import chain.

# Open the graphical recipe editor with tracemalloc enabled
gui-trace *PATH:
    uv run --extra qt craftgraph gui --trace-mem {{ if PATH == "" { "" } else { PATH } }}

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

# Install/sync all dependencies (runtime + dev + qt extra). Standard dev setup.
sync:
    uv sync --extra qt

# This is what end users get from `pip install craftgraph[qt]`. Useful before
# a release to catch dev-only imports that leaked into production code paths.

# Sync production install (runtime + qt extra, no dev tools)
sync-prod:
    uv sync --no-dev --extra qt

# Add a runtime dependency
add *PACKAGES:
    uv add {{PACKAGES}}

# Add a dev dependency
add-dev *PACKAGES:
    uv add --dev {{PACKAGES}}

# Run the default test sweep (excludes @pytest.mark.slow). Use `just test-all` for the full suite.
test *ARGS:
    uv run --extra qt pytest -m "not slow" {{ARGS}}

# Verbose default test sweep (still excludes @pytest.mark.slow)
test-v *ARGS:
    uv run --extra qt pytest -v -m "not slow" {{ARGS}}

# Run the entire suite including @pytest.mark.slow tests
test-all *ARGS:
    uv run --extra qt pytest {{ARGS}}

# Run only @pytest.mark.slow tests (test_qt_gui + test_perf_stress + test_hwnd_stress + test_incremental_rebuild_parity)
test-slow *ARGS:
    uv run --extra qt pytest -m slow {{ARGS}}

# Run a specific test file (no marker filter; explicit file wins)
test-file FILE *ARGS:
    uv run --extra qt pytest {{FILE}} {{ARGS}}

# Run the default sweep with coverage; print a per-file summary with missing-line ranges.
cov *ARGS:
    uv run --extra qt pytest -m "not slow" --cov=craftgraph --cov-report=term-missing {{ARGS}}

# Same as `just cov` but writes an HTML report to htmlcov/ and opens it.
cov-html *ARGS:
    uv run --extra qt pytest -m "not slow" --cov=craftgraph --cov-report=html {{ARGS}}
    @echo "Report: htmlcov/index.html"

# Full-suite coverage (including @pytest.mark.slow). Closer to the true number.
cov-all *ARGS:
    uv run --extra qt pytest --cov=craftgraph --cov-report=term-missing {{ARGS}}

# Full qt sweep with PYTHONUNBUFFERED + -s -- Windows variant (PowerShell env syntax).
test-qt-windows *ARGS:
    $env:PYTHONUNBUFFERED='1'; uv run --extra qt pytest tests/test_qt_gui.py tests/test_qt_nodes.py -s --tb=line {{ARGS}}

# Full qt sweep with PYTHONUNBUFFERED + -s -- Linux / macOS variant (POSIX env syntax).
test-qt-linux *ARGS:
    PYTHONUNBUFFERED=1 uv run --extra qt pytest tests/test_qt_gui.py tests/test_qt_nodes.py -s --tb=line {{ARGS}}

# Run the pytest-benchmark suite (slow-tagged). Pass --benchmark-only to skip non-benchmark tests, --benchmark-compare to diff against a saved baseline.
bench *ARGS:
    uv run pytest tests/test_benchmarks.py --benchmark-only {{ARGS}}

# Save current benchmark results as a named baseline (e.g. `just bench-save before`).
bench-save NAME:
    uv run pytest tests/test_benchmarks.py --benchmark-only --benchmark-save={{NAME}}

# ---------------------------------------------------------------------------
# Code Quality
# ---------------------------------------------------------------------------

# Lint with ruff (check only)
lint:
    uv run ruff check .

# Lint and auto-fix
lint-fix:
    uv run ruff check --fix .

# Format with ruff
fmt:
    uv run ruff format .

# Check formatting without changing files
fmt-check:
    uv run ruff format --check .

# Type-check with mypy
typecheck:
    uv run mypy craftgraph/

# Run all quality checks (lint + format check + typecheck)
qa: lint fmt-check typecheck

# ---------------------------------------------------------------------------
# File Association
# ---------------------------------------------------------------------------

# Register .craftgraph file association for the current user
register:
    uv run craftgraph register

# Remove .craftgraph file association
unregister:
    uv run craftgraph unregister

# ---------------------------------------------------------------------------
# Build & Distribution
# ---------------------------------------------------------------------------

# Cross-platform: works on Windows, macOS, Linux. PyInstaller produces a
# platform-native binary.
#
# Flag rationale:
#   --onedir / --windowed     ship a GUI app, no console flash, no per-launch
#                             extraction cost (vs --onefile)
#   --collect-submodules PySide6
#                             NodeGraphQt's Qt.py shim dynamically imports
#                             PySide6 submodules at runtime; PyInstaller's
#                             static analysis can't trace those.
#   --exclude-module <name>   keep optional / dev-only packages out of the
#                             bundle. rich is safe because log_setup falls
#                             back to stdlib StreamHandler; pyvis + IPython
#                             are only used by the CLI view/watch commands
#                             the bundled GUI does not expose.
#   --optimize 2              strip asserts + docstrings from bytecode.

# Bundle the GUI into a portable folder with PyInstaller
build:
    uv run pyinstaller --onedir --windowed --name craftgraph --collect-data craftgraph --hidden-import PySide6.QtCore --hidden-import PySide6.QtGui --hidden-import PySide6.QtWidgets --hidden-import PySide6.QtOpenGL --hidden-import PySide6.QtSvg --hidden-import PySide6.QtSvgWidgets --hidden-import PySide6.QtNetwork --hidden-import PySide6.QtPrintSupport --hidden-import PySide6.QtSql --hidden-import PySide6.QtXml --exclude-module pyvis --exclude-module IPython --exclude-module rich --exclude-module hypothesis --exclude-module mypy --exclude-module ruff --exclude-module pytest --exclude-module pytest_sugar --exclude-module pytest_clarity --exclude-module pytest_qt --exclude-module pytest_benchmark --exclude-module pytest_cov --exclude-module PyInstaller --exclude-module PySide6.QtDBus --exclude-module PySide6.QtOpenGLWidgets --exclude-module numpy --exclude-module scipy --optimize 2 --noconfirm craftgraph/gui_entry.py
    uv run python scripts/postbuild_trim.py

# ``--onefile`` is the right tradeoff: CLI invocations are typically
# one-shot (``craftgraph check ./recipes/``) and a single file is the
# convenient distribution unit; the ~2.8 s bootloader extraction cost
# only matters for tight loops. Excludes everything Qt + dev-only +
# pyvis/IPython (HTML viz needs ``pip install craftgraph[visualizer]``
# from source). Console-mode so stdout/stderr work normally.

# Bundle the CLI as a single self-extracting exe
build-cli:
    uv run pyinstaller --onefile --console --name craftgraph-cli --add-data "craftgraph/config.toml:craftgraph" --add-data "craftgraph/data:craftgraph/data" --exclude-module PySide6 --exclude-module NodeGraphQt --exclude-module Qt --exclude-module shiboken6 --exclude-module pyvis --exclude-module IPython --exclude-module rich --exclude-module hypothesis --exclude-module mypy --exclude-module ruff --exclude-module pytest --exclude-module pytest_sugar --exclude-module pytest_clarity --exclude-module pytest_qt --exclude-module pytest_benchmark --exclude-module pytest_cov --exclude-module PyInstaller --exclude-module psutil --exclude-module numpy --exclude-module scipy --optimize 2 --noconfirm craftgraph/cli.py

# GUI first because the installer expects ``dist/craftgraph/`` as the
# base layout; CLI's ``craftgraph-cli.exe`` lands directly in ``dist/``.

# Build both GUI + CLI bundles in sequence
build-all: build build-cli

# Compare dev vs release wall-clock on the mini fixture. Pass --build to auto-build first.
compare-release *ARGS:
    uv run python scripts/compare_dev_release.py {{ARGS}}

# Show the CarouselDialog with placeholder slides for visual review.
# FLAVOR = whats-new (default) | getting-started.
preview-carousel *FLAVOR:
    uv run --extra qt python scripts/preview_carousel.py {{FLAVOR}}

# Tries PATH first, then the default Inno Setup 6 install location.
# Restart the shell after installing Inno Setup so PATH updates land.
# Single-line PowerShell so the recipe runs in one shell process and
# ``$iscc`` carries across the chained statements.

# The CLI bundle is optional; if ``dist/craftgraph-cli.exe`` exists Inno
# Setup picks it up automatically (skipifsourcedoesntexist in the
# Components section). Run ``just build-all`` first to ship both.

# Wrap the GUI bundle into an Inno Setup installer (Windows only)
installer-windows: build
    $iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source; if (-not $iscc) { $iscc = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' }; if (-not (Test-Path $iscc)) { Write-Error 'ISCC.exe not found. Install Inno Setup 6 from https://jrsoftware.org/isinfo.php'; exit 1 }; & $iscc craftgraph.iss

# The Components page of the installer offers the CLI as a
# user-toggleable option.

# Build GUI + CLI then wrap both into an Inno Setup installer (Windows)
installer-all-windows: build-all
    $iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source; if (-not $iscc) { $iscc = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' }; if (-not (Test-Path $iscc)) { Write-Error 'ISCC.exe not found. Install Inno Setup 6 from https://jrsoftware.org/isinfo.php'; exit 1 }; & $iscc craftgraph.iss

# Single-line so it stays in one PS process (see installer-windows note).

# Clean build + cache artifacts -- Windows (PowerShell)
# -ErrorAction SilentlyContinue on every Remove-Item so a still-running
# craftgraph.exe locking dist/ doesn't bomb the whole recipe; close the
# app and re-run clean-windows to finish the job.
clean-windows:
    foreach ($p in 'build','dist','.mypy_cache','.pytest_cache','.ruff_cache','.hypothesis','.benchmarks','htmlcov','.coverage') { if (Test-Path $p) { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $p } }; Get-ChildItem -Path . -Recurse -Filter __pycache__ -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue; Get-ChildItem -Path . -Filter '*.spec' -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue

# Single-line so the recipe survives just's per-line shell invocation on
# distros where bash is not the default ``sh``.

# Clean build + cache artifacts -- Linux / macOS (POSIX shell)
clean-linux:
    rm -rf build dist .mypy_cache .pytest_cache .ruff_cache .hypothesis .benchmarks htmlcov .coverage && find . -type d -name __pycache__ -prune -exec rm -rf {} + && find . -type f -name '*.spec' -delete

# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------

# Run perf stress tests (Tier A asserts; B smoke; C skipped)
perf-test *ARGS:
    uv run --extra qt pytest tests/test_perf_stress.py -v {{ARGS}}

# Run --no-dev smoke: import every craftgraph.* module + parse a Tier A
# workload with only runtime + [qt] extra installed. Catches production
# code paths that accidentally depend on a dev-only package (the import
# raises ImportError when the dev install is absent).
smoke-no-dev:
    uv run --no-dev --extra qt python scripts/smoke_imports.py
    uv run --no-dev --extra qt python -c "from pathlib import Path; from craftgraph.parser import parse_directory; parse_directory(Path('craftgraph/cc3_reference_files/real-mod-examples')); print('parse smoke ok')"

# Capture pre/post Phase-1 baseline numbers (no output capture)
baseline-perf:
    uv run --extra qt pytest tests/test_perf_stress.py -v --capture=no
