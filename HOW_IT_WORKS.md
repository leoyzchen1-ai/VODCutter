# How it works

This turns a raw livestream VOD + a prose recap script into an automatically
cut timeline in DaVinci Resolve (free edition).

## Does it need Claude / the internet?

**No.** Everything runs locally on your machine. There is no Claude, no API
key, and no network access at runtime. The only "AI" involved is a handful of
**open-source models that run on your own GPU/CPU** (none are Claude/Anthropic).
They download once from Hugging Face, then are cached and run offline.

Caveat: *running* the pipeline is automatic, but the matching is approximate, so
getting a clean result still benefits from a human reviewing frames and nudging
a few thresholds.

## Pipeline

Each script writes a file the next one reads:

```
recap.txt ─▶ cutter/snap.py (beatify) ─▶ beats.txt ┐
                                                      │
VOD.mp4 ─▶ cutter/transcribe.py ──────────▶ transcript.json  (what was said, timestamped)
                                           │
beats.txt ───────────────────────────────┤
transcript.json ──────────────────────────┴▶ cutter/match_onnx.py ─▶ matches.csv  (which moment each beat is about)
VOD.mp4 ─▶ cutter/ocr_pass.py ────────────▶ ocr.csv           (on-screen text every 3s)
VOD.mp4 ─▶ cutter/motion.py ──────────────▶ motion.csv        (how much the picture moves)
matches + motion + ocr ─▶ cutter/snap.py ─▶ cuts.csv (exact start/end per beat)
cuts.csv ─▶ resolve_cut.lua ─▶ "Recap" timeline in DaVinci
```

### 1. `transcribe.py` — speech to text
Runs Whisper (via `faster-whisper`) on the audio to produce timestamped text.
Use the native language of the stream (here: Chinese) for accuracy.
Output: `transcript.json`.

### 2. `match_recap_onnx.py` — when is each script line talked about?
Embeds every recap sentence and every chunk of the transcript into vectors with
a **multilingual** model, then picks the transcript chunk closest in meaning to
each recap line. Multilingual is the trick: an **English** script matches a
**Chinese** transcript by *meaning*, not shared words.
Output: `matches.csv` (each beat → a timestamp region).
(TF-IDF word-overlap variants — `match_recap.py`, `match_recap_semantic.py` —
are kept for reference; the ONNX one is torch-free and what we use.)

### 3. Reading the picture, not just the audio
The transcript only tells you when something is *spoken* — often the hosts on
the couch, not the gameplay they're describing. Two signals read the pixels:

- **`snap_gameplay.py` → `motion.csv`**: how much the frame changes every
  ¼ second. Gameplay moves a lot; a couch shot is nearly still. Finds the
  *gameplay* portion inside a beat's window.
- **`ocr_pass.py` → `ocr.csv`**: reads the **on-screen text** every 3s with
  RapidOCR. A banner literally says `SIGNAL SEARCH / REMIELLE`, so banner/event
  beats can jump to the exact frame whose text matches the beat.

### 4. `snap_visual.py` — the hybrid decision
For each beat: strong motion in its window → use that **gameplay** span;
otherwise a frame whose **OCR text** matches the beat's names → use that (the
banner/event screen); otherwise fall back to the least-static moment.
Output: `cuts_gameplay.csv` (precise start/end per beat, in script order).

### 5. `resolve_cut.lua` — assembly
Paste into DaVinci Resolve's Lua console (Workspace ▸ Console ▸ Lua). It reads
`cuts_gameplay.csv` and, via Resolve's scripting API, creates a new timeline and
appends each `[start → end]` segment of the VOD back to back. No manual cutting.

## Models and where they live

All open-source, all local. Downloaded once, then cached.

| Stage | Model | Size | Location |
|---|---|---|---|
| Transcribe | `Systran/faster-whisper-medium` | ~1.5 GB | `D:\CutterDavinci\huggingface\hub\` |
| Match | `Xenova/paraphrase-multilingual-MiniLM-L12-v2` (ONNX) | ~490 MB | `D:\CutterDavinci\huggingface\hub\` |
| OCR | RapidOCR (PP-OCRv4 det/rec/cls) | ~16 MB | bundled in `.venv\Lib\site-packages\rapidocr_onnxruntime\models\` |

The HF cache lives inside the repo folder instead of the default
`C:\Users\<you>\.cache\huggingface\` because the user env var
`HF_HOME=D:\CutterDavinci\huggingface` is set (and `huggingface/` is gitignored,
so it's never committed). New terminals pick this up automatically; anything
already open needs a restart to see it. To use the default `C:` location
instead, just clear `HF_HOME`.

(The torch build `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`,
~480 MB, was left over from an earlier attempt — blocked by Windows Smart App
Control and unused — and has been deleted.)

None of these are in the git repo (they sit in the HF cache and the venv). A
fresh clone re-downloads them on first run.

## Project layout

**Code** (`D:\CutterDavinci`, this repo) — active pipeline at the root,
superseded scripts in `legacy/`:
```
transcribe.py  match_recap_onnx.py  ocr_pass.py  snap_gameplay.py  snap_visual.py  resolve_cut.lua
legacy/   match_recap.py (TF-IDF)  match_recap_semantic.py (torch)  matches_to_srt.py
          resolve_markers.py  run_markers.ps1
```

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

## Gotchas
- Run the video/ML scripts with the **venv python via PowerShell**. Git Bash
  trips Windows Smart App Control on some native DLLs (torch, PyAV).
- `motion.csv` and `ocr.csv` are caches — delete them to force a rebuild.
- Matching is approximate. Review the cuts and tune `snap_visual.py` /
  `snap_gameplay.py` thresholds if a beat lands wrong.
