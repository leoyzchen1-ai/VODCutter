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
