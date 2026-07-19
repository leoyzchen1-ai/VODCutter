# VODCutter Windows Installer (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `VODCutterSetup-<version>.exe` — an Inno Setup wizard that installs the cutter pipeline (embeddable Python payload), an optional NVIDIA GPU component, the Resolve menu script, a PATH shim, and a default config.

**Architecture:** `installer/build.ps1` assembles a `payload/` staging tree (official python.org embeddable 3.12 runtime with all deps pip-installed as plain files + the cutter package), stages the GPU DLL trees separately, smoke-tests the payload in isolation, then compiles `installer/vodcutter.iss` with Inno Setup 6. No changes to the `cutter` package itself.

**Tech Stack:** PowerShell 5.1 (build script), python.org embeddable CPython 3.12.10, pip, Inno Setup 6 (Pascal scripting for PATH handling), pip `nvidia-cudnn-cu12`/`nvidia-cublas-cu12` for the GPU component.

**Spec:** `docs/superpowers/specs/2026-07-18-vodcutter-installer-design.md`

## Global Constraints

- Work in `D:\CutterDavinci` on branch `vodcutter-installer`.
- **No code changes to the `cutter` package** — Phase 1 is frozen; bugs found go back to the controller, not fixed inline.
- Run all local Python via PowerShell (never Git Bash). The *payload's* python is invoked directly by absolute path.
- Embeddable Python pinned: **3.12.10** (`python-3.12.10-embed-amd64.zip`; `._pth` file is `python312._pth`).
- Install dir `{localappdata}\VODCutter`; `PrivilegesRequired=lowest`; per-user PATH via `HKCU\Environment`; `ChangesEnvironment=yes`.
- Components: `core` (fixed) + `gpu` (unchecked by default — the default setup type must NOT include it).
- Config → `{userappdata}\cutter\config.toml` with `onlyifdoesntexist uninsneveruninstall`; Resolve Lua → `{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\` with `uninsneveruninstall`.
- Uninstall removes the whole `{app}` dir (including downloaded `models\`) and the PATH entry.
- Models are NOT shipped; they download on first `cutter run` into `{app}\models` (via the `HF_HOME` set in `cutter.cmd`).
- Generated dirs (`installer/payload/`, `installer/cache/`, `installer/Output/`, `installer/tmp-smoke/`) are gitignored — never committed.
- Commit messages end with a second `-m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"`.
- pytest-style TDD does not apply to build scripts and Inno configs; every task instead has explicit verify steps with exact commands and expected output. Run them — do not skip verification.

---

### Task 1: installer/ static files

**Files:**
- Create: `installer/requirements-payload.txt`, `installer/cutter.cmd`, `installer/config-default.toml`, `installer/POSTINSTALL.txt`
- Modify: `.gitignore`

**Interfaces:**
- Produces: the exact filenames `build.ps1` (Task 2) copies into the payload and `vodcutter.iss` (Task 3) references. Do not rename anything.

- [ ] **Step 1: Create `installer/requirements-payload.txt`**

Runtime deps only — pins match the repo's `requirements.txt`, minus dev/test (`pytest`) and minus `scikit-learn` (used only by `legacy/` scripts, which are not part of the installed `cutter` package):

```
# Runtime dependencies shipped inside the installer payload.
# Pins mirror requirements.txt; excludes dev tools (pytest) and legacy-only deps (scikit-learn).
faster-whisper==1.2.1
huggingface-hub==1.24.0
tokenizers==0.22.2
av==18.0.0
numpy==2.5.1
pillow==12.3.0
onnxruntime==1.27.0
rapidocr-onnxruntime==1.4.4
pysbd==0.3.4
```

- [ ] **Step 2: Create `installer/cutter.cmd`**

```bat
@echo off
rem VODCutter entry point. Models cache inside the install dir; the nvidia
rem PATH prepend only fires when the GPU component was installed.
set "HF_HOME=%~dp0models"
if exist "%~dp0python\Lib\site-packages\nvidia\cudnn\bin" (
  set "PATH=%~dp0python\Lib\site-packages\nvidia\cudnn\bin;%~dp0python\Lib\site-packages\nvidia\cublas\bin;%PATH%"
)
"%~dp0python\python.exe" -m cutter %*
```

