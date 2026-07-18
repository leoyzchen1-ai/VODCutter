"""Orchestrates the stages. Each stage skips when its output file already
exists (delete the file to force a rebuild); per-stage CLI commands force-rerun."""
import os
from pathlib import Path
from typing import Callable

from .config import Config
from .jobs import Job, validate_inputs

STAGE_NAMES = ["beatify", "transcribe", "match", "motion", "ocr", "cut", "srt"]


def _prerequisites(job: Job) -> dict[str, list[Path]]:
    return {
        "beatify": [],
        "transcribe": [],
        "match": [job.transcript, job.beats],
        "motion": [],
        "ocr": [job.matches, job.motion],
        "cut": [job.matches, job.motion, job.ocr],
        "srt": [job.matches],
    }


def check_prerequisites(job: Job, name: str) -> None:
    for path in _prerequisites(job).get(name, []):
        if not path.exists():
            raise SystemExit(
                f"Missing {path.name} (needed by '{name}'). "
                f"Run 'cutter run <job>' or the earlier stages first."
            )


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
    if name not in STAGE_NAMES:
        raise SystemExit(f"Unknown stage: {name}. Stages: {', '.join(STAGE_NAMES)}")
    validate_inputs(job)
    check_prerequisites(job, name)
    job.ensure_dirs()
    for n, output, fn in stage_table(job, cfg):
        if n == name:
            _run(n, output, fn, force=True)
            return


def write_last_job(cuts_path: Path) -> None:
    utility = (Path(os.environ["APPDATA"]) / "Blackmagic Design" / "DaVinci Resolve"
               / "Support" / "Fusion" / "Scripts" / "Utility")
    if not utility.is_dir():
        print("[warn] DaVinci Resolve scripts folder not found; skipped last_job.txt "
              "(install Resolve, then re-run)")
        return
    (utility / "last_job.txt").write_text(str(cuts_path.resolve()), encoding="utf-8")
    print(f"[ok  ] Resolve will cut: {cuts_path}")
