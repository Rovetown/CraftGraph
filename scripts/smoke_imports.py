"""Production import smoke test.

Walks every module under ``craftgraph/`` and imports it. Run under
``uv run --no-dev --extra qt`` to catch any production code that
accidentally depends on a dev-only package -- the import will raise
``ImportError`` and the script exits non-zero.

Usage::

    uv run --no-dev --extra qt python scripts/smoke_imports.py

Exit codes:
    0 -- every module imported cleanly
    1 -- at least one module failed (errors printed to stderr)

Intentionally avoids importing ``craftgraph.cc3_reference_files`` (it
is a data directory of mod files, not Python). Modules with a ``__main__``
guard or expensive top-level work still get imported but no entry-point
code runs because we use ``importlib.import_module`` rather than executing
them as scripts.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
import traceback


def main() -> int:
    import craftgraph

    failed: list[tuple[str, str]] = []
    imported: list[str] = []

    # Walk the top-level package only; recursion would pull in
    # cc3_reference_files which is a data dir, not Python.
    # Skip ``__main__`` because its module body unconditionally calls
    # ``cli.main()`` -- importing it would invoke the click CLI.
    skip_suffixes = ("__main__",)
    for module_info in pkgutil.iter_modules(craftgraph.__path__, prefix="craftgraph."):
        name = module_info.name
        # cc3_reference_files is a data subpackage of recipe files;
        # skip even if a stray __init__.py exists.
        if "cc3_reference_files" in name:
            continue
        if any(name.endswith(suffix) for suffix in skip_suffixes):
            continue
        try:
            importlib.import_module(name)
        except ImportError as exc:
            failed.append((name, f"{type(exc).__name__}: {exc}"))
        except Exception:
            failed.append((name, traceback.format_exc()))
        else:
            imported.append(name)

    print(f"imported {len(imported)} modules from craftgraph.*")
    if failed:
        print(f"\n{len(failed)} import failure(s):", file=sys.stderr)
        for name, err in failed:
            print(f"  {name}: {err}", file=sys.stderr)
        return 1
    print("smoke ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