- [ ] **Step 3: Create `installer/config-default.toml`**

```toml
# VODCutter defaults. Delete a line to fall back to built-in defaults.
model = "small"    # whisper size; "medium" is more accurate but much slower on CPU
device = "auto"    # auto | cuda | cpu
```

- [ ] **Step 4: Create `installer/POSTINSTALL.txt`**

```
VODCutter is installed.

Next steps (open a NEW terminal so the updated PATH is picked up):

  1. cutter new myjob
     Creates Documents\CutterJobs\myjob with a recap.txt template.

  2. Copy your VOD (.mp4) into that folder and replace recap.txt with your
     recap script: ONE flowing paragraph of prose describing everything the
     video should cover, in order.

  3. cutter run myjob
     The first run downloads two AI models (~1 GB total) and then runs the
     whole pipeline. Later runs reuse the downloaded models.

  4. In DaVinci Resolve: import the VOD onto a timeline, then
     Workspace > Scripts > resolve_cut
     A "myjob Recap" timeline appears automatically.

Config: %APPDATA%\cutter\config.toml (model size, GPU/CPU, thresholds).
Jobs:   Documents\CutterJobs\
```

- [ ] **Step 5: Append to `.gitignore`**

```
# Installer build artifacts (installer/build.ps1 outputs)
installer/payload/
installer/cache/
installer/Output/
installer/tmp-smoke/
```

- [ ] **Step 6: Verify and commit**

Run: `Get-ChildItem D:\CutterDavinci\installer` — expect exactly the four files.

```powershell
git add installer/ .gitignore
git commit -m "feat: installer static files (shim, config, postinstall, payload reqs)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: build.ps1 — payload assembly + smoke test

**Files:**
- Create: `installer/build.ps1`

**Interfaces:**
- Consumes: Task 1's four files.
- Produces: `installer/payload/python/` (runtime + site-packages incl. cutter), `installer/payload/gpu/nvidia/` (GPU DLL trees), `installer/payload/cutter.cmd|config-default.toml|POSTINSTALL.txt`; flags `-SkipGpu` and `-SkipCompile`; the ISCC invocation added in Task 3 lives at the end of this script.

- [ ] **Step 1: Write `installer/build.ps1`**

```powershell
# Builds the VODCutter installer payload and (Task 3) compiles the setup exe.
#   powershell -ExecutionPolicy Bypass -File installer\build.ps1 [-SkipGpu] [-SkipCompile]
param([switch]$SkipGpu, [switch]$SkipCompile)
$ErrorActionPreference = "Stop"

$root  = Split-Path $PSScriptRoot -Parent          # repo root
$stage = Join-Path $PSScriptRoot "payload"
$pyDir = Join-Path $stage "python"
$cache = Join-Path $PSScriptRoot "cache"
$PyVer = "3.12.10"
New-Item -ItemType Directory -Force $stage, $cache | Out-Null

Write-Host "== 1/7 embeddable Python $PyVer =="
$zip = Join-Path $cache "python-$PyVer-embed-amd64.zip"
if (-not (Test-Path $zip)) {
  Invoke-WebRequest "https://www.python.org/ftp/python/$PyVer/python-$PyVer-embed-amd64.zip" -OutFile $zip
}
if (Test-Path $pyDir) { Remove-Item $pyDir -Recurse -Force }
Expand-Archive $zip -DestinationPath $pyDir

Write-Host "== 2/7 enable site-packages =="
$pth = Join-Path $pyDir "python312._pth"
(Get-Content $pth) -replace '^#import site$', 'import site' | Set-Content $pth -Encoding ascii

Write-Host "== 3/7 bootstrap pip =="
$getpip = Join-Path $cache "get-pip.py"
if (-not (Test-Path $getpip)) { Invoke-WebRequest "https://bootstrap.pypa.io/get-pip.py" -OutFile $getpip }
& "$pyDir\python.exe" $getpip --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "get-pip failed" }

