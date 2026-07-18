"""
OCR pass over the VOD: sample a frame every few seconds, read the on-screen
text, and cache it to ocr.csv (columns: t, text). Torch-free (RapidOCR on
onnxruntime), so it runs where Smart App Control blocks torch.

The on-screen text is what actually identifies a screen -- a banner splash
literally reads "SIGNAL SEARCH / REMIELLE", an event card reads its title, etc.
snap_visual.py matches recap beats against this text.

Run once (cached):
    & "D:\\CutterDavinci\\.venv\\Scripts\\python.exe" D:\\CutterDavinci\\ocr_pass.py
"""
import argparse
import csv
import os
import av
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

VIDEO = r"E:\Videos\VersionRecaps\ZZZ3.1\Zenless Zone Zero Version 3.1 - The Long Goodbye Special Program.mp4"
OUT = r"E:\Videos\VersionRecaps\ZZZ3.1\ocr.csv"
SAMPLE_S = 3.0          # seconds between OCR'd frames (titles/banners linger)
OCR_WIDTH = 1280        # downscale width for OCR (enough to read title text)
MIN_CONF = 0.5


def main():
    p = argparse.ArgumentParser(description="OCR the VOD every few seconds -> ocr.csv")
    p.add_argument("--video", default=VIDEO)
    p.add_argument("--out", default=OUT)
    p.add_argument("--sample", type=float, default=SAMPLE_S)
    args = p.parse_args()

    if os.path.exists(args.out) and os.path.getmtime(args.out) >= os.path.getmtime(args.video):
        print(f"OCR cache already current: {args.out}")
        return

    ocr = RapidOCR()
    container = av.open(args.video)
    stream = container.streams.video[0]
    tb = stream.time_base
    last_t = -1e9
    rows = []
    for frame in container.decode(stream):
        t = float(frame.pts * tb) if frame.pts is not None else None
        if t is None or t - last_t < args.sample:
            continue
        last_t = t
        h = int(frame.height * OCR_WIDTH / frame.width)
        img = frame.reformat(width=OCR_WIDTH, height=h, format="rgb24").to_ndarray()
        res, _ = ocr(img)
        texts = []
        if res:
            for _, txt, conf in res:
                if conf >= MIN_CONF:
                    texts.append(txt)
        joined = " ".join(texts).replace("\n", " ")
        rows.append((round(t, 1), joined))
        if len(rows) % 25 == 0:
            print(f"  {t:6.0f}s / 3424s  ({len(rows)} frames)  last: {joined[:60]}")
    container.close()

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t", "text"])
        w.writerows(rows)
    print(f"Wrote {args.out} ({len(rows)} frames OCR'd)")


if __name__ == "__main__":
    main()
