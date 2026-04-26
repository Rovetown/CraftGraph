"""Cross-platform file association for ``.craftgraph`` project files.

Registers/unregisters the ``.craftgraph`` extension so that double-clicking
a project file opens CraftGraph.  Each platform uses its native mechanism:

- **Windows:** ``HKCU\\Software\\Classes`` registry keys
- **Linux:** XDG MIME type + ``.desktop`` file
- **macOS:** Build-time ``Info.plist`` (runtime helper prints guidance)

No Qt imports.  All operations target the *current user* only (no admin).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

from craftgraph import app_dirs
from craftgraph.config import get_config

logger = logging.getLogger(__name__)

_APP_CFG = get_config().app
_EXT = _APP_CFG.file_ext
_PROG_ID = _APP_CFG.prog_id
_MIME_TYPE = _APP_CFG.mime_type
_FILE_DESCRIPTION = _APP_CFG.file_description


# -- Public API ----------------------------------------------------------------


def register() -> str:
    """Register the .craftgraph file association for the current user.

    Returns a human-readable summary of what was done.
    """
    if sys.platform == "win32":
        return _register_windows()
    if sys.platform == "linux":
        return _register_linux()
    if sys.platform == "darwin":
        return _register_macos()
    return f"File association is not supported on {sys.platform}."


def unregister() -> str:
    """Remove the .craftgraph file association for the current user.

    Returns a human-readable summary of what was removed.
    """
    if sys.platform == "win32":
        return _unregister_windows()
    if sys.platform == "linux":
        return _unregister_linux()
    if sys.platform == "darwin":
        return "macOS: remove the CFBundleDocumentTypes entry from Info.plist and re-sign the app."
    return f"File association is not supported on {sys.platform}."


def is_registered() -> bool:
    """Check whether the .craftgraph association is currently active."""
    if sys.platform == "win32":
        return _is_registered_windows()
    if sys.platform == "linux":
        return _is_registered_linux()
    # macOS: no reliable runtime check; always return False.
    return False


def executable_path() -> Path:
    """Best-guess path to the CraftGraph executable.

    When running as a PyInstaller bundle, returns the frozen ``.exe``.
    Otherwise returns the Python interpreter (the ``craftgraph`` console
    script is on PATH after ``uv sync``).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    # Dev mode: the `craftgraph` console script is next to python.
    script_name = "craftgraph.exe" if sys.platform == "win32" else "craftgraph"
    candidate = Path(sys.executable).parent / script_name
    if candidate.exists():
        return candidate
    return Path(sys.executable)


# =============================================================================
# Windows implementation
# =============================================================================