Write-Host "== 4/7 install runtime deps + cutter =="
& "$pyDir\python.exe" -m pip install --no-warn-script-location -r (Join-Path $PSScriptRoot "requirements-payload.txt")
if ($LASTEXITCODE -ne 0) { throw "dependency install failed" }
& "$pyDir\python.exe" -m pip install --no-warn-script-location $root
if ($LASTEXITCODE -ne 0) { throw "cutter install failed" }

Write-Host "== 5/7 GPU component staging =="
if (-not $SkipGpu) {
  $gpu = Join-Path $stage "gpu"
  if (Test-Path $gpu) { Remove-Item $gpu -Recurse -Force }
  & "$pyDir\python.exe" -m pip install --no-warn-script-location --target $gpu "nvidia-cublas-cu12" "nvidia-cudnn-cu12==9.*"
  if ($LASTEXITCODE -ne 0) { throw "GPU libs install failed" }
} else { Write-Host "   (skipped)" }

Write-Host "== 6/7 stage shim/config/postinstall =="
Copy-Item (Join-Path $PSScriptRoot "cutter.cmd") $stage -Force
Copy-Item (Join-Path $PSScriptRoot "config-default.toml") $stage -Force
Copy-Item (Join-Path $PSScriptRoot "POSTINSTALL.txt") $stage -Force

Write-Host "== 7/7 payload smoke test (isolated, CPU path) =="
$tmp = Join-Path $PSScriptRoot "tmp-smoke"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
New-Item -ItemType Directory -Force $tmp | Out-Null
$env:HF_HOME = Join-Path $tmp "hf"
$help = & "$pyDir\python.exe" -m cutter --help
if ($LASTEXITCODE -ne 0) { throw "cutter --help failed" }
if (-not ($help -join " " -match "beatify")) { throw "--help missing subcommands" }
$job = Join-Path $tmp "smokejob"
New-Item -ItemType Directory -Force $job | Out-Null
Set-Content (Join-Path $job "vod.mp4") "dummy" -Encoding ascii   # beatify never decodes video
Set-Content (Join-Path $job "recap.txt") "First we see the intro. Then we see the gameplay." -Encoding ascii
& "$pyDir\python.exe" -m cutter beatify $job
if ($LASTEXITCODE -ne 0) { throw "beatify smoke failed" }
$beats = @(Get-Content (Join-Path $job "work\beats.txt"))
if ($beats.Count -ne 2) { throw "expected 2 beats, got $($beats.Count)" }
Write-Host "Smoke test OK (2 beats)"

$payloadMB = [math]::Round(((Get-ChildItem $stage -Recurse -File | Measure-Object Length -Sum).Sum)/1MB)
Write-Host "Payload size: $payloadMB MB"

