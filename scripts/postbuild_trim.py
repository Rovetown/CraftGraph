"""Post-build bundle trimming.

PyInstaller's ``--exclude-module`` only removes Python modules from the
graph; binaries collected by ``--collect-submodules PySide6`` (the Qt
DLLs themselves) ignore those flags. This script runs after
``pyinstaller`` to delete the specific binary files and data dirs that
the GUI bundle does not need.

OS-aware:

- **Platform-agnostic cleanups** (qml/ data dir, numpy dir, translations
  regex, craftgraph cc3 reference data, plugin dir removals) run on
  every OS because the file structure of those targets is the same.
- **Binary-name cleanups** (Qt DLL / .so / .dylib globs) are split per
  platform because the filenames differ (``Qt6Foo.dll`` on Windows,
  ``libQt6Foo.so.6`` on Linux, frameworks on macOS).

Right now only the Windows binary patterns are populated. The macOS /
Linux branches are stubs with TODOs so the script no-ops cleanly on
those platforms instead of accidentally matching the wrong files.

Each cleanup group is gated on whether the target exists, so running
the script before a build is a no-op rather than an error.

Usage::

    python scripts/postbuild_trim.py

Run automatically from ``just build`` after pyinstaller completes.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

# Translation files we keep: ``<module>_en.qm`` and any English regional
# variants like ``<module>_en_US.qm``. Every other language gets dropped;
# Qt falls back to the source strings (English) when no .qm matches the
# user's locale, so non-English locales still get a working UI.
_KEEP_TRANSLATION_RE = re.compile(r"_en(_[A-Z]{2})?\.qm$")

BUNDLE_ROOT = Path("dist/craftgraph/_internal")


def remove_files(directory: Path, patterns: list[str]) -> tuple[int, int]:
    """Delete files in *directory* matching any of *patterns* (glob).

    Returns ``(count, bytes_removed)`` for the report at the end. Missing
    directories or zero matches are not errors.
    """
    if not directory.is_dir():
        return 0, 0
    count = 0
    total = 0
    for pat in patterns:
        for match in directory.glob(pat):
            if match.is_file():
                size = match.stat().st_size
                match.unlink()
                count += 1
                total += size
    return count, total


def remove_dir(path: Path) -> int:
    """Delete *path* recursively if present; return bytes removed."""
    if not path.is_dir():
        return 0
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    shutil.rmtree(path)
    return total


# ---------------------------------------------------------------------------
# Platform-specific binary patterns
# ---------------------------------------------------------------------------


def _windows_binary_patterns() -> dict[str, list[str]]:
    """Return Windows-specific binary cleanup patterns, grouped by step.

    All globs target ``PySide6/`` directly. Filenames follow the Windows
    convention: ``Qt6Foo.dll`` for shared libs, ``QtFoo.pyd`` for the
    PySide6 Python wrappers.
    """
    return {
        "WebEngine + WebChannel binaries (Step 1)": [
            "Qt6WebEngine*.dll",
            "Qt6WebChannel*.dll",
            "QtWebEngine*.pyd",
            "QtWebChannel*.pyd",
        ],
        "Qml / Quick / Qt3D binaries (Step 2)": [
            "Qt6Qml*.dll",
            "QtQml*.pyd",
            "Qt6Quick*.dll",
            "QtQuick*.pyd",
            "Qt63D*.dll",
            "Qt3D*.pyd",
            "Qt6ShaderTools.dll",
            "Qt6Graphs*.dll",
        ],
        "no-Python-side Qt binaries (Step 8)": [
            # PyInstaller may still drag these in via direct-dep tracking
            # of QtCore/QtGui even though no Python module ever imports
            # the wrapper. Confirmed unused by the modules-gui.txt dump.
            "Qt6DBus*.dll",
            "QtDBus*.pyd",
            "Qt6OpenGLWidgets*.dll",
            "QtOpenGLWidgets*.pyd",
        ],
        "leftover unused Qt module binaries (Step 4)": [
            "Qt6Multimedia*.dll",
            "QtMultimedia*.pyd",
            "Qt6SpatialAudio*.dll",
            "QtSpatialAudio*.pyd",
            "Qt6Designer*.dll",
            "QtDesigner*.pyd",
            "Qt6UiTools*.dll",
            "QtUiTools*.pyd",
            "Qt6Help*.dll",
            "QtHelp*.pyd",
            "Qt6Pdf*.dll",
            "QtPdf*.pyd",
            "Qt6Charts*.dll",
            "QtCharts*.pyd",
            "Qt6DataVisualization*.dll",
            "QtDataVisualization*.pyd",
            "Qt6Location*.dll",
            "QtLocation*.pyd",
            "Qt6Positioning*.dll",
            "QtPositioning*.pyd",
            "Qt6RemoteObjects*.dll",
            "QtRemoteObjects*.pyd",
            "Qt6Bluetooth*.dll",
            "QtBluetooth*.pyd",
            "Qt6Nfc*.dll",
            "QtNfc*.pyd",
            "Qt6Scxml*.dll",
            "QtScxml*.pyd",
            "Qt6Sensors*.dll",
            "QtSensors*.pyd",
            "Qt6Serial*.dll",
            "QtSerial*.pyd",
            "Qt6TextToSpeech*.dll",
            "QtTextToSpeech*.pyd",
            "Qt6StateMachine*.dll",
            "QtStateMachine*.pyd",
            "Qt6NetworkAuth*.dll",
            "QtNetworkAuth*.pyd",
            "Qt6HttpServer*.dll",
            "QtHttpServer*.pyd",
            "Qt6Test*.dll",
            "QtTest*.pyd",
            "Qt6VirtualKeyboard*.dll",
            "QtVirtualKeyboard*.pyd",
            "Qt6WebSockets*.dll",
            "QtWebSockets*.pyd",
            "Qt6WebView*.dll",
            "QtWebView*.pyd",
            "Qt6CanvasPainter*.dll",
            "QtCanvasPainter*.pyd",
            # ffmpeg ships for QtMultimedia codec support.
            "avcodec-*.dll",
            "avformat-*.dll",
            "avutil-*.dll",
            "swresample-*.dll",
            "swscale-*.dll",
        ],
    }


def _linux_binary_patterns() -> dict[str, list[str]]:
    """Return Linux-specific binary cleanup patterns, grouped by step.

    TODO: Populate when a Linux build is needed. Linux PySide6 ships
    ``libQt6Foo.so.6.x.y`` style shared objects (note the ``lib`` prefix
    and the ``.so.<major>`` suffix; the version number may be on the
    filename). Plugin TLS backends differ too: Linux normally ships
    OpenSSL only, no Schannel / SecureTransport, so the TLS-backend
    pruning would need a different list there.

    Returns an empty dict for now so the script no-ops on Linux without
    matching anything by accident.
    """
    return {}


def _darwin_binary_patterns() -> dict[str, list[str]]:
    """Return macOS-specific binary cleanup patterns, grouped by step.

    TODO: Populate when a macOS build is needed. PySide6 on macOS ships
    Qt as ``QtFoo.framework/`` bundle directories, not as bare dylibs --
    each framework needs a ``remove_dir`` call rather than a file glob.
    Keep the ``qcocoa`` platform plugin (analogue of ``qwindows.dll``);
    drop ``qsecuretransportbackend`` is the native macOS TLS backend so
    it stays, ``qschannelbackend`` would not even be shipped.

    Returns an empty dict for now.
    """
    return {}


def _binary_patterns_for_platform() -> dict[str, list[str]]:
    """Pick the right pattern dict for the current ``sys.platform``."""
    if sys.platform == "win32":
        return _windows_binary_patterns()
    if sys.platform == "darwin":
        return _darwin_binary_patterns()
    if sys.platform.startswith("linux"):
        return _linux_binary_patterns()
    return {}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    if not BUNDLE_ROOT.is_dir():
        print(f"no bundle at {BUNDLE_ROOT}; nothing to trim", file=sys.stderr)
        return 0

    pyside_root = BUNDLE_ROOT / "PySide6"
    report: list[tuple[str, int, int]] = []

    # ----- Platform-specific binary cleanups (Steps 1, 2, 4) ----------
    binary_patterns = _binary_patterns_for_platform()
    for label, patterns in binary_patterns.items():
        n, b = remove_files(pyside_root, patterns)
        report.append((label, n, b))

    # ----- Platform-agnostic cleanups ---------------------------------
    # These run on every OS because the target paths exist with the same
    # structure regardless of platform: PySide6/qml/ data tree, numpy/
    # transitive bundle, .qm translation files, craftgraph package data,
    # plugins/ subdirs.

    # ``PySide6/qml/`` (Step 2) -- QML runtime tree, ~25 MB on Windows.
    qml_dir_bytes = remove_dir(pyside_root / "qml")
    if qml_dir_bytes:
        report.append(("PySide6/qml/ data tree (Step 2)", 1, qml_dir_bytes))

    # ``plugins/<sub>/`` (Step 6) -- whole-dir prunes.
    plugins_root = pyside_root / "plugins"
    for sub in ("sqldrivers", "networkinformation"):
        byts = remove_dir(plugins_root / sub)
        if byts:
            report.append((f"plugins/{sub}/ dir (Step 6)", 1, byts))

    # ``plugins/<sub>/<file>`` (Step 6) -- specific files inside kept dirs.
    plugin_files: list[tuple[str, list[str]]] = [
        ("platforms", ["qminimal.dll", "qoffscreen.dll"]),
        ("imageformats", ["qpdf.dll", "qicns.dll"]),
    ]
    plug_n = 0
    plug_b = 0
    for sub, names in plugin_files:
        sub_dir = plugins_root / sub
        if not sub_dir.is_dir():
            continue
        for name in names:
            target = sub_dir / name
            if target.is_file():
                plug_b += target.stat().st_size
                target.unlink()
                plug_n += 1
    if plug_n:
        report.append(("plugins/<sub>/* files (Step 6)", plug_n, plug_b))

    # ``numpy/`` + ``numpy.libs/`` (Step 5). ``--exclude-module numpy``
    # in just build keeps PyInstaller from collecting it, but this
    # defensive cleanup catches builds where some Python-level reference
    # still pulled it into the data-collection phase.
    for nm in ("numpy", "numpy.libs"):
        d = BUNDLE_ROOT / nm
        if d.is_dir():
            byts = remove_dir(d)
            if byts:
                report.append((f"{nm}/ data tree (Step 5)", 1, byts))

    # ``craftgraph/cc3_reference_files/`` (cc3-data micro-step) -- the
    # 11 MB tree of reference mod files used for parser tests + dev
    # exploration. Only a single docstring in production code mentions
    # the path; nothing loads it at runtime. ``--collect-data craftgraph``
    # in just build pulls it in unconditionally, so we strip it here.
    cc3_dir = BUNDLE_ROOT / "craftgraph" / "cc3_reference_files"
    cc3_bytes = remove_dir(cc3_dir)
    if cc3_bytes:
        report.append(
            ("craftgraph/cc3_reference_files/ (data micro-step)", 1, cc3_bytes),
        )

    # ``PySide6/translations/`` (Step 3) -- keep only ``_en.qm`` variants.
    translations_dir = pyside_root / "translations"
    tr_count = 0
    tr_bytes = 0
    if translations_dir.is_dir():
        for qm in translations_dir.glob("*.qm"):
            if _KEEP_TRANSLATION_RE.search(qm.name):
                continue
            tr_bytes += qm.stat().st_size
            qm.unlink()
            tr_count += 1
    report.append(("non-English translations (Step 3)", tr_count, tr_bytes))

    # Print report so build logs show what came out.
    total_files = 0
    total_bytes = 0
    for label, files, byts in report:
        total_files += files
        total_bytes += byts
        print(f"  {label}: -{files} files, -{byts / 1024 / 1024:.1f} MB")
    print(f"post-build trim: -{total_files} files, -{total_bytes / 1024 / 1024:.1f} MB total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
