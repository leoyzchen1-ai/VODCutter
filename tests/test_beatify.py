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