def _register_windows() -> str:
    import winreg

    exe = str(executable_path())
    icon = _resolve_icon_windows(exe)
    open_cmd = f'"{exe}" gui "%1"'

    lines: list[str] = []

    # .craftgraph -> CraftGraph.Project
    _winreg_set(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{_EXT}", "", _PROG_ID)
    lines.append(f"Set {_EXT} -> {_PROG_ID}")

    # ProgID keys
    base = rf"Software\Classes\{_PROG_ID}"
    _winreg_set(winreg.HKEY_CURRENT_USER, base, "", _FILE_DESCRIPTION)
    _winreg_set(winreg.HKEY_CURRENT_USER, rf"{base}\DefaultIcon", "", icon)
    _winreg_set(winreg.HKEY_CURRENT_USER, rf"{base}\shell\open\command", "", open_cmd)
    lines.append(f"DefaultIcon = {icon}")
    lines.append(f"Open command = {open_cmd}")

    # Notify Explorer of the change.
    _notify_shell_windows()
    lines.append("Notified Windows shell of change.")

    return "\n".join(lines)


def _unregister_windows() -> str:
    import winreg

    lines: list[str] = []

    for key_path in [
        rf"Software\Classes\{_PROG_ID}\shell\open\command",
        rf"Software\Classes\{_PROG_ID}\shell\open",
        rf"Software\Classes\{_PROG_ID}\shell",
        rf"Software\Classes\{_PROG_ID}\DefaultIcon",
        rf"Software\Classes\{_PROG_ID}",
        rf"Software\Classes\{_EXT}",
    ]:
        if _winreg_delete(winreg.HKEY_CURRENT_USER, key_path):
            lines.append(f"Removed {key_path}")

    _notify_shell_windows()
    lines.append("Notified Windows shell of change.")
    return "\n".join(lines) if lines else "Nothing to remove."


def _is_registered_windows() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{_EXT}"):
            return True
    except FileNotFoundError:
        return False


def _resolve_icon_windows(exe_path: str) -> str:
    """Return the best available icon reference for Windows.

    Prefers the bundled ``.ico`` file if it exists, otherwise falls back
    to the ``.exe`` itself (index 0) so that the embedded PyInstaller
    icon is used.
    """
    ico = app_dirs.bundled_icon_path()
    if ico.exists():
        return str(ico)
    return f"{exe_path},0"


def _winreg_set(root: int, subkey: str, name: str, value: str) -> None:
    import winreg

    with winreg.CreateKeyEx(root, subkey, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def _winreg_delete(root: int, subkey: str) -> bool:
    import winreg

    try:
        winreg.DeleteKey(root, subkey)
    except FileNotFoundError:
        return False
    return True


def _notify_shell_windows() -> None:
    """Tell Explorer to refresh its icon cache.

    Uses ``SHChangeNotify`` via ctypes -- this is the standard way to
    poke the shell after modifying file associations.
    """
    try:
        import ctypes

        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        ctypes.windll.shell32.SHChangeNotify(
            SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None
        )
    except Exception:
        logger.debug("SHChangeNotify failed; Explorer may need a manual refresh.")


# =============================================================================
# Linux implementation
# =============================================================================

_XDG_MIME_XML = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="{_MIME_TYPE}">
    <comment>{_FILE_DESCRIPTION}</comment>
    <glob pattern="*{_EXT}"/>
  </mime-type>
</mime-info>
"""

_DESKTOP_TEMPLATE = """\
[Desktop Entry]
Type=Application
Name=CraftGraph
Comment=Node-based recipe editor for CustomCraft3
Exec={exec_path} gui %f
Icon={icon_path}
Terminal=false
MimeType={mime_type};
Categories=Development;Utility;
"""


def _register_linux() -> str:
    lines: list[str] = []

    # 1. Install MIME type XML
    mime_packages = Path.home() / ".local" / "share" / "mime" / "packages"
    mime_packages.mkdir(parents=True, exist_ok=True)
    mime_file = mime_packages / "craftgraph.xml"
    mime_file.write_text(_XDG_MIME_XML, encoding="utf-8")
    lines.append(f"Wrote MIME definition to {mime_file}")

    # 2. Install .desktop file
    apps_dir = Path.home() / ".local" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = apps_dir / "craftgraph.desktop"
    desktop_file.write_text(
        _DESKTOP_TEMPLATE.format(
            exec_path=executable_path(),
            icon_path=app_dirs.bundled_icon_path(),
            mime_type=_MIME_TYPE,
        ),
        encoding="utf-8",
    )
    lines.append(f"Wrote desktop entry to {desktop_file}")

    # 3. Update MIME and desktop databases
    if shutil.which("update-mime-database"):
        mime_dir = Path.home() / ".local" / "share" / "mime"
        subprocess.run(
            ["update-mime-database", str(mime_dir)],
            check=True,
            capture_output=True,
        )
        lines.append("Updated MIME database.")

    if shutil.which("update-desktop-database"):
        subprocess.run(
            ["update-desktop-database", str(apps_dir)],
            check=True,
            capture_output=True,
        )
        lines.append("Updated desktop database.")

    return "\n".join(lines)


def _unregister_linux() -> str:
    lines: list[str] = []

    mime_file = Path.home() / ".local" / "share" / "mime" / "packages" / "craftgraph.xml"
    if mime_file.exists():
        mime_file.unlink()
        lines.append(f"Removed {mime_file}")

    desktop_file = Path.home() / ".local" / "share" / "applications" / "craftgraph.desktop"
    if desktop_file.exists():
        desktop_file.unlink()
        lines.append(f"Removed {desktop_file}")

    if shutil.which("update-mime-database"):
        mime_dir = Path.home() / ".local" / "share" / "mime"
        subprocess.run(
            ["update-mime-database", str(mime_dir)],
            check=True,
            capture_output=True,
        )
        lines.append("Updated MIME database.")

    if shutil.which("update-desktop-database"):
        apps_dir = Path.home() / ".local" / "share" / "applications"
        subprocess.run(
            ["update-desktop-database", str(apps_dir)],
            check=True,
            capture_output=True,
        )
        lines.append("Updated desktop database.")

    return "\n".join(lines) if lines else "Nothing to remove."


def _is_registered_linux() -> bool:
    desktop_file = Path.home() / ".local" / "share" / "applications" / "craftgraph.desktop"
    return desktop_file.exists()


# =============================================================================
# macOS implementation
# =============================================================================


_PLIST_GUIDANCE = """\
macOS file associations are set at build time in Info.plist.

Add the following to your .app bundle's Info.plist:

  <key>CFBundleDocumentTypes</key>
  <array>
    <dict>
      <key>CFBundleTypeName</key>
      <string>CraftGraph Project</string>
      <key>CFBundleTypeExtensions</key>
      <array>
        <string>craftgraph</string>
      </array>
      <key>CFBundleTypeIconFile</key>
      <string>craftgraph-file</string>
      <key>CFBundleTypeRole</key>
      <string>Editor</string>
      <key>LSHandlerRank</key>
      <string>Owner</string>
    </dict>
  </array>

After building, run:
  /System/Library/Frameworks/CoreServices.framework/Frameworks/\\
  LaunchServices.framework/Support/lsregister -f /path/to/CraftGraph.app
"""


def _register_macos() -> str:
    return _PLIST_GUIDANCE