$version = (Select-String -Path (Join-Path $root "pyproject.toml") -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
Write-Host "Version: $version"

if (-not $SkipCompile) {
  $iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
  if (-not $iscc) { throw "Inno Setup 6 not found. Install with: winget install -e --id JRSoftware.InnoSetup" }
  & $iscc "/DAppVersion=$version" (Join-Path $PSScriptRoot "vodcutter.iss")
  if ($LASTEXITCODE -ne 0) { throw "ISCC failed" }
  Write-Host "Installer: $(Join-Path $PSScriptRoot "Output\VODCutterSetup-$version.exe")"
} else { Write-Host "(compile skipped)" }
```

- [ ] **Step 2: Run the payload build (no compile yet)**

Run: `powershell -ExecutionPolicy Bypass -File D:\CutterDavinci\installer\build.ps1 -SkipCompile`
Expected: steps 1–7 all print, ending with `Smoke test OK (2 beats)`, a payload size (~700–900 MB with GPU staging; the `python\` part ~400–500 MB), and `(compile skipped)`. Downloads (~1 GB total incl. NVIDIA wheels) make the first run take several minutes.

- [ ] **Step 3: Spot-check the staging tree**

Run: `Get-ChildItem D:\CutterDavinci\installer\payload; Get-ChildItem D:\CutterDavinci\installer\payload\gpu\nvidia`
Expected: `payload\` holds `python\`, `gpu\`, `cutter.cmd`, `config-default.toml`, `POSTINSTALL.txt`; `gpu\nvidia\` holds `cublas\` and `cudnn\` (each with a `bin\` full of DLLs).

- [ ] **Step 4: Commit**

```powershell
git add installer/build.ps1
git commit -m "feat: installer payload build script with isolated smoke test" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Inno Setup script + compile

**Files:**
- Create: `installer/vodcutter.iss`

**Interfaces:**
- Consumes: the `payload/` tree from Task 2; `AppVersion` passed by build.ps1 via `/DAppVersion=`.
- Produces: `installer/Output/VODCutterSetup-<version>.exe`.

- [ ] **Step 1: Install Inno Setup 6 (build machine prerequisite)**

Run: `winget install -e --id JRSoftware.InnoSetup --accept-source-agreements --accept-package-agreements`
Expected: installed to `C:\Program Files (x86)\Inno Setup 6\` (may require an elevation prompt — accept it; if the sandboxed shell blocks elevation, re-run with the sandbox disabled).
Verify: `Test-Path "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"` → True.

- [ ] **Step 2: Write `installer/vodcutter.iss`**

```iss
; VODCutter installer. Compiled by build.ps1:  ISCC /DAppVersion=x.y.z vodcutter.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppName=VODCutter
AppVersion={#AppVersion}
AppPublisher=leoyz
DefaultDirName={localappdata}\VODCutter
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Output
OutputBaseFilename=VODCutterSetup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ChangesEnvironment=yes
InfoAfterFile=payload\POSTINSTALL.txt

[Types]
Name: "cpu"; Description: "CPU only (works everywhere)"
Name: "gpufull"; Description: "With NVIDIA GPU acceleration"
Name: "custom"; Description: "Custom"; Flags: iscustom

[Components]
Name: "core"; Description: "VODCutter pipeline (required)"; Types: cpu gpufull custom; Flags: fixed
Name: "gpu"; Description: "GPU acceleration (NVIDIA) - requires an NVIDIA GPU (~1 GB)"; Types: gpufull

[Files]
Source: "payload\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs ignoreversion; Components: core
Source: "payload\cutter.cmd"; DestDir: "{app}"; Flags: ignoreversion; Components: core
Source: "..\resolve_cut.lua"; DestDir: "{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility"; Flags: ignoreversion uninsneveruninstall; Components: core
Source: "payload\config-default.toml"; DestDir: "{userappdata}\cutter"; DestName: "config.toml"; Flags: onlyifdoesntexist uninsneveruninstall; Components: core
Source: "payload\gpu\nvidia\*"; DestDir: "{app}\python\Lib\site-packages\nvidia"; Flags: recursesubdirs ignoreversion; Components: gpu

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Check: NeedsAddPath(ExpandConstant('{app}'))

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function NeedsAddPath(Param: string): boolean;
var OrigPath: string;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Param) + ';', ';' + Uppercase(OrigPath) + ';') = 0;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var P, App: string;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if RegQueryStringValue(HKCU, 'Environment', 'Path', P) then
    begin
      App := ExpandConstant('{app}');
      StringChangeEx(P, ';' + App, '', True);
      StringChangeEx(P, App + ';', '', True);
      StringChangeEx(P, App, '', True);
      RegWriteExpandStringValue(HKCU, 'Environment', 'Path', P);
    end;
  end;
end;
```

- [ ] **Step 3: Compile**

Run: `powershell -ExecutionPolicy Bypass -File D:\CutterDavinci\installer\build.ps1`
(The payload from Task 2 is reused; downloads are cached; the smoke test re-runs, then ISCC compiles — LZMA2 on ~1.5 GB takes a while.)
Expected: ends with `Installer: D:\CutterDavinci\installer\Output\VODCutterSetup-0.1.0.exe`.

- [ ] **Step 4: Verify the artifact**

Run: `Get-Item D:\CutterDavinci\installer\Output\VODCutterSetup-0.1.0.exe | Select-Object Name, @{n='GB';e={[math]::Round($_.Length/1GB,2)}}`
Expected: exists; roughly 0.7–2 GB (LZMA2 compresses the DLL trees well; anything under ~0.4 GB or over ~2.5 GB deserves investigation).

- [ ] **Step 5: Commit**

```powershell
git add installer/vodcutter.iss
git commit -m "feat: Inno Setup script with GPU component and PATH handling" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Real install / uninstall verification (dev machine, GPU ON)

