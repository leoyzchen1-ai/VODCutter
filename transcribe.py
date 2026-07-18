"""
Transcribe a video file to a timestamped JSON transcript using faster-whisper.

Usage:
    python transcribe.py path/to/stream.mp4 -o transcript.json --model medium

Requires: pip install faster-whisper
"""
import argparse
import json
from faster_whisper import WhisperModel


def transcribe(video_path, model_size="medium", device="cuda", compute_type="float16", task="transcribe"):
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


def main():
    parser = argparse.ArgumentParser(description="Transcribe video with timestamps")
    parser.add_argument("video", help="Path to source video/audio file")
    parser.add_argument("-o", "--output", default="transcript.json", help="Output JSON path")
    parser.add_argument("--model", default="medium", help="Whisper model size (tiny/base/small/medium/large-v3)")
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"], help="Inference device")
    parser.add_argument("--compute-type", default="float16", help="float16 (GPU), int8 (CPU-friendly)")
    parser.add_argument("--task", default="transcribe", choices=["transcribe", "translate"],
                        help="transcribe = keep source language; translate = output English (for matching an English recap against a non-English stream)")
    args = parser.parse_args()

    segments = transcribe(args.video, args.model, args.device, args.compute_type, args.task)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(segments, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(segments)} segments to {args.output}")


if __name__ == "__main__":
    main()
