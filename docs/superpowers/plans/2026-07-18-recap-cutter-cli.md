# Recap Cutter CLI (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the hardcoded single-project pipeline into a reusable `cutter` CLI: a job folder (VOD + prose recap) in, `out\cuts.csv` + one Resolve click out.

**Architecture:** A `cutter/` Python package containing the five existing stage scripts (moved in, `PROJECT` constants removed, core logic extracted into `run_*` functions taking explicit paths), plus new modules: config (TOML), job resolution, beatify (prose→beats), device fallback, srt, pipeline orchestrator (cache-skip), and an argparse CLI. `resolve_cut.lua` finds the newest job via `last_job.txt` instead of a hardcoded path.

**Tech Stack:** Python 3.12 (`.venv`), faster-whisper, onnxruntime, PyAV, RapidOCR, pysbd (new), tomllib (stdlib), pytest (new), Lua (Resolve console).

**Spec:** `docs/superpowers/specs/2026-07-18-recap-cutter-cli-design.md`

## Global Constraints

- Work in `D:\CutterDavinci` on branch `recap-cutter-cli`.
- Run ALL Python via the venv in **PowerShell**: `.venv\Scripts\python.exe` (Git Bash trips Windows Smart App Control on native DLLs).
- Test command: `.venv\Scripts\python.exe -m pytest tests -v` (e2e tests excluded by default via pytest markers).
- No torch. No network at runtime except one-time HF model downloads (`HF_HOME=D:\CutterDavinci\huggingface` already set).
- Do not touch `legacy/`. Do not modify the existing `E:\Videos\VersionRecaps\ZZZ3.1` data.
- Fixed jobs root default: `%USERPROFILE%\Documents\CutterJobs`. Global config: `%APPDATA%\cutter\config.toml`. Job config: `<job>\cutter.toml`.
- Job folder layout (spec): inputs `vod.mp4` (first `*.mp4`) + `recap.txt`; generated `work\beats.txt`, `work\transcript.json`, `work\matches.csv`, `work\motion.csv`, `work\ocr.csv`; deliverables `out\cuts.csv`, `out\recap.srt`.
- Every stage skips if its output file exists ("delete the cache to rebuild"). Per-stage CLI subcommands force-rerun their stage.
- Errors are plain-English `SystemExit` messages raised BEFORE slow work.
- End every commit message with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` (use a second `-m`).

---

### Task 1: Package scaffold + editable install

**Files:**
- Create: `pyproject.toml`, `cutter/__init__.py`, `tests/__init__.py`, `tests/test_scaffold.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: importable `cutter` package; `cutter` console script; `pytest` configured with an `e2e` marker excluded by default.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scaffold.py
def test_package_imports():
    import cutter
    assert cutter.__version__ == "0.1.0"
```

Also create empty `tests/__init__.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'cutter'` or pytest not installed — if pytest missing, first do Step 3's pip install, then re-run to see the import failure).

- [ ] **Step 3: Create package, pyproject, and install**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "cutter"
version = "0.1.0"
description = "Recap-to-cuts pipeline: VOD + prose recap -> DaVinci Resolve timeline"
requires-python = ">=3.11"

[project.scripts]
cutter = "cutter.cli:main"

[tool.setuptools]
packages = ["cutter"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-m 'not e2e'"
markers = ["e2e: full-pipeline test; needs models + video encode; run with: pytest -m e2e"]
```

```python
# cutter/__init__.py
__version__ = "0.1.0"
```

Append to `requirements.txt`:

```
# --- beatify (prose -> beats) + tests ---
pysbd==0.3.4
pytest>=8
```

