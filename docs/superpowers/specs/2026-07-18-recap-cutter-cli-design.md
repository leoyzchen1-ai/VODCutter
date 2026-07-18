# Recap Cutter — reusable per-VOD CLI (Phase 1)

**Date:** 2026-07-18
**Status:** Design approved, pending spec review
**Scope:** Phase 1 only — the parameterized CLI core. The bundled installer/.exe is
Phase 2 and gets its own spec once Phase 1 runs on a second real VOD.

## Problem

The pipeline (transcribe → match → OCR → motion → snap → Resolve cut) currently only
works on one hardcoded project. Every script carries a `PROJECT = ...\ZZZ3.1` constant
and `resolve_cut.lua` has a hardcoded `cuts_gameplay.csv` path. Cutting a *second* VOD
today means hand-editing five files. We want a workflow where a **semi-technical
customer** drops a VOD plus a prose recap into a job folder, runs one command, then
makes a single click in DaVinci Resolve to get a cut timeline.

## Users & decisions locked in brainstorming

- **Audience:** semi-technical customer — can install software and run one command or
  double-click a `.bat`, but must never edit Python or file paths.
- **Resolve step:** the command runs the whole AI pipeline; the customer opens Resolve,
  imports the VOD, and clicks **Workspace ▸ Scripts ▸ resolve_cut** once. Not headless.
- **Recap input:** the customer writes it. The tool stays fully local/offline — no LLM,
  no API, no network at runtime (models are the only downloads, cached once).
- **Recap form:** ONE flowing paragraph of prose, no beats. The tool splits it into
  beats itself (new Stage 0).
- **Packaging (end goal):** a bundled installer/.exe — **Phase 2**, not this spec.
- **Jobs location:** a single fixed jobs root, one subfolder per VOD.
- **Beat granularity:** one beat per sentence, with an editable intermediate for
  exceptions.

## Non-goals (explicitly out of scope for Phase 1)

- The bundled installer/.exe and model pre-fetch (Phase 2).
- Generating the recap for the customer (would require an LLM; rejected).
- Driving Resolve headlessly / auto-importing the VOD.
- Any change to the matching/OCR/motion algorithms themselves — only their plumbing
  (paths, config, orchestration) changes.

## Job model

