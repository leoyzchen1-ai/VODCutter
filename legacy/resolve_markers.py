"""
Read matches.csv (from match_recap.py) and drop a marker on the DaVinci
Resolve timeline at each matched timestamp, labeled with the recap line.
Review/adjust the markers in Resolve, then cut by hand around them —
the matches are approximate, treat them as a starting point, not gospel.

Run this from Resolve's built-in Console (Workspace > Console, switch to Py3),
or externally with Resolve's scripting environment variables set
(see README.md for RESOLVE_SCRIPT_API / RESOLVE_SCRIPT_LIB / PYTHONPATH).

Usage:
    python resolve_markers.py matches.csv
"""
import argparse
import csv
import sys

try:
    import DaVinciResolveScript as dvr
except ImportError:
    sys.exit(
        "Can't import DaVinciResolveScript. Set the Resolve scripting env vars "
        "(see README.md) or run this from Resolve's built-in Python console."
    )

MARKER_COLOR = "Blue"


def main():
    parser = argparse.ArgumentParser(description="Add recap-matched markers to the current Resolve timeline")
    parser.add_argument("matches_csv", help="CSV output from match_recap.py")
    parser.add_argument("--fps", type=float, default=None, help="Timeline frame rate override (else read from timeline)")
    parser.add_argument("--min-confidence", type=float, default=0.0, help="Skip matches below this confidence score")
    args = parser.parse_args()

    resolve = dvr.scriptapp("Resolve")
    project = resolve.GetProjectManager().GetCurrentProject()
    timeline = project.GetCurrentTimeline()
    if not timeline:
        sys.exit("No timeline is open in Resolve. Open the stream footage on a timeline first.")

    fps = args.fps or float(timeline.GetSetting("timelineFrameRate"))

    with open(args.matches_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    added, skipped = 0, 0
    for row in rows:
        if float(row["confidence"]) < args.min_confidence:
            skipped += 1
            continue
        start_seconds = float(row["start"])
        frame_id = int(round(start_seconds * fps))
        note = f"conf {row['confidence']}: {row['matched_transcript'][:80]}"
        ok = timeline.AddMarker(frame_id, MARKER_COLOR, row["recap_line"][:60], note, 1)
        added += 1 if ok else 0

    print(f"Added {added} markers to timeline '{timeline.GetName()}' ({skipped} skipped below confidence threshold)")


if __name__ == "__main__":
    main()
