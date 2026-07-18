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
