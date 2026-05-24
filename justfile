# CraftGraph -- project commands
# Run any command with: just <recipe>
# List all commands with: just --list

# use PowerShell instead of sh:
set shell := ["powershell.exe", "-c"]
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

# Visualize recipe dependency graph
view PATH:
    uv run craftgraph view {{PATH}}

# Watch a recipe directory for changes
watch PATH:
    uv run craftgraph watch {{PATH}}

# Export parsed recipes back to EasyMarkup text
export PATH *ARGS:
    uv run craftgraph export {{PATH}} {{ARGS}}

# Open the graphical recipe editor (PySide6 + NodeGraphQt)
gui *PATH:
    uv run --extra qt craftgraph gui {{ if PATH == "" { "" } else { PATH } }}

# Same as `just gui` but starts tracemalloc just before the GUI launches
# so Help > Dump Memory Snapshot has real allocation data. Tracemalloc
# is started AFTER imports settle, so startup is not slowed by the
# pyvis/IPython import chain.
gui-trace *PATH:
    uv run --extra qt craftgraph gui --trace-mem {{ if PATH == "" { "" } else { PATH } }}

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

# Install/sync all dependencies from pyproject.toml
sync:
    uv sync

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

# Run the full qt sweep with PYTHONUNBUFFERED + -s (works around pipe-buffering stalls)
test-qt *ARGS:
    PYTHONUNBUFFERED=1 uv run --extra qt pytest tests/test_qt_gui.py tests/test_qt_nodes.py -s --tb=line {{ARGS}}

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

# Bundle into a standalone binary with PyInstaller (--optimize 2 strips asserts/docstrings)
build:
    uv run pyinstaller --onefile --name craftgraph --collect-data pyvis --collect-data craftgraph --optimize 2 craftgraph/cli.py

# Clean build artifacts
clean:
    rm -rf build/ dist/ *.spec __pycache__ .mypy_cache .pytest_cache .ruff_cache

# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------

# Run perf stress tests (Tier A asserts; B smoke; C skipped)
perf-test *ARGS:
    uv run --extra qt pytest tests/test_perf_stress.py -v {{ARGS}}

# Run --no-dev smoke: parse Tier A workload with runtime deps only
smoke-no-dev:
    uv run --no-dev --extra qt python -c "from pathlib import Path; from craftgraph.parser import parse_directory; parse_directory(Path('craftgraph/cc3_reference_files/real-mod-examples')); print('smoke ok')"

# Capture pre/post Phase-1 baseline numbers (no output capture)
baseline-perf:
    uv run --extra qt pytest tests/test_perf_stress.py -v --capture=no
