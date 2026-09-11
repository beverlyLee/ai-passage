#!/usr/bin/env python3
import os
import subprocess
import struct

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SVG_DIR = "/Users/liboyang/WorkBuddy/2026-08-14-17-18-24/ai-passage/2026-09-11-GPT-6Astra强在哪又怕在哪/diagram/GPT-6Astra强在哪又怕在哪"

SVGS = [
    "01-computer-use-architecture.svg",
    "02-benchmark-comparison.svg",
    "03-searchable-notes.svg",
    "04-critical-daybreak.svg",
    "05-capability-safety-tradeoff.svg",
    "06-pricing-cliff.svg",
]


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(26)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def main():
    os.makedirs(SVG_DIR, exist_ok=True)
    for svg in SVGS:
        src = os.path.join(SVG_DIR, svg)
        out = os.path.join(SVG_DIR, svg.replace(".svg", "@2x.png"))
        if not os.path.exists(src):
            print(f"MISSING {src}")
            continue
        subprocess.run(
            [
                CHROME,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--hide-scrollbars",
                "--force-device-scale-factor=2",
                "--window-size=680,450",
                f"--screenshot={out}",
                src,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        size = png_size(out)
        ok = size == (1360, 900)
        print(f"{svg} -> {out} {size} {'OK' if ok else 'BAD SIZE'}")


if __name__ == "__main__":
    main()
