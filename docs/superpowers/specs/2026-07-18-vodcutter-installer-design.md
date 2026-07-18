# VODCutter Windows Installer (Phase 2)

**Date:** 2026-07-18
**Status:** Design approved, pending spec review
**Depends on:** Phase 1 (`cutter` CLI), merged to main at `d123f74`.

## Problem

Phase 1 made the pipeline reusable, but a customer still needs the repo, a venv,
and manual setup steps. Phase 2 ships a single **`VODCutterSetup.exe`** a
semi-technical customer double-clicks, after which `cutter new` / `cutter run`
work in any terminal and the Resolve menu script is in place.

## Decisions locked in brainstorming

- **Bundle tech:** official python.org **embeddable Python 3.12** runtime with
  all dependencies pre-installed as plain files, wrapped in an **Inno Setup**
  wizard. NOT PyInstaller — frozen unsigned exes are the most likely thing for
  Windows Smart App Control / antivirus to block (torch's DLLs were already
  blocked on the dev machine), and native-dep hooks (ctranslate2, onnxruntime,
  PyAV, RapidOCR) are fragile.
- **Models:** NOT shipped. Whisper `small` (~460 MB) and the ONNX matcher
  (~490 MB) auto-download on the customer's first `cutter run` — both stages
  already do this natively via huggingface_hub / faster-whisper. Installer
  stays ~300–500 MB.
- **GPU:** CPU-only bundle. No NVIDIA cuDNN/cuBLAS wheels (~800 MB+ saved).
  `device = "auto"` already degrades to CPU; the CPU slowness warning already
  exists.
- **Default model:** installer writes a global config with `model = "small"`
  so CPU transcription of a long VOD stays tolerable; customers can raise it.

## Non-goals

- No code changes to the `cutter` package itself (Phase 1 is frozen for this
  work; bugs found during verification are separate fixes).
- No code signing (cost/logistics; revisit if SmartScreen friction proves bad).
- No auto-update mechanism.
- No macOS/Linux installers.
- No CUDA variant of the bundle (a GPU customer can use the repo install).

## Install-time behavior (what VODCutterSetup.exe does)

| Step | Detail |
|---|---|
| Install dir | `%LOCALAPPDATA%\VODCutter` — per-user, `PrivilegesRequired=lowest`, no UAC/admin |
| Payload | `python\` (embeddable runtime + site-packages with all deps + cutter), `cutter.cmd`, `resolve_cut.lua`, `config-default.toml` |
| PATH | Appends the install dir to the **user** PATH (registry `HKCU\Environment`), no duplicates on reinstall |
| Resolve script | Copies `resolve_cut.lua` to `%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\` (dir created if missing) |
| Global config | Copies `config-default.toml` → `%APPDATA%\cutter\config.toml` **only if absent** (`onlyifdoesntexist`) — never clobbers an existing config |
| Uninstall | Standard Apps-list uninstall; removes the install dir including any downloaded `models\`; removes the PATH entry. The Resolve script and `%APPDATA%\cutter` remain (cheap, and removing the Lua could surprise a user mid-project) |

### `cutter.cmd` (the PATH entry point)

```bat
@echo off
set "HF_HOME=%~dp0models"
"%~dp0python\python.exe" -m cutter %*
```

`HF_HOME` is set **per-process only** — both models cache under
`<install dir>\models\`, and user-wide env vars are never touched (no collision
with a dev setup that has its own HF_HOME).

### `config-default.toml`

```toml
# VODCutter defaults. Delete a line to fall back to built-in defaults.
model = "small"    # whisper size; "medium" is more accurate but much slower on CPU
device = "auto"    # auto | cuda | cpu
```

## Build system (repo side)

New `installer/` directory:

```
installer/
  build.ps1             # assembles payload + compiles the installer
  vodcutter.iss         # Inno Setup 6 script
  cutter.cmd            # shim (copied into payload)
  config-default.toml   # default global config (copied into payload)
  payload/              # GENERATED staging area (gitignored)
  Output/               # GENERATED VODCutterSetup.exe (gitignored)
