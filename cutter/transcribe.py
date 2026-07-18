# cutter/transcribe.py
"""
Transcribe a video file to a timestamped JSON transcript using faster-whisper.

Standalone usage:
    python -m cutter.transcribe path/to/stream.mp4 -o transcript.json --model medium
"""
import argparse
import json
from pathlib import Path

from .device import pick_device


def transcribe(video_path, model_size="medium", device="cuda", compute_type="float16", task="transcribe"):
    from faster_whisper import WhisperModel  # lazy: heavy import
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, info = model.transcribe(video_path, beam_size=5, vad_filter=True, task=task)

    result = []
    for seg in segments:
        result.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
        })
        print(f"[{seg.start:8.1f}s -> {seg.end:8.1f}s] {seg.text.strip()}")

    return result


def run_transcribe(video: Path, out_json: Path, model: str, device: str = "auto", task: str = "transcribe") -> None:
    """Pipeline stage: transcribe with auto device + runtime CPU fallback."""
    dev, ctype = pick_device(device)
    if dev == "cpu":
        print("[warn] transcribing on CPU: a long VOD can take a long time "
              "(a smaller --model, e.g. 'small', is much faster)")
    try:
        segments = transcribe(str(video), model, dev, ctype, task)
    except Exception as e:
        if dev != "cuda":
            raise
        print(f"[!] CUDA transcription failed ({e}); retrying on CPU/int8")
        print("[warn] transcribing on CPU: a long VOD can take a long time "
              "(a smaller --model, e.g. 'small', is much faster)")
        segments = transcribe(str(video), model, "cpu", "int8", task)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(segments, f, indent=2, ensure_ascii=False)
    print(f"[transcribe] {len(segments)} segments -> {out_json}")


def main():
    parser = argparse.ArgumentParser(description="Transcribe video with timestamps")
    parser.add_argument("video", help="Path to source video/audio file")
    parser.add_argument("-o", "--output", default="transcript.json", help="Output JSON path")
    parser.add_argument("--model", default="medium", help="Whisper model size (tiny/base/small/medium/large-v3)")
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"], help="Inference device")
    parser.add_argument("--task", default="transcribe", choices=["transcribe", "translate"])
    args = parser.parse_args()
    run_transcribe(Path(args.video), Path(args.output), args.model, args.device, args.task)


if __name__ == "__main__":
    main()
