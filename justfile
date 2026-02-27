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
# Build & Distribution
# ---------------------------------------------------------------------------

# Bundle into a standalone binary with PyInstaller
build:
    uv run pyinstaller --onefile --name craftgraph --collect-data pyvis craftgraph/cli.py

# Clean build artifacts
clean:
    rm -rf build/ dist/ *.spec __pycache__ .mypy_cache .pytest_cache .ruff_cache