No repo files change in this task unless a bug is found (report bugs to the controller — do not patch `cutter/` inline). All artifacts go to the scratchpad or `%LOCALAPPDATA%\VODCutter`.

- [ ] **Step 1: Silent install with the GPU component**

```powershell
& "D:\CutterDavinci\installer\Output\VODCutterSetup-0.1.0.exe" /SILENT /SUPPRESSMSGBOXES /COMPONENTS="core,gpu" /LOG="$env:TEMP\vodcutter-install.log"
```
Wait for the process to exit, then verify:
```powershell
Test-Path "$env:LOCALAPPDATA\VODCutter\cutter.cmd"                                   # True
Test-Path "$env:LOCALAPPDATA\VODCutter\python\python.exe"                            # True
Test-Path "$env:LOCALAPPDATA\VODCutter\python\Lib\site-packages\nvidia\cudnn\bin"    # True (GPU component)
(Get-ItemProperty HKCU:\Environment).Path -like "*VODCutter*"                        # True
Get-Content "$env:APPDATA\cutter\config.toml"                                        # model = "small" ...
# Resolve script matches repo:
(Get-FileHash "$env:APPDATA\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\resolve_cut.lua").Hash -eq (Get-FileHash D:\CutterDavinci\resolve_cut.lua).Hash   # True
```

- [ ] **Step 2: Create a real 60-second test clip**

Write this to the scratchpad as `make_clip.py` and run it with the DEV venv (`D:\CutterDavinci\.venv\Scripts\python.exe make_clip.py`):

```python
"""Remux the first ~60s of the ZZZ3.1 VOD (stream copy, no re-encode)."""
import av, os, sys

SRC = r"E:\Videos\VersionRecaps\ZZZ3.1\source\Zenless Zone Zero Version 3.1 - The Long Goodbye Special Program.mp4"
DST = os.path.join(os.environ["USERPROFILE"], "Documents", "CutterJobs", "e2etest", "vod.mp4")

inp = av.open(SRC)
out = av.open(DST, "w")
m = {}
for s in inp.streams:
    if s.type in ("video", "audio"):
        try:
            m[s] = out.add_stream_from_template(s)   # PyAV >= 12
        except AttributeError:
            m[s] = out.add_stream(template=s)        # older PyAV
for pkt in inp.demux(list(m)):
    if pkt.dts is None:
        continue
    if pkt.pts is not None and float(pkt.pts * pkt.time_base) > 60.0:
        if pkt.stream.type == "video":
            break
        continue
    pkt.stream = m[pkt.stream]
    out.mux(pkt)
out.close(); inp.close()
print("wrote", DST)
```

First scaffold the job so the folder exists, THEN run the script:
```powershell
& "$env:LOCALAPPDATA\VODCutter\cutter.cmd" new e2etest     # creates Documents\CutterJobs\e2etest
& D:\CutterDavinci\.venv\Scripts\python.exe <scratchpad>\make_clip.py
Set-Content "$env:USERPROFILE\Documents\CutterJobs\e2etest\recap.txt" "The hosts introduce the new version update. Then they show the first gameplay preview." -Encoding utf8
```

- [ ] **Step 3: Run the installed pipeline end to end (GPU)**

Run: `& "$env:LOCALAPPDATA\VODCutter\cutter.cmd" run e2etest`
Expected observations (record them):
- First-run model downloads (whisper `small` + the ONNX matcher) — verify afterward: `Test-Path "$env:LOCALAPPDATA\VODCutter\models\hub"` → True.
- Transcription runs WITHOUT the `[warn] transcribing on CPU` line (GPU path — this machine has an RTX 5070 Ti and the component installed the cuDNN/cuBLAS DLLs).
- Pipeline completes; `Documents\CutterJobs\e2etest\out\cuts.csv` and `out\recap.srt` exist.
- `last_job.txt` in the Resolve Utility folder now points at the e2etest `cuts.csv`.
If transcription falls back to CPU or any stage crashes: STOP, capture the full output, report to the controller.

