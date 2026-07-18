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