A "job" is one self-contained folder under a fixed jobs root
(default `%USERPROFILE%\Documents\CutterJobs\`, overridable in global config):

```
Documents\CutterJobs\myjob\
  vod.mp4          # the stream (first *.mp4 used, or --vod NAME)
  recap.txt        # customer-written prose, ONE paragraph, no beats
  cutter.toml      # optional per-job config; defaults used if absent
  work\            # GENERATED caches: beats.txt, transcript.json, matches.csv,
                   #   motion.csv, ocr.csv
  out\             # GENERATED deliverables: cuts.csv, recap.srt
```

This replaces the old `source/ transcripts/ work/ output/` split and every `PROJECT`
constant. All paths are derived from the job folder; nothing is hardcoded.

## Stages

Each stage reads/writes files inside the job folder and **skips if its output cache
already exists** (delete the cache to force a rebuild). This makes `run` resumable and
cheap to re-invoke — unchanged from today's behavior for motion/ocr.

| Stage | Input | Output | Notes |
|---|---|---|---|
| 0. beatify | `recap.txt` | `work\beats.txt` | NEW. Prose paragraph → one beat per line. |
| 1. transcribe | `vod.mp4` | `work\transcript.json` | faster-whisper. |
| 2. match | beats + transcript | `work\matches.csv` | multilingual ONNX embeddings. |
| 3. motion | `vod.mp4` | `work\motion.csv` | per-frame motion. |
| 4. ocr | `vod.mp4` + matches | `work\ocr.csv` | RapidOCR, only beats that need text. |
| 5. snap | matches+motion+ocr | `out\cuts.csv` | hybrid gameplay/OCR decision. |
| (srt) | matches | `out\recap.srt` | subtitle deliverable. |

### Stage 0 — beatify (new)

Splits the prose `recap.txt` into beats using **rule-based, offline sentence-boundary
segmentation** (`pysbd`, MIT, no model download; handles abbreviations and decimals
like `3.1`, `1,600`, `Mr. Click`, `S-Rank`, `Soldier 0 Anby`). A regex splitter on
`.?!` is the fallback if `pysbd` is unavailable. Result: roughly one sentence per beat,
matching the shape of the existing hand-made `.beats.txt` (28 sentences → 28 beats).

`work\beats.txt` is a **reviewable, editable intermediate**: `run` regenerates it only
if absent, so the default is fully automatic, but a human can open it and merge/split/
delete beats before the expensive matching runs — the cheapest available lever on match
quality.

## CLI

Single entry point, `cutter`, with subcommands. Argument is a job folder name (resolved
under the jobs root) or an absolute path.

```
cutter run myjob         # Stage 0→5 + srt; what a customer uses
cutter beatify myjob      # individual stages, for tuning / re-running one
cutter transcribe myjob
cutter match myjob
cutter cut myjob          # the snap stage
cutter new myjob          # scaffolds an empty job folder with a recap.txt template
```

`run` is the customer path. The per-stage commands are for the operator when tuning
thresholds. `new` lowers the "where do I put things" friction for a semi-technical user.

## Configuration

`cutter.toml` in the job folder (optional) surfaces knobs currently buried as
constants: `min_conf`, `pad`, motion/OCR thresholds, whisper `model` size, and
`device`. A global config (jobs-root location, defaults) lives at
`%APPDATA%\cutter\config.toml`. Job config overrides global; both are optional.

**GPU→CPU fallback:** default `device = "auto"`. Try CUDA/float16; on any CUDA/cuDNN
error, fall back to CPU/int8 with a printed warning. Today's code assumes a CUDA GPU;
a customer's machine likely has none, so this must degrade gracefully rather than crash.

## Resolve handoff (the one click)

`resolve_cut.lua`'s hardcoded CSV path is removed. On a successful `cutter run`, the
tool writes the finished job's absolute `out\cuts.csv` path to `last_job.txt` stored
next to the installed menu script (in the Resolve `Scripts\Utility` folder). The menu
script reads `last_job.txt` and cuts the most recent job. If `last_job.txt` is missing,
it falls back to scanning the jobs root for the newest `out\cuts.csv`.

Flow for the customer: import VOD → drop on any timeline → **Workspace ▸ Scripts ▸
resolve_cut** → a new "Recap" timeline appears. The original timeline/VOD is untouched
(unchanged from today). Installing the menu script is a setup step (already scripted as
`install_resolve_script.ps1`; Phase 2's installer folds it in).

## Error handling

Fail loud and early, in plain English, **before** the slow work starts:

- Missing/empty `vod.mp4` or `recap.txt` → clear message naming the job folder.
- Unreadable/zero-length video → stop before transcription.
- `recap.txt` present but blank after trimming → stop at beatify.
- Resolve side: no project open / VOD not found → the existing Lua error messages,
  retained.

Each stage validates its inputs exist and are non-empty. Because outputs are cached, a
failed `run` is always safe to re-invoke.

## Testing

- **End-to-end fixture:** a tiny job (a few-second clip + a 2-sentence `recap.txt`)
  that runs `cutter run` through to `out\cuts.csv`. Guards the plumbing/paths.
- **Unit tests (no video, no Resolve):**
  - beatify: prose → beats on the tricky cases (`3.1`, `1,600`, `Mr. Click`,
    `S-Rank`, `Soldier 0 Anby`) — asserts they are NOT split.
  - CSV parse (the quote-aware parser reused by the Lua logic / Python side).
  - snap decision: given synthetic motion/ocr rows, the gameplay-vs-OCR-vs-fallback
    choice.
  - device selection: `auto` picks CPU when CUDA probe fails.

## Migration / mapping to current code

- `snap_gameplay.py`, `ocr_pass.py`, `snap_visual.py`, `match_recap_onnx.py`,
  `transcribe.py` → become stage functions taking a job path; `PROJECT` constants
  removed.
- New: `beatify` stage, `cutter` CLI entry point, job/config resolution module.
- `resolve_cut.lua` → read `last_job.txt` instead of a hardcoded CSV path.
- `legacy/` untouched.
- The existing `ZZZ3.1` data is not migrated; it stays where it is as reference.

## Open items deferred to Phase 2

- PyInstaller/Inno packaging of native ML deps (onnxruntime, ctranslate2, PyAV,
  RapidOCR).
- Shipping vs. first-run download of the ~2 GB models.
- One-click installer that also installs the Resolve menu script.