Run: `.venv\Scripts\python.exe -m pip install -r requirements.txt -e .`
Expected: installs pysbd, pytest, and `cutter` in editable mode. (`cutter.cli` doesn't exist yet — the console script only resolves at invocation time, so install succeeds.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests -v`
Expected: 1 PASS

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml cutter/__init__.py tests/__init__.py tests/test_scaffold.py requirements.txt
git commit -m "feat: scaffold cutter package with pyproject and pytest" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Config module (defaults, TOML, global<job override)

**Files:**
- Create: `cutter/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces:
  - `Config` frozen dataclass, fields (with defaults): `model: str = "medium"`, `device: str = "auto"`, `min_conf: float = 0.15`, `clip_len: float = 9.0`, `move_thresh: float = 6.0`, `min_moving_frac: float = 0.55`, `ocr_sample: float = 3.0`, `window_segments: int = 8`, `stride: int = 3`, `jobs_root: str = ""`
  - `load_config(job_dir: Path | None = None) -> Config`
  - `jobs_root_path(cfg: Config) -> Path` (config override or `%USERPROFILE%\Documents\CutterJobs`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
from pathlib import Path
import pytest
from cutter.config import Config, load_config, jobs_root_path


def test_defaults_when_no_files(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cfg = load_config()
    assert cfg.model == "medium"
    assert cfg.device == "auto"
    assert cfg.min_conf == 0.15
    assert cfg.window_segments == 8


def test_job_overrides_global(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    (tmp_path / "cutter").mkdir()
    (tmp_path / "cutter" / "config.toml").write_text('model = "small"\nmin_conf = 0.2\n', encoding="utf-8")
    job = tmp_path / "job"
    job.mkdir()
    (job / "cutter.toml").write_text("min_conf = 0.3\n", encoding="utf-8")
    cfg = load_config(job)
    assert cfg.model == "small"      # from global
    assert cfg.min_conf == 0.3       # job wins


def test_unknown_key_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    job = tmp_path / "job"
    job.mkdir()
    (job / "cutter.toml").write_text("banana = 1\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="banana"):
        load_config(job)


def test_jobs_root_default_and_override(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert jobs_root_path(Config()) == tmp_path / "Documents" / "CutterJobs"
    assert jobs_root_path(Config(jobs_root=r"D:\jobs")) == Path(r"D:\jobs")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cutter.config'`

- [ ] **Step 3: Implement**

```python
# cutter/config.py
"""Configuration: dataclass defaults <- %APPDATA%\\cutter\\config.toml <- <job>\\cutter.toml."""
import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Config:
    model: str = "medium"          # whisper size: tiny/base/small/medium/large-v3
    device: str = "auto"           # auto | cuda | cpu
    min_conf: float = 0.15         # skip beats matched below this confidence
    clip_len: float = 9.0          # target seconds per cut
    move_thresh: float = 6.0       # motion magnitude counting as "moving"
    min_moving_frac: float = 0.55  # window must move this often to be gameplay
    ocr_sample: float = 3.0        # seconds between OCR'd frames
    window_segments: int = 8       # transcript segments per matching window
    stride: int = 3                # window slide step
    jobs_root: str = ""            # empty -> %USERPROFILE%\Documents\CutterJobs


def _load_toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_config(job_dir: Path | None = None) -> Config:
    data = _load_toml(Path(os.environ["APPDATA"]) / "cutter" / "config.toml")
    if job_dir is not None:
        data.update(_load_toml(Path(job_dir) / "cutter.toml"))
    valid = {f.name for f in fields(Config)}
    unknown = sorted(set(data) - valid)
    if unknown:
        raise SystemExit(
            f"Unknown config key(s): {', '.join(unknown)}. Valid keys: {', '.join(sorted(valid))}"
        )
    return Config(**data)


def jobs_root_path(cfg: Config) -> Path:
    if cfg.jobs_root:
        return Path(cfg.jobs_root)
    return Path(os.environ["USERPROFILE"]) / "Documents" / "CutterJobs"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```powershell
git add cutter/config.py tests/test_config.py
git commit -m "feat: config module with TOML global/job override" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Job model (folder resolution, paths, validation)

**Files:**
- Create: `cutter/jobs.py`, `tests/test_jobs.py`

**Interfaces:**
- Consumes: nothing (pure paths).
- Produces:
  - `Job` frozen dataclass with `root: Path` and properties: `work` (`root/"work"`), `out` (`root/"out"`), `beats` (`work/"beats.txt"`), `transcript` (`work/"transcript.json"`), `matches` (`work/"matches.csv"`), `motion` (`work/"motion.csv"`), `ocr` (`work/"ocr.csv"`), `cuts` (`out/"cuts.csv"`), `srt` (`out/"recap.srt"`), `recap` (`root/"recap.txt"`); method `find_vod() -> Path`; method `ensure_dirs()`.
  - `resolve_job(name_or_path: str, jobs_root: Path) -> Job` (raises `SystemExit` if folder missing)
  - `validate_inputs(job: Job) -> None` (raises `SystemExit` on missing/empty vod or recap)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_jobs.py
import pytest
from cutter.jobs import Job, resolve_job, validate_inputs


def make_job(tmp_path, name="j"):
    root = tmp_path / name
    root.mkdir()
    (root / "stream.mp4").write_bytes(b"\x00" * 64)
    (root / "recap.txt").write_text("First thing. Second thing.", encoding="utf-8")
    return root


def test_resolve_by_name(tmp_path):
    root = make_job(tmp_path)
    job = resolve_job("j", tmp_path)
    assert job.root == root


def test_resolve_by_absolute_path(tmp_path):
    root = make_job(tmp_path)
    job = resolve_job(str(root), tmp_path / "elsewhere")
    assert job.root == root


def test_missing_folder_is_plain_english(tmp_path):
    with pytest.raises(SystemExit, match="Job folder not found"):
        resolve_job("nope", tmp_path)


def test_derived_paths(tmp_path):
    job = Job(root=tmp_path)
    assert job.beats == tmp_path / "work" / "beats.txt"
    assert job.transcript == tmp_path / "work" / "transcript.json"
    assert job.matches == tmp_path / "work" / "matches.csv"
    assert job.motion == tmp_path / "work" / "motion.csv"
    assert job.ocr == tmp_path / "work" / "ocr.csv"
    assert job.cuts == tmp_path / "out" / "cuts.csv"
    assert job.srt == tmp_path / "out" / "recap.srt"


def test_find_vod_picks_first_mp4(tmp_path):
    root = make_job(tmp_path)
    job = Job(root=root)
    assert job.find_vod().name == "stream.mp4"


def test_validate_missing_vod(tmp_path):
    root = tmp_path / "j"
    root.mkdir()
    (root / "recap.txt").write_text("Words.", encoding="utf-8")
    with pytest.raises(SystemExit, match="No .mp4"):
        validate_inputs(Job(root=root))


def test_validate_blank_recap(tmp_path):
    root = make_job(tmp_path)
    (root / "recap.txt").write_text("   \n  ", encoding="utf-8")
    with pytest.raises(SystemExit, match="recap.txt"):
        validate_inputs(Job(root=root))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cutter.jobs'`

- [ ] **Step 3: Implement**

```python
# cutter/jobs.py
"""A job = one folder holding one VOD + recap and everything generated from them."""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Job:
    root: Path

    @property
    def work(self) -> Path: return self.root / "work"
    @property
    def out(self) -> Path: return self.root / "out"
    @property
    def recap(self) -> Path: return self.root / "recap.txt"
    @property
    def beats(self) -> Path: return self.work / "beats.txt"
    @property
    def transcript(self) -> Path: return self.work / "transcript.json"
    @property
    def matches(self) -> Path: return self.work / "matches.csv"
    @property
    def motion(self) -> Path: return self.work / "motion.csv"
    @property
    def ocr(self) -> Path: return self.work / "ocr.csv"
    @property
    def cuts(self) -> Path: return self.out / "cuts.csv"
    @property
    def srt(self) -> Path: return self.out / "recap.srt"

    def find_vod(self) -> Path:
        vods = sorted(self.root.glob("*.mp4"))
        if not vods:
            raise SystemExit(f"No .mp4 found in {self.root}. Copy your VOD into the job folder.")
        return vods[0]

    def ensure_dirs(self) -> None:
        self.work.mkdir(exist_ok=True)
        self.out.mkdir(exist_ok=True)


def resolve_job(name_or_path: str, jobs_root: Path) -> Job:
    p = Path(name_or_path)
    root = p if p.is_absolute() else jobs_root / name_or_path
    if not root.is_dir():
        raise SystemExit(
            f"Job folder not found: {root}\n"
            f"Create it with: cutter new {name_or_path}"
        )
    return Job(root=root)


def validate_inputs(job: Job) -> None:
    vod = job.find_vod()                       # raises if missing
    if vod.stat().st_size == 0:
        raise SystemExit(f"VOD is empty: {vod}")
    if not job.recap.is_file():
        raise SystemExit(f"Missing recap.txt in {job.root}. Write your recap as one prose paragraph.")
    if not job.recap.read_text(encoding="utf-8").strip():
        raise SystemExit(f"recap.txt is blank: {job.recap}. Write your recap as one prose paragraph.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_jobs.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```powershell
git add cutter/jobs.py tests/test_jobs.py
git commit -m "feat: job model with folder resolution and input validation" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Beatify (prose paragraph -> beats.txt)

**Files:**
- Create: `cutter/beatify.py`, `tests/test_beatify.py`

**Interfaces:**
- Consumes: `Job` from `cutter.jobs` (uses `job.recap`, `job.beats`, `job.ensure_dirs()`).
- Produces:
  - `split_prose(text: str) -> list[str]` — pure; pysbd sentence split with regex fallback.
  - `run_beatify(job: Job) -> None` — reads `recap.txt`, writes one beat per line to `work\beats.txt`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_beatify.py
import pytest
from cutter.beatify import split_prose, run_beatify
from cutter.jobs import Job

PROSE = (
    "Here's a quick recap of the Zenless Zone Zero 3.1 live stream. "
    "There's a Mr. Click photography event and 1,600 Polychromes just for logging in. "
    "That's Jane, Soldier 0 Anby, Hugo, Trigger, or Lucia, along with their W-Engine."
)


def test_splits_into_three_sentences():
    beats = split_prose(PROSE)
    assert len(beats) == 3


def test_does_not_split_on_decimals_abbrevs_numbers():
    beats = split_prose(PROSE)
    assert any("3.1 live stream" in b for b in beats)          # decimal survives
    assert not any(b.rstrip().endswith("Mr.") for b in beats)  # abbreviation survives
    assert any("1,600 Polychromes" in b for b in beats)        # thousands comma survives
    assert any("Soldier 0 Anby" in b for b in beats)           # digit-in-name survives


def test_collapses_whitespace_and_newlines():
    beats = split_prose("One  thing\nhere. Two things   there.")
    assert beats == ["One thing here.", "Two things there."]


def test_empty_text_gives_no_beats():
    assert split_prose("   \n ") == []


def test_run_beatify_writes_one_beat_per_line(tmp_path):
    root = tmp_path / "j"
    root.mkdir()
    (root / "recap.txt").write_text(PROSE, encoding="utf-8")
    job = Job(root=root)
    run_beatify(job)
    lines = job.beats.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3


def test_run_beatify_blank_recap_fails_plainly(tmp_path):
    root = tmp_path / "j"
    root.mkdir()
    (root / "recap.txt").write_text(" ", encoding="utf-8")
    with pytest.raises(SystemExit, match="recap.txt"):
        run_beatify(Job(root=root))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_beatify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cutter.beatify'`

- [ ] **Step 3: Implement**

```python
# cutter/beatify.py
"""Stage 0: split the customer's prose recap paragraph into one beat per line.

Rule-based and offline: pysbd handles abbreviations (Mr.), decimals (3.1) and
thousands separators (1,600). A regex splitter is the fallback if pysbd is
unavailable. The output work\\beats.txt is editable: `cutter run` regenerates it
only if absent, so a human can merge/split beats before matching runs.
"""
import re
from .jobs import Job


def _regex_split(text: str) -> list[str]:
    # Best-effort fallback: split after .!? followed by whitespace + capital,
    # but not after a single capital letter or common abbreviation.
    parts = re.split(r"(?<!\b[A-Z])(?<!\bMr)(?<!\bMs)(?<!\bDr)(?<=[.!?])\s+(?=[A-Z\"'])", text)
    return [p.strip() for p in parts if p.strip()]


def split_prose(text: str) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    try:
        import pysbd
        seg = pysbd.Segmenter(language="en", clean=False)
        beats = [s.strip() for s in seg.segment(text)]
    except ImportError:
        beats = _regex_split(text)
    return [b for b in beats if b]


def run_beatify(job: Job) -> None:
    if not job.recap.is_file() or not job.recap.read_text(encoding="utf-8").strip():
        raise SystemExit(f"recap.txt is missing or blank: {job.recap}. Write your recap as one prose paragraph.")
    beats = split_prose(job.recap.read_text(encoding="utf-8"))
    if not beats:
        raise SystemExit(f"Could not extract any beats from {job.recap}.")
    job.ensure_dirs()
    job.beats.write_text("\n".join(beats) + "\n", encoding="utf-8")
    print(f"[beatify] {len(beats)} beats -> {job.beats} (edit this file, then delete downstream caches to re-match)")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_beatify.py -v`
Expected: 6 PASS. If a pysbd split disagrees with a test (e.g. "Soldier 0 Anby"), the test tells you exactly which text broke — adjust `split_prose` post-processing (merge a beat shorter than 4 words into the previous one), not the test.

- [ ] **Step 5: Commit**

```powershell
git add cutter/beatify.py tests/test_beatify.py
git commit -m "feat: beatify stage, prose recap to beats via pysbd" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Device selection with CUDA->CPU fallback

**Files:**
- Create: `cutter/device.py`, `tests/test_device.py`

**Interfaces:**
- Produces: `pick_device(requested: str = "auto") -> tuple[str, str]` returning `("cuda", "float16")` or `("cpu", "int8")`; internal seam `_cuda_count() -> int`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_device.py
import cutter.device as device


def test_explicit_cpu():
    assert device.pick_device("cpu") == ("cpu", "int8")


def test_explicit_cuda():
    assert device.pick_device("cuda") == ("cuda", "float16")


def test_auto_with_gpu(monkeypatch):
    monkeypatch.setattr(device, "_cuda_count", lambda: 1)
    assert device.pick_device("auto") == ("cuda", "float16")


def test_auto_without_gpu(monkeypatch):
    monkeypatch.setattr(device, "_cuda_count", lambda: 0)
    assert device.pick_device("auto") == ("cpu", "int8")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_device.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# cutter/device.py
"""GPU probe: default 'auto' uses CUDA when present, else CPU/int8.

A customer's machine likely has no CUDA -- degrade, don't crash.
"""


def _cuda_count() -> int:
    try:
        import ctranslate2  # ships with faster-whisper
        return ctranslate2.get_cuda_device_count()
    except Exception:
        return 0


def pick_device(requested: str = "auto") -> tuple[str, str]:
    if requested == "cpu":
        return ("cpu", "int8")
    if requested == "cuda":
        return ("cuda", "float16")
    if _cuda_count() > 0:
        return ("cuda", "float16")
    print("[device] no CUDA GPU found; using CPU/int8 (slower but works everywhere)")
    return ("cpu", "int8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_device.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```powershell
git add cutter/device.py tests/test_device.py
git commit -m "feat: device auto-selection with CPU fallback" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Move transcribe into package + runtime CUDA fallback

**Files:**
- Move: `transcribe.py` -> `cutter/transcribe.py` (via `git mv`)
- Modify: `cutter/transcribe.py`
- Test: `tests/test_transcribe.py`

**Interfaces:**
- Consumes: `pick_device` from `cutter.device`.
- Produces: `run_transcribe(video: Path, out_json: Path, model: str, device: str = "auto") -> None`; existing `transcribe(video_path, model_size, device, compute_type, task)` kept (import of faster_whisper made lazy).

- [ ] **Step 1: Move the file**

```powershell
git mv transcribe.py cutter/transcribe.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_transcribe.py
import json
import cutter.transcribe as tr


def test_run_transcribe_falls_back_to_cpu_on_cuda_error(monkeypatch, tmp_path):
    calls = []

    def fake_transcribe(video, model, device, ctype, task="transcribe"):
        calls.append((device, ctype))
        if device == "cuda":
            raise RuntimeError("cudnn not found")
        return [{"start": 0.0, "end": 1.0, "text": "hi"}]

    monkeypatch.setattr(tr, "transcribe", fake_transcribe)
    monkeypatch.setattr(tr, "pick_device", lambda req: ("cuda", "float16"))

    out = tmp_path / "work" / "transcript.json"
    tr.run_transcribe(tmp_path / "v.mp4", out, model="medium", device="auto")

    assert calls == [("cuda", "float16"), ("cpu", "int8")]
    assert json.loads(out.read_text(encoding="utf-8"))[0]["text"] == "hi"


def test_run_transcribe_writes_json(monkeypatch, tmp_path):
    monkeypatch.setattr(tr, "transcribe", lambda *a, **k: [{"start": 0.0, "end": 2.5, "text": "hello"}])
    monkeypatch.setattr(tr, "pick_device", lambda req: ("cpu", "int8"))
    out = tmp_path / "transcript.json"
    tr.run_transcribe(tmp_path / "v.mp4", out, model="tiny")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == [{"start": 0.0, "end": 2.5, "text": "hello"}]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_transcribe.py -v`
Expected: FAIL — `AttributeError: module 'cutter.transcribe' has no attribute 'run_transcribe'` (the module-level `from faster_whisper import WhisperModel` may also make collection slow; the next step fixes that too).

- [ ] **Step 4: Modify cutter/transcribe.py**

Replace the import block and add `run_transcribe`. The file becomes:

```python
# cutter/transcribe.py
"""
Transcribe a video file to a timestamped JSON transcript using faster-whisper.

Standalone usage:
    python -m cutter.transcribe path/to/stream.mp4 -o transcript.json --model medium
"""
import argparse
import json
from pathlib import Path

from .device import pick_device


def transcribe(video_path, model_size="medium", device="cuda", compute_type="float16", task="transcribe"):
    from faster_whisper import WhisperModel  # lazy: heavy import
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, info = model.transcribe(video_path, beam_size=5, vad_filter=True, task=task)

    result = []
    for seg in segments:
        result.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
        })
        print(f"[{seg.start:8.1f}s -> {seg.end:8.1f}s] {seg.text.strip()}")

    return result


def run_transcribe(video: Path, out_json: Path, model: str, device: str = "auto") -> None:
    """Pipeline stage: transcribe with auto device + runtime CPU fallback."""
    dev, ctype = pick_device(device)
    try:
        segments = transcribe(str(video), model, dev, ctype)
    except Exception as e:
        if dev != "cuda":
            raise
        print(f"[!] CUDA transcription failed ({e}); retrying on CPU/int8")
        segments = transcribe(str(video), model, "cpu", "int8")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(segments, f, indent=2, ensure_ascii=False)
    print(f"[transcribe] {len(segments)} segments -> {out_json}")


def main():
    parser = argparse.ArgumentParser(description="Transcribe video with timestamps")
    parser.add_argument("video", help="Path to source video/audio file")
    parser.add_argument("-o", "--output", default="transcript.json", help="Output JSON path")
    parser.add_argument("--model", default="medium", help="Whisper model size (tiny/base/small/medium/large-v3)")
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"], help="Inference device")
    parser.add_argument("--task", default="transcribe", choices=["transcribe", "translate"])
    args = parser.parse_args()
    run_transcribe(Path(args.video), Path(args.output), args.model, args.device)


if __name__ == "__main__":
    main()
```

(Note: the old `--compute-type` flag is folded into device selection; the old `task` parameter survives on `transcribe()` itself.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_transcribe.py -v`
Expected: 2 PASS

- [ ] **Step 6: Commit**

```powershell
git add -A
git commit -m "refactor: move transcribe into package with device fallback stage" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Move ONNX matcher into package, extract run_match

**Files:**
- Move: `match_recap_onnx.py` -> `cutter/match_onnx.py` (via `git mv`)
- Modify: `cutter/match_onnx.py`
- Test: `tests/test_match_onnx.py`

**Interfaces:**
- Produces: `run_match(transcript_path, beats_path, out_path, window_segments=8, stride=3, enforce_order=False, backtrack_slack=30.0, flag_below=0.35) -> None`; pure `build_windows(segments, window_segments, stride)` unchanged and importable.

- [ ] **Step 1: Move the file**

```powershell
git mv match_recap_onnx.py cutter/match_onnx.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_match_onnx.py
from cutter.match_onnx import build_windows


def _segs(n):
    return [{"start": float(i), "end": float(i + 1), "text": f"s{i}"} for i in range(n)]


def test_windows_cover_whole_transcript():
    w = build_windows(_segs(10), window_segments=4, stride=2)
    assert w[0]["start"] == 0.0 and w[0]["end"] == 4.0
    assert w[1]["start"] == 2.0
    assert w[-1]["end"] == 10.0          # last window reaches the end


def test_window_text_joins_segments():
    w = build_windows(_segs(4), window_segments=2, stride=2)
    assert w[0]["text"] == "s0 s1"


def test_short_transcript_single_window():
    w = build_windows(_segs(3), window_segments=8, stride=3)
    assert len(w) == 1 and w[0]["end"] == 3.0


def test_run_match_is_importable():
    from cutter.match_onnx import run_match
    assert callable(run_match)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_match_onnx.py -v`
Expected: FAIL — `ImportError: cannot import name 'run_match'` (the module import itself works after the move; `build_windows` tests may already pass).

- [ ] **Step 4: Refactor main() body into run_match**

In `cutter/match_onnx.py`, replace `main()` with a `run_match` function plus a thin `main()`. The rest of the file (docstring, imports, `REPO`, `MAX_LEN`, `load_transcript`, `load_recap_lines`, `build_windows`, `Embedder`) is unchanged:

```python
def run_match(transcript_path, beats_path, out_path, window_segments=8, stride=3,
              enforce_order=False, backtrack_slack=30.0, flag_below=0.35):
    """Pipeline stage: semantic-match each beat to a transcript window."""
    segments = load_transcript(transcript_path)
    recap_lines = load_recap_lines(beats_path)
    if not segments:
        raise SystemExit(f"Transcript is empty: {transcript_path}")
    if not recap_lines:
        raise SystemExit(f"Beats file is empty: {beats_path}")
    windows = build_windows(segments, window_segments, stride)
    print(f"{len(recap_lines)} recap beats, {len(windows)} transcript windows")

    emb = Embedder()
    print("Embedding transcript windows...")
    win_vecs = emb.encode([w["text"] for w in windows])
    print("Embedding recap beats...")
    rec_vecs = emb.encode(recap_lines)
    sims = rec_vecs @ win_vecs.T                                  # cosine (both normalized)

    results = []
    cursor = -backtrack_slack
    for i, line in enumerate(recap_lines):
        row = sims[i].copy()
        if enforce_order:
            for j, w in enumerate(windows):
                if w["start"] < cursor:
                    row[j] = -1.0
        j = int(row.argmax())
        best = windows[j]
        results.append({
            "recap_line": line,
            "start": round(best["start"], 1),
            "end": round(best["end"], 1),
            "confidence": round(float(sims[i][j]), 3),
            "matched_transcript": best["text"][:160],
        })
        if enforce_order:
            cursor = best["start"] - backtrack_slack

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["recap_line", "start", "end", "confidence", "matched_transcript"])
        w.writeheader()
        w.writerows(results)
    print(f"\nWrote {len(results)} matches to {out_path}")
    low = [r for r in results if r["confidence"] < flag_below]
    if low:
        print(f"[!] {len(low)} below {flag_below}:")
        for r in low:
            print(f"  [{r['start']}s] conf {r['confidence']} {r['recap_line'][:55]}")


def main():
    p = argparse.ArgumentParser(description="Torch-free multilingual semantic recap matcher")
    p.add_argument("transcript")
    p.add_argument("recap")
    p.add_argument("-o", "--output", default="matches_onnx.csv")
    p.add_argument("--window-segments", type=int, default=8)
    p.add_argument("--stride", type=int, default=3)
    p.add_argument("--enforce-order", action="store_true")
    p.add_argument("--backtrack-slack", type=float, default=30.0)
    p.add_argument("--flag-below", type=float, default=0.35)
    args = p.parse_args()
    run_match(args.transcript, args.recap, args.output, args.window_segments,
              args.stride, args.enforce_order, args.backtrack_slack, args.flag_below)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_match_onnx.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```powershell
git add -A
git commit -m "refactor: move ONNX matcher into package, extract run_match" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Move motion precompute into package as cutter/motion.py

**Files:**
- Move: `snap_gameplay.py` -> `cutter/motion.py` (via `git mv`)
- Modify: `cutter/motion.py`
- Test: `tests/test_motion.py`

**Interfaces:**
- Produces: `compute_motion(video, sample_hz, aw, ah)`, `load_or_build_motion(video, cache, sample_hz, aw, ah)` (both unchanged in behavior), constants `SAMPLE_HZ=4, AW=160, AH=90`, and `run_motion(video: Path, cache: Path) -> None`.
- Deletes: the old `PROJECT/VIDEO/MATCHES/OUT` constants, the snapping half (`best_window`, `main`) — `snap_visual` (Task 9) is the one snapper now.

- [ ] **Step 1: Move the file**

```powershell
git mv snap_gameplay.py cutter/motion.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_motion.py
import os
import time
from cutter.motion import load_or_build_motion, run_motion


def test_loads_fresh_cache_without_decoding(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"\x00")
    cache = tmp_path / "motion.csv"
    cache.write_text("t,mag\n0.000,1.000\n0.250,7.000\n", encoding="utf-8")
    now = time.time()
    os.utime(video, (now - 100, now - 100))   # cache newer than video
    os.utime(cache, (now, now))

    times, mags = load_or_build_motion(str(video), str(cache), 4, 160, 90)
    assert list(times) == [0.0, 0.25]
    assert list(mags) == [1.0, 7.0]


def test_run_motion_is_importable():
    assert callable(run_motion)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_motion.py -v`
Expected: FAIL — `ImportError: cannot import name 'run_motion'`

- [ ] **Step 4: Trim and adapt the module**

`cutter/motion.py` keeps only the motion code. Full new content:

```python
# cutter/motion.py
"""Whole-VOD motion precompute (cached in work\\motion.csv).

Gameplay/PV footage has sustained visual motion; talking-head couch shots are
nearly static. Downstream, cutter/snap.py uses this signal to land cuts on the
footage a beat describes instead of the people describing it.
"""
import csv
import os
from pathlib import Path

import av
import numpy as np

SAMPLE_HZ = 4            # motion samples per second
AW, AH = 160, 90         # downscaled analysis resolution (gray)


def compute_motion(video, sample_hz, aw, ah):
    """Return (times, mags) numpy arrays: per-sample mean abs frame difference."""
    container = av.open(video)
    stream = container.streams.video[0]
    tb = stream.time_base
    step = 1.0 / sample_hz
    prev = None
    last_t = -1e9
    times, mags = [], []
    for frame in container.decode(stream):
        t = float(frame.pts * tb) if frame.pts is not None else None
        if t is None or t - last_t < step:
            continue
        last_t = t
        g = frame.reformat(width=aw, height=ah, format="gray").to_ndarray().astype(np.int16)
        if prev is not None:
            times.append(t)
            mags.append(float(np.abs(g - prev).mean()))
        prev = g
    container.close()
    return np.array(times), np.array(mags)


def load_or_build_motion(video, cache, sample_hz, aw, ah):
    if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(video):
        arr = np.loadtxt(cache, delimiter=",", skiprows=1)
        print(f"Loaded cached motion: {cache} ({len(arr)} samples)")
        return arr[:, 0], arr[:, 1]
    print("Computing motion (one-time; decodes the whole VOD)...")
    times, mags = compute_motion(video, sample_hz, aw, ah)
    with open(cache, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t", "mag"])
        for t, m in zip(times, mags):
            w.writerow([f"{t:.3f}", f"{m:.3f}"])
    print(f"Wrote motion cache: {cache} ({len(times)} samples)")
    return times, mags


def run_motion(video: Path, cache: Path) -> None:
    """Pipeline stage: ensure work\\motion.csv exists and is fresh."""
    cache.parent.mkdir(parents=True, exist_ok=True)
    load_or_build_motion(str(video), str(cache), SAMPLE_HZ, AW, AH)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_motion.py -v`
Expected: 2 PASS

- [ ] **Step 6: Commit**

```powershell
git add -A
git commit -m "refactor: snap_gameplay becomes cutter/motion, precompute only" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Move OCR pass into package, extract run_ocr

**Files:**
- Move: `ocr_pass.py` -> `cutter/ocr_pass.py` (via `git mv`)
- Modify: `cutter/ocr_pass.py`
- Test: `tests/test_ocr_pass.py`

**Interfaces:**
- Produces: `run_ocr(video, matches, motion, out, sample=3.0, full=False) -> None`; pure `needed_windows(matches, motion, back, fwd)` unchanged and importable; constants `OCR_BACK=25.0, OCR_FWD=80.0` kept.

- [ ] **Step 1: Move the file**

```powershell
git mv ocr_pass.py cutter/ocr_pass.py
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_ocr_pass.py
import csv
from cutter.ocr_pass import needed_windows, OCR_BACK, OCR_FWD


def _write_motion(path, gameplay_ranges):
    """1 Hz motion samples 0..400s; mag 20 inside gameplay_ranges, else 1."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t", "mag"])
        for t in range(400):
            mag = 20.0 if any(a <= t <= b for a, b in gameplay_ranges) else 1.0
            w.writerow([f"{t:.3f}", f"{mag:.3f}"])


def _write_matches(path, beats):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["recap_line", "start", "end", "confidence", "matched_transcript"])
        w.writeheader()
        for s, e in beats:
            w.writerow({"recap_line": "x", "start": s, "end": e, "confidence": 0.5, "matched_transcript": ""})


def test_gameplay_beats_excluded_static_merged(tmp_path):
    motion = tmp_path / "motion.csv"
    matches = tmp_path / "matches.csv"
    _write_motion(motion, gameplay_ranges=[(95, 115)])
    # beat A (100-105) sits in gameplay -> no OCR needed
    # beats B (200-205) and C (210-215) are static -> OCR windows overlap -> merged
    _write_matches(matches, [(100, 105), (200, 205), (210, 215)])

    wins = needed_windows(str(matches), str(motion), OCR_BACK, OCR_FWD)

    assert len(wins) == 1
    a, b = wins[0]
    assert a == 200 - OCR_BACK       # 175.0
    assert b == 215 + OCR_FWD        # 295.0


def test_run_ocr_is_importable():
    from cutter.ocr_pass import run_ocr
    assert callable(run_ocr)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ocr_pass.py -v`
Expected: FAIL — `ImportError: cannot import name 'run_ocr'`

- [ ] **Step 4: Refactor**

In `cutter/ocr_pass.py`: delete the `PROJECT/VIDEO/MATCHES/MOTION/OUT` constant block; keep `SAMPLE_S`, `OCR_WIDTH`, `MIN_CONF`, `MOVE_THRESH`, `MIN_MOVING_FRAC`, `CLIP_BACK`, `CLIP_FWD`, `OCR_BACK`, `OCR_FWD` and `needed_windows` exactly as they are. Replace `main()` with `run_ocr` + a thin `main()`:

```python
def run_ocr(video, matches, motion, out, sample=SAMPLE_S, full=False):
    """Pipeline stage: OCR on-screen text in the windows that need it."""
    if full:
        windows = [(0.0, 1e9)]
    else:
        windows = needed_windows(matches, motion, OCR_BACK, OCR_FWD)
        total = sum(b - a for a, b in windows)
        print(f"{len(windows)} windows to OCR, ~{total/60:.1f} min of video. "
              f"~{int(total/sample)} frames.", flush=True)

    ocr = RapidOCR()
    container = av.open(str(video))
    stream = container.streams.video[0]
    tb = stream.time_base
    rows, done = [], 0
    for a, b in windows:
        if not full:
            container.seek(int(a / tb), stream=stream, backward=True)
        last_t = -1e9
        for frame in container.decode(stream):
            t = float(frame.pts * tb) if frame.pts is not None else None
            if t is None:
                continue
            if t < a:
                continue
            if t > b:
                break
            if t - last_t < sample:
                continue
            last_t = t
            h = int(frame.height * OCR_WIDTH / frame.width)
            img = frame.reformat(width=OCR_WIDTH, height=h, format="rgb24").to_ndarray()
            res, _ = ocr(img, use_cls=False)
            texts = [txt for _, txt, conf in (res or []) if conf >= MIN_CONF]
            rows.append((round(t, 1), " ".join(texts).replace("\n", " ")))
            done += 1
            if done % 10 == 0:
                print(f"  {done} frames | {t:6.0f}s | {(' '.join(texts))[:55]}", flush=True)
    container.close()

    rows.sort()
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t", "text"])
        w.writerows(rows)
    print(f"Wrote {out} ({len(rows)} frames OCR'd)", flush=True)


def main():
    p = argparse.ArgumentParser(description="Targeted on-screen-text OCR pass")
    p.add_argument("--video", required=True)
    p.add_argument("--matches", required=True)
    p.add_argument("--motion", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--sample", type=float, default=SAMPLE_S)
    p.add_argument("--full", action="store_true", help="OCR the whole video, not just beat windows")
    args = p.parse_args()
    run_ocr(args.video, args.matches, args.motion, args.out, args.sample, args.full)
```

Also update the module docstring's usage line to `python -m cutter.ocr_pass --video ... --matches ... --motion ... --out ...`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_ocr_pass.py -v`
Expected: 2 PASS

- [ ] **Step 6: Commit**

```powershell
git add -A
git commit -m "refactor: move ocr_pass into package, extract run_ocr" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: Move hybrid snapper into package as cutter/snap.py

**Files:**
- Move: `snap_visual.py` -> `cutter/snap.py` (via `git mv`)
- Modify: `cutter/snap.py`
- Test: `tests/test_snap.py`

**Interfaces:**
- Consumes: `work\matches.csv`, `work\motion.csv`, `work\ocr.csv` file formats produced by Tasks 7-9.
- Produces: `run_snap(matches, motion, ocr, out, min_conf=0.15, clip_len=9.0, move_thresh=6.0, min_moving_frac=0.55) -> None` writing `out\cuts.csv`; pure `best_window(...)`, `best_ocr(...)`, `beat_terms(...)` unchanged and importable.

- [ ] **Step 1: Move the file**

```powershell
git mv snap_visual.py cutter/snap.py
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_snap.py
import csv
import numpy as np
from cutter.snap import best_window, best_ocr, beat_terms


def test_best_window_prefers_the_moving_span():
    times = np.arange(0.0, 60.0, 1.0)
    mags = np.where((times >= 30) & (times < 40), 20.0, 1.0)
    # matched window 25-30; search allows [23, 34]; the latest slide start (25)
    # overlaps the moving region most
    a, frac, mean_mag = best_window(times, mags, 25.0, 30.0, 9.0, 2.0, 4.0, 6.0)
    assert a == 25.0
    assert frac > 0.3


def test_best_ocr_prefers_entity_hits():
    rows = [
        (10.0, "signalsearchremielle", "SIGNAL SEARCH REMIELLE"),
        (12.0, "somethingelse", "SOMETHING ELSE"),
    ]
    got = best_ocr(rows, 11.0, 12.0, ents=["Remielle"], kws=["banners"], back=25.0, fwd=80.0)
    t, ent_hits, kw_hits, raw = got
    assert t == 10.0 and ent_hits == 1


def test_beat_terms_extracts_entities_not_stopwords():
    ents, kws = beat_terms("For the banners, Remielle is up first.")
    assert "Remielle" in ents
    assert "the" not in kws


def test_run_snap_gameplay_ocr_weak_tiers(tmp_path):
    from cutter.snap import run_snap
    # motion: 1 Hz 0..400, moving only 95-115
    motion = tmp_path / "motion.csv"
    with open(motion, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t", "mag"])
        for t in range(400):
            w.writerow([f"{t:.3f}", "20.000" if 95 <= t <= 115 else "1.000"])
    # ocr: one frame at 205s showing REMIELLE
    ocr = tmp_path / "ocr.csv"
    ocr.write_text('t,text\n205.0,"SIGNAL SEARCH REMIELLE"\n', encoding="utf-8")
    # matches: beat1 in gameplay region, beat2 static + OCR-able, beat3 nothing
    matches = tmp_path / "matches.csv"
    with open(matches, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["recap_line", "start", "end", "confidence", "matched_transcript"])
        w.writeheader()
        w.writerow({"recap_line": "Combat gameplay showcase here", "start": 100, "end": 105, "confidence": 0.6, "matched_transcript": ""})
        w.writerow({"recap_line": "For the banners, Remielle is up first", "start": 200, "end": 205, "confidence": 0.6, "matched_transcript": ""})
        w.writerow({"recap_line": "Miscellaneous closing chatter", "start": 300, "end": 305, "confidence": 0.6, "matched_transcript": ""})
    out = tmp_path / "cuts.csv"

    run_snap(matches, motion, ocr, out)

    with open(out, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    assert rows[0]["matched_transcript"].startswith("gameplay")
    assert rows[1]["matched_transcript"].startswith("ocr[")
    assert rows[2]["matched_transcript"].startswith("weak")


def test_run_snap_respects_min_conf(tmp_path):
    from cutter.snap import run_snap
    motion = tmp_path / "motion.csv"
    motion.write_text("t,mag\n0.000,1.000\n1.000,1.000\n", encoding="utf-8")
    ocr = tmp_path / "ocr.csv"
    ocr.write_text("t,text\n", encoding="utf-8")
    matches = tmp_path / "matches.csv"
    matches.write_text(
        'recap_line,start,end,confidence,matched_transcript\nlow,0,1,0.05,\n',
        encoding="utf-8")
    out = tmp_path / "cuts.csv"
    run_snap(matches, motion, ocr, out, min_conf=0.15)
    with open(out, newline="", encoding="utf-8") as f:
        assert list(csv.DictReader(f)) == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_snap.py -v`
Expected: the pure-function tests may PASS; `run_snap` tests FAIL with `ImportError: cannot import name 'run_snap'`

- [ ] **Step 4: Refactor**

In `cutter/snap.py`: delete the `PROJECT/MATCHES/MOTION/OCR/OUT` constants. Keep `CLIP_LEN`, `MIN_CONF`, `MOVE_THRESH`, `MIN_MOVING_FRAC`, `BACK`, `FWD`, `OCR_BACK`, `OCR_FWD`, `STOP`, `load_motion`, `load_ocr`, `best_window`, `beat_terms`, `best_ocr` unchanged. Replace `main()` with:

```python
def run_snap(matches, motion, ocr, out, min_conf=MIN_CONF, clip_len=CLIP_LEN,
             move_thresh=MOVE_THRESH, min_moving_frac=MIN_MOVING_FRAC):
    """Pipeline stage: pick the exact cut span per beat (gameplay > OCR > weak)."""
    times, mags = load_motion(motion)
    ocr_rows = load_ocr(ocr)
    with open(matches, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    out_rows, n_game, n_ocr, n_weak = [], 0, 0, 0
    for r in rows:
        try:
            conf, s, e = float(r["confidence"]), float(r["start"]), float(r["end"])
        except (KeyError, ValueError):
            continue
        if conf < min_conf:
            continue
        dur = min(clip_len, (e - s) + BACK + FWD)
        ents, kws = beat_terms(r["recap_line"])

        gm = best_window(times, mags, s, e, dur, BACK, FWD, move_thresh)
        if gm and gm[1] >= min_moving_frac:
            ws = gm[0]
            tier = f"gameplay frac={gm[1]:.2f}"
            n_game += 1
        else:
            oc = best_ocr(ocr_rows, s, e, ents, kws, OCR_BACK, OCR_FWD)
            if oc and oc[1] >= 1:                       # >=1 named entity on screen
                ws = max(0.0, oc[0] - 1.0)
                tier = f"ocr[{oc[1]}e/{oc[2]}k]@{oc[0]:.0f}s: {oc[3][:45]}"
                n_ocr += 1
            else:
                ws = gm[0] if gm else s                 # least-static fallback
                tier = f"weak frac={gm[1]:.2f}" if gm else "weak"
                n_weak += 1

        out_rows.append({
            "recap_line": r["recap_line"], "start": f"{ws:.1f}", "end": f"{ws + dur:.1f}",
            "confidence": r["confidence"], "matched_transcript": tier,
        })
        print(f"[{tier[:60]:<60}] {r['recap_line'][:40]}")

    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["recap_line", "start", "end", "confidence", "matched_transcript"])
        w.writeheader()
        w.writerows(out_rows)
    print(f"\n{n_game} gameplay, {n_ocr} OCR-matched, {n_weak} weak. Wrote {out} ({len(out_rows)} cuts).")


def main():
    p = argparse.ArgumentParser(description="Hybrid gameplay+OCR visual matcher")
    p.add_argument("--matches", required=True)
    p.add_argument("--motion", required=True)
    p.add_argument("--ocr", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--min-conf", type=float, default=MIN_CONF)
    args = p.parse_args()
    run_snap(args.matches, args.motion, args.ocr, args.out, args.min_conf)
```

Note: `load_motion` uses `np.loadtxt`, which needs at least 2 data rows to stay 2-D; test fixtures already provide that. Also update the docstring usage line to `python -m cutter.snap --matches ... --motion ... --ocr ... --out ...`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_snap.py -v`
Expected: 6 PASS

- [ ] **Step 6: Commit**

```powershell
git add -A
git commit -m "refactor: move snap_visual into package as snap, extract run_snap" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: SRT writer

**Files:**
- Create: `cutter/srt.py`, `tests/test_srt.py`

**Interfaces:**
- Consumes: `work\matches.csv` format (`recap_line,start,end,confidence,matched_transcript`).
- Produces: `fmt_ts(sec: float) -> str` (`HH:MM:SS,mmm`); `write_srt(matches_csv: Path, out_srt: Path) -> int` (returns block count; blocks sorted chronologically).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_srt.py
from cutter.srt import fmt_ts, write_srt


def test_fmt_ts():
    assert fmt_ts(0) == "00:00:00,000"
    assert fmt_ts(3671.25) == "01:01:11,250"
    assert fmt_ts(59.9999) == "00:01:00,000"   # millisecond carry


def test_write_srt_sorted_blocks(tmp_path):
    matches = tmp_path / "matches.csv"
    matches.write_text(
        "recap_line,start,end,confidence,matched_transcript\n"
        "Second spoken beat,100.0,105.0,0.5,\n"
        "First spoken beat,10.0,15.0,0.5,\n",
        encoding="utf-8")
    out = tmp_path / "recap.srt"
    n = write_srt(matches, out)
    assert n == 2
    text = out.read_text(encoding="utf-8")
    assert text.startswith("1\n00:00:10,000 --> 00:00:15,000\nFirst spoken beat\n\n2\n")
    assert "00:01:40,000 --> 00:01:45,000\nSecond spoken beat" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_srt.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# cutter/srt.py
"""Deliverable: out\\recap.srt -- the recap narration as chronological subtitles."""
import csv
from pathlib import Path


def fmt_ts(sec: float) -> str:
    ms = round(sec * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(matches_csv: Path, out_srt: Path) -> int:
    with open(matches_csv, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("start")]
    rows.sort(key=lambda r: float(r["start"]))
    blocks = []
    for i, r in enumerate(rows, 1):
        blocks.append(f"{i}\n{fmt_ts(float(r['start']))} --> {fmt_ts(float(r['end']))}\n{r['recap_line']}\n")
    out_srt.parent.mkdir(parents=True, exist_ok=True)
    out_srt.write_text("\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8")
    print(f"[srt] {len(blocks)} blocks -> {out_srt}")
    return len(blocks)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_srt.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```powershell
git add cutter/srt.py tests/test_srt.py
git commit -m "feat: srt deliverable from matches" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 12: Pipeline orchestrator (cache-skip + last_job.txt)

**Files:**
- Create: `cutter/pipeline.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `Job`, `Config`, and the `run_*` functions from Tasks 4-11: `beatify.run_beatify(job)`, `transcribe.run_transcribe(video, out_json, model, device)`, `match_onnx.run_match(transcript, beats, out, window_segments, stride)`, `motion.run_motion(video, cache)`, `ocr_pass.run_ocr(video, matches, motion, out, sample)`, `snap.run_snap(matches, motion, ocr, out, min_conf, clip_len, move_thresh, min_moving_frac)`, `srt.write_srt(matches, srt)`.
- Produces:
  - `stage_table(job: Job, cfg: Config) -> list[tuple[str, Path, Callable[[], None]]]` — ordered `(name, output, fn)`.
  - `run_all(job: Job, cfg: Config) -> None` — validates inputs, runs every stage with cache-skip, then `write_last_job`.
  - `run_stage(job: Job, cfg: Config, name: str) -> None` — force-reruns one stage by name (`beatify|transcribe|match|motion|ocr|cut|srt`).
  - `write_last_job(cuts_path: Path) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pipeline.py
import json
import os
import pytest
from cutter import pipeline
from cutter.config import Config
from cutter.jobs import Job


@pytest.fixture
def job(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))  # no Resolve dir -> warn path
    root = tmp_path / "j"
    root.mkdir()
    (root / "vod.mp4").write_bytes(b"\x00" * 64)
    (root / "recap.txt").write_text("One thing. Two things.", encoding="utf-8")
    return Job(root=root)


def _fake_stages(monkeypatch, calls):
    """Replace every heavy run_* with a recorder that creates its output file."""
    import cutter.beatify, cutter.transcribe, cutter.match_onnx
    import cutter.motion, cutter.ocr_pass, cutter.snap, cutter.srt

    def patch(mod, attr, name, output_of):
        def wrapper(*a, **k):
            calls.append(name)
            p = output_of(a)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x", encoding="utf-8")
        monkeypatch.setattr(mod, attr, wrapper)

    patch(cutter.beatify, "run_beatify", "beatify", lambda a: a[0].beats)
    patch(cutter.transcribe, "run_transcribe", "transcribe", lambda a: a[1])
    patch(cutter.match_onnx, "run_match", "match", lambda a: a[2])
    patch(cutter.motion, "run_motion", "motion", lambda a: a[1])
    patch(cutter.ocr_pass, "run_ocr", "ocr", lambda a: a[3])
    patch(cutter.snap, "run_snap", "cut", lambda a: a[3])
    patch(cutter.srt, "write_srt", "srt", lambda a: a[1])


def test_run_all_runs_stages_in_order_then_skips(job, monkeypatch, capsys):
    calls = []
    _fake_stages(monkeypatch, calls)
    cfg = Config()

    pipeline.run_all(job, cfg)
    assert calls == ["beatify", "transcribe", "match", "motion", "ocr", "cut", "srt"]

    calls.clear()
    pipeline.run_all(job, cfg)          # everything cached now
    assert calls == []
    assert "skip" in capsys.readouterr().out


def test_run_stage_forces_rerun(job, monkeypatch):
    calls = []
    _fake_stages(monkeypatch, calls)
    cfg = Config()
    pipeline.run_all(job, cfg)
    calls.clear()
    pipeline.run_stage(job, cfg, "match")
    assert calls == ["match"]


def test_run_stage_unknown_name(job):
    with pytest.raises(SystemExit, match="Unknown stage"):
        pipeline.run_stage(job, Config(), "florp")


def test_run_all_validates_before_work(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    root = tmp_path / "empty"
    root.mkdir()
    (root / "recap.txt").write_text("Hi there.", encoding="utf-8")
    with pytest.raises(SystemExit, match="No .mp4"):
        pipeline.run_all(Job(root=root), Config())


def test_write_last_job(tmp_path, monkeypatch):
    utility = tmp_path / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Fusion" / "Scripts" / "Utility"
    utility.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cuts = tmp_path / "j" / "out" / "cuts.csv"
    cuts.parent.mkdir(parents=True)
    cuts.write_text("x", encoding="utf-8")
    pipeline.write_last_job(cuts)
    assert (utility / "last_job.txt").read_text(encoding="utf-8") == str(cuts.resolve())


def test_write_last_job_no_resolve_is_warning_not_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("APPDATA", str(tmp_path))   # Utility dir absent
    cuts = tmp_path / "cuts.csv"
    cuts.write_text("x", encoding="utf-8")
    pipeline.write_last_job(cuts)                   # must not raise
    assert "Resolve" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cutter.pipeline'`

- [ ] **Step 3: Implement**

```python
# cutter/pipeline.py
"""Orchestrates the stages. Each stage skips when its output file already
exists (delete the file to force a rebuild); per-stage CLI commands force-rerun."""
import os
from pathlib import Path
from typing import Callable

from .config import Config
from .jobs import Job, validate_inputs

STAGE_NAMES = ["beatify", "transcribe", "match", "motion", "ocr", "cut", "srt"]


def stage_table(job: Job, cfg: Config) -> list[tuple[str, Path, Callable[[], None]]]:
    # Imports are lazy so `cutter --help` etc. never pay for av/onnxruntime.
    from . import beatify, match_onnx, motion, ocr_pass, snap, srt, transcribe

    vod = job.find_vod()
    return [
        ("beatify", job.beats, lambda: beatify.run_beatify(job)),
        ("transcribe", job.transcript,
         lambda: transcribe.run_transcribe(vod, job.transcript, cfg.model, cfg.device)),
        ("match", job.matches,
         lambda: match_onnx.run_match(job.transcript, job.beats, job.matches,
                                      cfg.window_segments, cfg.stride)),
        ("motion", job.motion, lambda: motion.run_motion(vod, job.motion)),
        ("ocr", job.ocr,
         lambda: ocr_pass.run_ocr(vod, job.matches, job.motion, job.ocr, cfg.ocr_sample)),
        ("cut", job.cuts,
         lambda: snap.run_snap(job.matches, job.motion, job.ocr, job.cuts,
                               cfg.min_conf, cfg.clip_len, cfg.move_thresh,
                               cfg.min_moving_frac)),
        ("srt", job.srt, lambda: srt.write_srt(job.matches, job.srt)),
    ]


def _run(name: str, output: Path, fn: Callable[[], None], force: bool) -> None:
    if output.exists() and not force:
        print(f"[skip] {name}: {output.name} exists (delete it to rebuild)")
        return
    print(f"[run ] {name}")
    fn()


def run_all(job: Job, cfg: Config) -> None:
    validate_inputs(job)          # fail early, before any slow work
    job.ensure_dirs()
    for name, output, fn in stage_table(job, cfg):
        _run(name, output, fn, force=False)
    write_last_job(job.cuts)
    print(f"\nDone. Deliverables in {job.out}")
    print("Next: open DaVinci Resolve, import the VOD onto a timeline, then "
          "Workspace > Scripts > resolve_cut")


def run_stage(job: Job, cfg: Config, name: str) -> None:
    validate_inputs(job)
    job.ensure_dirs()
    for n, output, fn in stage_table(job, cfg):
        if n == name:
            _run(n, output, fn, force=True)
            return
    raise SystemExit(f"Unknown stage: {name}. Stages: {', '.join(STAGE_NAMES)}")


def write_last_job(cuts_path: Path) -> None:
    utility = (Path(os.environ["APPDATA"]) / "Blackmagic Design" / "DaVinci Resolve"
               / "Support" / "Fusion" / "Scripts" / "Utility")
    if not utility.is_dir():
        print("[warn] DaVinci Resolve scripts folder not found; skipped last_job.txt "
              "(install Resolve, then re-run)")
        return
    (utility / "last_job.txt").write_text(str(cuts_path.resolve()), encoding="utf-8")
    print(f"[ok  ] Resolve will cut: {cuts_path}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_pipeline.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```powershell
git add cutter/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline orchestrator with cache-skip and last_job handoff" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 13: CLI (run / new / per-stage subcommands)

**Files:**
- Create: `cutter/cli.py`, `cutter/__main__.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_config`, `jobs_root_path` (Task 2); `resolve_job` (Task 3); `pipeline.run_all`, `pipeline.run_stage`, `pipeline.STAGE_NAMES` (Task 12).
- Produces: `main(argv: list[str] | None = None) -> None`; console script `cutter` (wired in Task 1's pyproject); `python -m cutter` entry.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli.py
import pytest
from cutter import cli, pipeline


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    root = tmp_path / "Documents" / "CutterJobs"
    root.mkdir(parents=True)
    return root


def test_new_scaffolds_job(env):
    cli.main(["new", "myjob"])
    assert (env / "myjob" / "recap.txt").is_file()
    assert "paragraph" in (env / "myjob" / "recap.txt").read_text(encoding="utf-8")


def test_new_refuses_existing(env):
    cli.main(["new", "myjob"])
    with pytest.raises(SystemExit, match="already exists"):
        cli.main(["new", "myjob"])


def test_run_resolves_job_by_name(env, monkeypatch):
    (env / "myjob").mkdir()
    (env / "myjob" / "vod.mp4").write_bytes(b"\x00")
    (env / "myjob" / "recap.txt").write_text("A thing. Another.", encoding="utf-8")
    seen = {}
    monkeypatch.setattr(pipeline, "run_all", lambda job, cfg: seen.update(root=job.root))
    cli.main(["run", "myjob"])
    assert seen["root"] == env / "myjob"


def test_stage_subcommand_dispatches(env, monkeypatch):
    (env / "myjob").mkdir()
    (env / "myjob" / "vod.mp4").write_bytes(b"\x00")
    (env / "myjob" / "recap.txt").write_text("A thing.", encoding="utf-8")
    seen = {}
    monkeypatch.setattr(pipeline, "run_stage", lambda job, cfg, name: seen.update(name=name))
    cli.main(["match", "myjob"])
    assert seen["name"] == "match"


def test_missing_job_fails_plainly(env):
    with pytest.raises(SystemExit, match="Job folder not found"):
        cli.main(["run", "ghost"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cli.py -v`
Expected: FAIL with `ImportError` (no `cutter.cli`)

- [ ] **Step 3: Implement**

```python
# cutter/cli.py
"""The `cutter` command.

    cutter new <job>       scaffold a job folder under the jobs root
    cutter run <job>       run the whole pipeline (cached stages skip)
    cutter <stage> <job>   force-rerun one stage: beatify | transcribe | match |
                           motion | ocr | cut | srt
"""
import argparse
from pathlib import Path

from . import pipeline
from .config import jobs_root_path, load_config
from .jobs import resolve_job

RECAP_TEMPLATE = (
    "Replace this text with your recap script: one flowing paragraph of prose "
    "describing everything the video should cover, in the order you want it "
    "covered. The tool splits it into beats automatically.\n"
)


def cmd_new(root: Path, name: str) -> None:
    d = root / name
    if d.exists():
        raise SystemExit(f"Job already exists: {d}")
    d.mkdir(parents=True)
    (d / "recap.txt").write_text(RECAP_TEMPLATE, encoding="utf-8")
    print(f"Created {d}")
    print(f"Next: copy your VOD (.mp4) into that folder, rewrite recap.txt, then run:")
    print(f"    cutter run {name}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="cutter", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ["new", "run", *pipeline.STAGE_NAMES]:
        sp = sub.add_parser(name)
        sp.add_argument("job", help="job folder name (under the jobs root) or absolute path")
    args = p.parse_args(argv)

    root = jobs_root_path(load_config())
    if args.cmd == "new":
        cmd_new(root, args.job)
        return

    job = resolve_job(args.job, root)
    cfg = load_config(job.root)
    if args.cmd == "run":
        pipeline.run_all(job, cfg)
    else:
        pipeline.run_stage(job, cfg, args.cmd)
```

```python
# cutter/__main__.py
from .cli import main

main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cli.py -v`
Expected: 5 PASS

- [ ] **Step 5: Smoke the console script**

Run: `.venv\Scripts\cutter.exe --help`
Expected: usage text listing `new`, `run`, and the seven stage subcommands. (If `cutter.exe` is missing, re-run `.venv\Scripts\python.exe -m pip install -e .` once.)

- [ ] **Step 6: Run the whole suite**

Run: `.venv\Scripts\python.exe -m pytest tests -v`
Expected: all tests pass, e2e deselected.

- [ ] **Step 7: Commit**

```powershell
git add cutter/cli.py cutter/__main__.py tests/test_cli.py
git commit -m "feat: cutter CLI with new/run/per-stage subcommands" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 14: resolve_cut.lua reads last_job.txt (+ jobs-root fallback)

**Files:**
- Modify: `resolve_cut.lua:16-21` (the CONFIG block) and its header comment (lines 1-14).

**Interfaces:**
- Consumes: `last_job.txt` written by `pipeline.write_last_job` (absolute path to a `cuts.csv`, single line, UTF-8); job layout `<jobs root>\<job>\out\cuts.csv`.
- Produces: nothing new downstream — the rest of the Lua (CSV parse, timeline build) is untouched.

- [ ] **Step 1: Replace the CONFIG block**

Replace lines 16-21 of `resolve_cut.lua`:

```lua
-- ===================== CONFIG =====================
local PAD          = 1.0            -- seconds of padding added before start / after end
local MIN_CONF     = 0.15           -- skip matches below this confidence
-- =================================================

-- ---- locate the cuts.csv written by `cutter run` ----
local function readLastJob()
  local appdata = os.getenv("APPDATA")
  if not appdata then return nil end
  local f = io.open(appdata .. "\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Utility\\last_job.txt", "r")
  if not f then return nil end
  local p = f:read("*l")
  f:close()
  if p and #p > 0 then return p end
  return nil
end

local function newestCutsInJobsRoot()
  -- fallback: newest cuts.csv anywhere under Documents\CutterJobs
  local cmd = [[powershell -NoProfile -Command "Get-ChildItem (Join-Path $env:USERPROFILE 'Documents\CutterJobs') -Recurse -Filter cuts.csv -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName"]]
  local h = io.popen(cmd)
  if not h then return nil end
  local out = h:read("*l")
  h:close()
  if out and #out > 0 then return out end
  return nil
end

local CSV = readLastJob() or newestCutsInJobsRoot()
if not CSV then
  print("ERROR: no cuts.csv found. Run 'cutter run <job>' first.")
  return
end
local probe = io.open(CSV, "r")
if not probe then
  print("ERROR: cuts file listed in last_job.txt is missing: " .. CSV)
  return
end
probe:close()

-- timeline named after the job folder: ...\myjob\out\cuts.csv -> "myjob Recap"
local jobName = CSV:match("([^\\]+)\\out\\cuts%.csv$") or "Cutter"
local TIMELINE_NAME = jobName .. " Recap"
print("Cutting from: " .. CSV .. "  ->  timeline '" .. TIMELINE_NAME .. "'")
```

Also update the header comment (lines 1-14): replace the mention of `matches.csv` and the fixed timeline name with "reads the cuts.csv of the last `cutter run` (via last_job.txt), or the newest job under Documents\CutterJobs; timeline is named `<job> Recap`."

- [ ] **Step 2: Re-deploy to Resolve's menu**

Run: `powershell -File D:\CutterDavinci\install_resolve_script.ps1`
Expected: `Installed: ...\Scripts\Utility\resolve_cut.lua`

- [ ] **Step 3: Manual verification (no Lua unit harness exists)**

1. Create `%APPDATA%\...\Scripts\Utility\last_job.txt` containing `E:\Videos\VersionRecaps\ZZZ3.1\output\cuts_gameplay.csv` — a real, existing cuts file from the old project (the CSV format is identical).
2. Open Resolve with the ZZZ3.1 project, VOD on a timeline.
3. Workspace ▸ Scripts ▸ resolve_cut.
Expected: console prints `Cutting from: E:\...cuts_gameplay.csv` and builds a timeline (named "Cutter Recap" since the old path doesn't match `\out\cuts.csv` — that's the fallback name working as designed).
4. Delete `last_job.txt`, run the script again with no `Documents\CutterJobs` folder.
Expected: `ERROR: no cuts.csv found. Run 'cutter run <job>' first.`

- [ ] **Step 4: Commit**

```powershell
git add resolve_cut.lua
git commit -m "feat: resolve_cut.lua auto-finds cuts via last_job.txt" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 15: End-to-end fixture test (marked e2e)

**Files:**
- Create: `tests/test_e2e.py`

**Interfaces:**
- Consumes: the full CLI (`cutter.cli.main`) and every real stage except transcription (pre-seeded transcript exercises the documented cache-skip); the real ONNX matcher model (~490 MB, already in `D:\CutterDavinci\huggingface`).

- [ ] **Step 1: Write the test**

```python
# tests/test_e2e.py
"""Full-pipeline test on a generated 20s clip. Run manually:

    .venv\\Scripts\\python.exe -m pytest tests/test_e2e.py -m e2e -v

Needs the ONNX matcher model (auto-downloads ~490 MB on first ever run;
already cached in this repo's huggingface/ folder)."""
import json
import numpy as np
import av
import pytest

pytestmark = pytest.mark.e2e


def make_video(path, dur=20, fps=8, w=160, h=90):
    container = av.open(str(path), "w")
    stream = container.add_stream("libx264", rate=fps)
    stream.width, stream.height, stream.pix_fmt = w, h, "yuv420p"
    rng = np.random.default_rng(0)
    for i in range(dur * fps):
        t = i / fps
        if t < 10:
            arr = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)   # motion
        else:
            arr = np.full((h, w, 3), 128, dtype=np.uint8)            # static
        frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
        for pkt in stream.encode(frame):
            container.mux(pkt)
    for pkt in stream.encode():
        container.mux(pkt)
    container.close()


def test_full_pipeline_on_synthetic_job(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))     # no Resolve -> warn only
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    job = tmp_path / "Documents" / "CutterJobs" / "e2e"
    (job / "work").mkdir(parents=True)

    make_video(job / "vod.mp4")
    (job / "recap.txt").write_text(
        "First we look at the exciting action scene. Then we see the calm menu screen.",
        encoding="utf-8")
    # Pre-seed the transcript: exercises cache-skip and avoids a Whisper run.
    (job / "work" / "transcript.json").write_text(json.dumps([
        {"start": 0.0, "end": 5.0, "text": "here is the exciting action scene"},
        {"start": 5.0, "end": 10.0, "text": "so much action happening on screen"},
        {"start": 10.0, "end": 15.0, "text": "now we look at the calm menu screen"},
        {"start": 15.0, "end": 20.0, "text": "a quiet menu with options"},
    ]), encoding="utf-8")

    from cutter.cli import main
    main(["run", "e2e"])

    cuts = (job / "out" / "cuts.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(cuts) == 3                       # header + 2 beats
    assert (job / "out" / "recap.srt").is_file()
    assert (job / "work" / "beats.txt").read_text(encoding="utf-8").count("\n") == 2
```

- [ ] **Step 2: Confirm it is excluded by default**

Run: `.venv\Scripts\python.exe -m pytest tests -v`
Expected: `test_e2e.py` shows as **deselected**, everything else passes.

- [ ] **Step 3: Run it for real**

Run: `.venv\Scripts\python.exe -m pytest tests/test_e2e.py -m e2e -v`
Expected: 1 PASS in under ~2 minutes (ONNX embed + motion decode of a 20s clip; no Whisper). If the matcher places both beats in one window, that's fine — the assertion only counts rows.

- [ ] **Step 4: Commit**

```powershell
git add tests/test_e2e.py
git commit -m "test: end-to-end pipeline fixture on synthetic job" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 16: Documentation for the new workflow

**Files:**
- Modify: `HOW_IT_WORKS.md` (the "Project layout" and "Run it end to end" sections), `README.md` (top pointer note).

- [ ] **Step 1: Update HOW_IT_WORKS.md**

Replace the **Project layout** section's data-folder block (the part describing `E:\Videos\VersionRecaps\ZZZ3.1` and `PROJECT` constants) with:

```markdown
**Data** — one folder per VOD under the jobs root (`Documents\CutterJobs\`,
override with `jobs_root` in `%APPDATA%\cutter\config.toml`):
```
Documents\CutterJobs\myjob\
  vod.mp4          your stream (first .mp4 in the folder is used)
  recap.txt        your recap: ONE prose paragraph, no timestamps, no beats
  cutter.toml      optional per-job knobs (model, device, min_conf, ...)
  work\            caches: beats.txt, transcript.json, matches.csv, motion.csv, ocr.csv
  out\             deliverables: cuts.csv, recap.srt
```
The old `E:\Videos\VersionRecaps\ZZZ3.1` layout predates the CLI and stays as-is
for reference.
```

Replace the **Run it end to end** section with:

```markdown
## Run it end to end

```powershell
# one-time
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -e .
powershell -File install_resolve_script.ps1     # adds Workspace > Scripts > resolve_cut

# per VOD
.venv\Scripts\cutter new myjob                  # scaffolds Documents\CutterJobs\myjob
#   -> copy your VOD .mp4 in, write recap.txt as one prose paragraph
.venv\Scripts\cutter run myjob                  # beatify -> transcribe -> match -> motion -> ocr -> cut -> srt
# then in DaVinci Resolve: import the VOD onto a timeline,
# Workspace > Scripts > resolve_cut  ->  a "myjob Recap" timeline appears
```

Stages skip when their output exists — delete a file in `work\` to rebuild it.
`work\beats.txt` is editable: tweak the beat split, delete `work\matches.csv`
and everything after it, and re-run. Force one stage with
`cutter <stage> myjob` (stages: beatify transcribe match motion ocr cut srt).
No GPU? `device = "auto"` (the default) falls back to CPU automatically.
```

Also update the **Pipeline** diagram near the top: `recap.txt (prose) -> beatify -> beats.txt` feeds the matcher, and script names gain their `cutter/` paths.

- [ ] **Step 2: Update README.md**

Add directly under the existing note at the top:

```markdown
> **Update (Jul 2026):** the pipeline is now a reusable CLI — `cutter new <job>`,
> `cutter run <job>` — over per-VOD job folders in `Documents\CutterJobs\`.
> See HOW_IT_WORKS.md. The per-script commands below still work but are superseded.
```

- [ ] **Step 3: Verify docs match reality**

Run: `.venv\Scripts\cutter --help`
Compare the listed subcommands against what the docs claim. Skim both edited sections once for stale paths (`E:\Videos`, `snap_gameplay.py`, `match_recap_onnx.py` should no longer appear in the *active* instructions).

- [ ] **Step 4: Run the full suite one last time**

Run: `.venv\Scripts\python.exe -m pytest tests -v`
Expected: all pass, e2e deselected.

- [ ] **Step 5: Commit**

```powershell
git add HOW_IT_WORKS.md README.md
git commit -m "docs: document the cutter CLI job workflow" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
