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

# Run the full test suite
test *ARGS:
    uv run pytest {{ARGS}}

# Run tests with verbose output
test-v *ARGS:
    uv run pytest -v {{ARGS}}

# Run a specific test file
test-file FILE *ARGS:
    uv run pytest {{FILE}} {{ARGS}}

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

# Bundle into a standalone binary with PyInstaller
build:
    uv run pyinstaller --onefile --name craftgraph --collect-data pyvis craftgraph/cli.py

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
