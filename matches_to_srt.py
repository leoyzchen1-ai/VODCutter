"""
Convert matches.csv (from match_recap.py) into an SRT subtitle file.

Workaround for DaVinci Resolve *free*, which has no scripting API: instead of
dropping timeline markers (Studio-only), import this SRT onto a subtitle track.
Each recap beat becomes a subtitle clip sitting at its matched timecode, so you
can eyeball / navigate to each beat and cut around it.

Assumes the VOD starts at the very start of the timeline (timeline 00:00:00 =
video 0s), same assumption resolve_markers.py made.

Usage:
    python matches_to_srt.py matches.csv -o recap.srt
    python matches_to_srt.py matches.csv --min-confidence 0.15
"""
import argparse
import csv


def to_timecode(seconds):
    if seconds < 0:
        seconds = 0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    parser = argparse.ArgumentParser(description="Convert recap matches CSV to an SRT subtitle file")
    parser.add_argument("matches_csv", help="CSV output from match_recap.py")
    parser.add_argument("-o", "--output", default="recap.srt", help="Output SRT path")
    parser.add_argument("--min-confidence", type=float, default=0.0, help="Skip matches below this confidence score")
    parser.add_argument("--min-duration", type=float, default=2.0,
                        help="Minimum seconds a subtitle stays on screen (padded past 'end' if needed)")
    parser.add_argument("--show-confidence", action="store_true",
                        help="Prefix each line with its confidence score")
    args = parser.parse_args()

    with open(args.matches_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    entries = []
    for row in rows:
        if float(row["confidence"]) < args.min_confidence:
            continue
        start = float(row["start"])
        end = float(row.get("end") or start)
        if end - start < args.min_duration:
            end = start + args.min_duration
        text = row["recap_line"].strip()
        if args.show_confidence:
            text = f"[{row['confidence']}] {text}"
        entries.append((start, end, text))

    entries.sort(key=lambda e: e[0])

    with open(args.output, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(entries, 1):
            f.write(f"{i}\n{to_timecode(start)} --> {to_timecode(end)}\n{text}\n\n")

    print(f"Wrote {len(entries)} subtitles to {args.output}")


if __name__ == "__main__":
    main()