- [ ] **Step 4: Uninstall test**

```powershell
& "$env:LOCALAPPDATA\VODCutter\unins000.exe" /SILENT
```
After it exits, verify:
```powershell
Test-Path "$env:LOCALAPPDATA\VODCutter"                     # False (models dir removed too)
(Get-ItemProperty HKCU:\Environment).Path -like "*VODCutter*"   # False (PATH entry removed)
Test-Path "$env:APPDATA\cutter\config.toml"                 # True  (survives by design)
Test-Path "$env:APPDATA\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\resolve_cut.lua"  # True (survives by design)
```

- [ ] **Step 5: Restore the dev machine's state**

The install test changed two things a developer on THIS machine relies on — put them back:
```powershell
# last_job.txt: point back at the ZZZ3.1 cuts so the user's Resolve flow still works
Set-Content "$env:APPDATA\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\last_job.txt" "E:\Videos\VersionRecaps\ZZZ3.1\output\cuts_gameplay.csv" -NoNewline -Encoding ascii
# global config: remove so the dev repo keeps its built-in defaults (model=medium)
Remove-Item "$env:APPDATA\cutter\config.toml"
```

- [ ] **Step 6: Record results**

Append a short verification log (what ran, durations, model download sizes, GPU confirmed) to the task report. No commit (no repo files changed).

---

### Task 5: Documentation

**Files:**
- Modify: `HOW_IT_WORKS.md` (add a "Shipping it: the installer" section at the end, before Gotchas), `README.md` (extend the update note)

- [ ] **Step 1: Add to `HOW_IT_WORKS.md`** (insert as a new section between "Run it end to end" and "Gotchas"):

```markdown
## Shipping it: the installer

`installer\build.ps1` builds `VODCutterSetup-<version>.exe` — a per-user Inno
Setup wizard for customers (no admin, no Python required):

```powershell
# build machine one-time: winget install -e --id JRSoftware.InnoSetup
powershell -ExecutionPolicy Bypass -File installer\build.ps1
# -> installer\Output\VODCutterSetup-<version>.exe
```

What installing does: puts an embeddable Python + the pipeline in
`%LOCALAPPDATA%\VODCutter`, adds `cutter` to the user PATH, installs the
Resolve menu script, and writes a default `%APPDATA%\cutter\config.toml`
(`model = "small"` for tolerable CPU transcription). An optional
"GPU acceleration (NVIDIA)" checkbox lays cuDNN/cuBLAS into the bundled
runtime — with it, `device = "auto"` uses the GPU automatically. Models are
not shipped; the first `cutter run` downloads them (~1 GB) into
`%LOCALAPPDATA%\VODCutter\models`. Uninstalling (Windows Apps list) removes
the install dir, downloaded models, and the PATH entry.

Customer flow after install: open a new terminal → `cutter new myjob` →
drop in the VOD + write `recap.txt` → `cutter run myjob` → one click in
Resolve. The installer shows these steps on its final page.
```

- [ ] **Step 2: Extend the README note** — change the existing update blockquote's last line to also mention the installer:

After the sentence about per-script commands being superseded, append:
```markdown
> Customers get `installer\Output\VODCutterSetup-<version>.exe` (built by
> `installer\build.ps1`) — see "Shipping it: the installer" in HOW_IT_WORKS.md.
```

- [ ] **Step 3: Verify docs against reality**

Cross-check every path/command named in the new sections against the actual repo (`installer\build.ps1` exists, output filename matches the iss `OutputBaseFilename`, config keys match `config-default.toml`).

- [ ] **Step 4: Commit**

```powershell
git add HOW_IT_WORKS.md README.md
git commit -m "docs: document the installer build and customer install flow" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
