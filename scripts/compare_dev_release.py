"""Compare dev-mode CLI vs the PyInstaller release binary on identical scenarios.

For each scenario we time N invocations of:

    Dev:     uv run craftgraph <args>
    Release: dist/craftgraph(.exe) <args>

and print a side-by-side median wall-clock table. Output is informational --
no assertion, no exit code based on relative performance. The intent is to
make regressions / improvements visible per release build.

Run via ``just compare-release`` (auto-builds if the binary is missing) or
directly::

    uv run python scripts/compare_dev_release.py
    uv run python scripts/compare_dev_release.py --build  # rebuild first
    uv run python scripts/compare_dev_release.py --runs 10
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from statistics import median

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "mini_mod"
DIST = REPO_ROOT / "dist"
# --onedir layout: dist/craftgraph/craftgraph(.exe) lives alongside _internal/.
BINARY = DIST / "craftgraph" / ("craftgraph.exe" if sys.platform == "win32" else "craftgraph")


# (label, args-after-binary). Side-effect-free; no GUI, no browser, no watch.
SCENARIOS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("check", ("check", str(FIXTURE))),
    ("check -v", ("check", "-v", str(FIXTURE))),
    ("export", ("export", str(FIXTURE), "-o", str(REPO_ROOT / "dist" / "_compare_export"))),
)


def _run(cmd: Sequence[str]) -> float:
    """Time a single subprocess invocation in milliseconds (wall-clock)."""
    start = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    if result.returncode != 0:
        sys.stderr.write(f"\n[fail] {' '.join(cmd)} -> exit {result.returncode}\n")
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    return elapsed_ms


def _ensure_binary(build: bool) -> None:
    if BINARY.exists():
        return
    if not build:
        sys.stderr.write(
            f"Release binary not found at {BINARY}.\n"
            f"Build first with `just build` or pass --build to this script.\n"
        )
        raise SystemExit(2)
    sys.stderr.write(f"Building release binary at {BINARY}...\n")
    build_cmd = [
        "uv", "run", "pyinstaller", "--onedir", "--name", "craftgraph",
        "--collect-data", "pyvis", "--collect-data", "craftgraph",
        "--optimize", "2", "--noconfirm",
        str(REPO_ROOT / "craftgraph" / "cli.py"),
    ]
    subprocess.run(build_cmd, cwd=REPO_ROOT, check=True)
    if not BINARY.exists():
        sys.stderr.write("Build completed but binary still missing.\n")
        raise SystemExit(2)


def _print_table(rows: list[tuple[str, float, float]]) -> None:
    name_width = max(len(r[0]) for r in rows)
    name_width = max(name_width, len("scenario"))
    header = (
        f"{'scenario':<{name_width}}  {'dev (ms)':>10}  "
        f"{'release (ms)':>14}  {'ratio':>8}  verdict"
    )
    print(header)
    print("-" * len(header))
    # Thresholds calibrated for --onedir: no per-invocation bootloader, so
    # release should track dev within measurement noise. Anything past ~1.5x
    # is worth investigating (real work-side regression).
    for label, dev_ms, rel_ms in rows:
        ratio = rel_ms / dev_ms if dev_ms > 0 else float("inf")
        if ratio < 1.2:
            verdict = "parity"
        elif ratio < 1.5:
            verdict = "marginal -- inspect if persistent"
        else:
            verdict = "release slower -- investigate"
        print(
            f"{label:<{name_width}}  {dev_ms:>10.1f}  {rel_ms:>14.1f}  "
            f"{ratio:>7.2f}x  {verdict}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--build", action="store_true", help="Build the binary if missing.")
    parser.add_argument(
        "--runs", type=int, default=5, help="Invocations per scenario (default 5).",
    )
    args = parser.parse_args(argv)

    if not FIXTURE.is_dir():
        sys.stderr.write(f"Mini fixture missing: {FIXTURE}\n")
        return 2

    _ensure_binary(build=args.build)

    uv = shutil.which("uv")
    if uv is None:
        sys.stderr.write("uv not on PATH; install uv first.\n")
        return 2

    print(f"Comparing dev vs release on {FIXTURE.relative_to(REPO_ROOT)}")
    print(f"Runs per scenario: {args.runs}  (taking median)\n")

    rows: list[tuple[str, float, float]] = []
    for label, scenario_args in SCENARIOS:
        dev_cmd = [uv, "run", "craftgraph", *scenario_args]
        rel_cmd = [str(BINARY), *scenario_args]

        dev_ms = median(_run(dev_cmd) for _ in range(args.runs))
        rel_ms = median(_run(rel_cmd) for _ in range(args.runs))
        rows.append((label, dev_ms, rel_ms))

    _print_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
