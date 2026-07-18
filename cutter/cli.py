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
