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
