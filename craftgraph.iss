; CraftGraph -- Inno Setup script
;
; Wraps the PyInstaller --onedir output at dist/craftgraph/ (GUI) plus the
; optional dist/craftgraph-cli.exe (CLI --onefile) into a single
; self-contained installer at dist/CraftGraph-Setup-<version>.exe.
;
; Build chain:
;   1. `just build`       -> dist/craftgraph/{craftgraph.exe, _internal/}
;   2. `just build-cli`   -> dist/craftgraph-cli.exe (optional)
;   3. `just installer`   -> dist/CraftGraph-Setup-<version>.exe
;
; The installer shows a components page: the GUI is required (fixed
; flag), the CLI is an optional checkbox.
;
; Requires Inno Setup 6 (https://jrsoftware.org/isinfo.php). The ISCC.exe
; compiler must be on PATH, or invoke this script with its full path.
;
; AppId UUID is LOCKED IN. Do NOT regenerate -- Windows uses it to detect
; upgrade installs vs side-by-side installs. Changing it would orphan the
; existing install and ship a brand-new entry in Add/Remove Programs.

#define AppName "CraftGraph"
; Display-string version (semver pre-release). Mirrors pyproject.toml's
; ``version =`` and craftgraph/__init__.py's ``__version__``.
#define AppVersion "0.1.0-alpha.1"
; Binary metadata version baked into the EXE / installer resources.
; Must be ``major.minor.build.revision`` integers (Inno Setup rejects
; non-numeric values like ``-alpha.1`` here). Bump the last segment for
; each alpha; reset to ``0.1.0.0`` when we cut the real 0.1.0 release.
#define AppBinaryVersion "0.1.0.1"
#define AppPublisher "Rovetown"
#define AppURL "https://github.com/Rovetown/CraftGraph"
#define AppExe "craftgraph.exe"
#define CliExe "craftgraph-cli.exe"

[Setup]
; Unique product identifier. Locked in across releases.
AppId={{B3A41E7F-2C5D-4F0A-8E91-7D3B6A2C5E4F}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
VersionInfoVersion={#AppBinaryVersion}

; Per-user install by default; user can pick all-users via the dialog.
DefaultDirName={autopf}\{#AppName}
UsePreviousAppDir=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; 64-bit only; CraftGraph targets modern Windows.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Uninstall + Start Menu setup.
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} {#AppVersion}

; Output settings.
OutputDir=dist
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; Wizard appearance.
WizardStyle=modern
LicenseFile=LICENSE
SetupIconFile=

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Components]
; ``gui`` is fixed -- the installer always includes it. ``cli`` is a
; user-toggleable component; the components page on the wizard shows a
; checkbox the user can clear to skip it. ``Types: full`` means the cli
; gets selected automatically when the user picks the Full install
; option, but Custom installs honour the user's checkbox state.
Name: "gui"; Description: "CraftGraph GUI"; Types: full compact custom; Flags: fixed
Name: "cli"; Description: "Command-line tool (craftgraph-cli.exe)"; Types: full

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Top-level GUI exe -- gui component only.
Source: "dist\{#AppName}\{#AppExe}"; DestDir: "{app}"; Components: gui; Flags: ignoreversion
; GUI bundled dependencies (Python interpreter, Qt DLLs, etc.). recursesubdirs
; preserves the _internal/ tree exactly as PyInstaller emits it.
Source: "dist\{#AppName}\_internal\*"; DestDir: "{app}\_internal"; Components: gui; Flags: ignoreversion recursesubdirs createallsubdirs
; CLI exe -- onefile build, no _internal/ companion needed. Tagged
; ``cli`` so the components page can opt it out. ``skipifsourcedoesntexist``
; lets ``just installer`` work even when only ``just build`` ran (no CLI
; bundle on disk yet); without the flag, ISCC would error.
Source: "dist\{#CliExe}"; DestDir: "{app}"; Components: cli; Flags: ignoreversion skipifsourcedoesntexist
; Ship the project license alongside the binary so users can read it
; locally (also satisfies the "license must travel with the distribution"
; clause for the LGPL-licensed PySide6 bundled in _internal/).
Source: "LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; Components: gui
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Components: gui; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Components: gui; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clear PyInstaller's _internal cache subdirs that the installer didn't
; create -- otherwise the install dir is left non-empty on uninstall.
Type: filesandordirs; Name: "{app}\_internal"
