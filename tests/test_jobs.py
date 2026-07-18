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