```

### `build.ps1` steps

1. Download `python-3.12.x-embed-amd64.zip` from python.org (pinned version,
   cached in `installer\payload\`), expand to `payload\python\`.
2. Enable site-packages: edit `python312._pth` to uncomment `import site`.
3. Bootstrap pip: download `get-pip.py`, run with the embedded python.
4. `payload\python\python.exe -m pip install -r ..\requirements.txt` **minus
   dev-only lines** (pytest excluded) plus the cutter package itself
   (`pip install <repo root>` — a normal, non-editable install).
5. Stage `cutter.cmd`, `resolve_cut.lua` (from repo root), `config-default.toml`.
6. Smoke-test the payload in isolation (see Verification).
7. Compile: `iscc vodcutter.iss` → `installer\Output\VODCutterSetup.exe`.

Version is read from `pyproject.toml` and passed to Inno (`AppVersion`,
setup filename `VODCutterSetup-<version>.exe`).

**Build prerequisite:** Inno Setup 6 on the build machine
(`winget install -e --id JRSoftware.InnoSetup`).

### `vodcutter.iss` essentials

- `AppName=VODCutter`, `AppVersion` injected, `DefaultDirName={localappdata}\VODCutter`
- `PrivilegesRequired=lowest`, `ArchitecturesAllowed=x64compatible`
- Files: payload tree → `{app}`
- Registry: append `{app}` to `HKCU\Environment\Path` if not present (with
  `ChangesEnvironment=yes` so Explorer broadcasts the change)
- `[Files]` entry for the Resolve Lua → `{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\`
- `[Files]` entry for config-default.toml → `{userappdata}\cutter\config.toml`
  with `onlyifdoesntexist`
- Post-install page text: next steps (`cutter new <job>`, first run downloads
  models, the Resolve click)

## Customer experience

1. Double-click `VODCutterSetup.exe` → wizard → finish.
2. Open a **new** terminal (PATH change needs a fresh shell): `cutter new myjob`.
3. Drop the `.mp4` into `Documents\CutterJobs\myjob\`, write `recap.txt`
   (one prose paragraph).
4. `cutter run myjob` — first run downloads the two models with progress,
   then the pipeline runs (CPU).
5. DaVinci Resolve: import the VOD onto a timeline → Workspace ▸ Scripts ▸
   resolve_cut → `myjob Recap` timeline appears (result popup included).

## Verification

1. **Payload smoke test (pre-package, scripted in build.ps1):** run with ONLY
   the staged runtime — `payload\python\python.exe -m cutter --help` lists all
   subcommands; a scratch job with a `recap.txt` runs the `beatify` stage
   (`python -m cutter beatify <job>`) proving pysbd + the package import work
   without the dev venv. `HF_HOME` pointed at a scratch dir.
2. **Real install test (manual, on the dev machine):** run the built setup,
   which installs to `%LOCALAPPDATA%\VODCutter` (isolated from
   `D:\CutterDavinci`); in a fresh terminal run `cutter new e2etest`, add a
   short real `.mp4` + recap, `cutter run e2etest` — confirms the first-run
   model download into `<install>\models\` and the full CPU pipeline; verify
   the Resolve script was copied and `config.toml` written.
3. **Uninstall test:** uninstall from Apps list; install dir and PATH entry
   gone.

## Risks / open items

- Embeddable-Python + pip is well-trodden but pip-in-embeddable requires the
  `._pth` edit — build.ps1 owns that; a pinned Python patch version keeps it
  reproducible.
- SmartScreen may warn on the unsigned installer ("unknown publisher") — the
  customer clicks "More info → Run anyway". Accepted for now (see Non-goals);
  code signing is the future fix.
- The `zenless` media-pool fallback string in `resolve_cut.lua:93` (flagged in
  the Phase 1 final review) ships to customers as-is; harmless (mp4 match runs
  first) but worth cleaning up in a Phase 1 follow-up.
