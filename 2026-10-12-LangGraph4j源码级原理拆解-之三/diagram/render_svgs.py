#!/usr/bin/env python3
"""Render dark-theme SVGs to @2x PNGs (1360x900) via Chrome headless.

Pipeline: each SVG is embedded in a 680x450 HTML wrapper, then captured at
device scale factor 2 so the output is exactly 1360x900 with no white border.
Also runs a bounds self-check: every rect/text x+width must stay < 680 and
y+height < 450, so nothing spills off the canvas.
"""
import html
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

SVG_FILES = [
    "01_state_is_map.svg",
    "02_channel_strategies.svg",
    "03_update_state.svg",
]

W, H = 680, 450


def bounds_check(svg_name: str) -> None:
    """Flag any rect/text whose right or bottom edge would exceed the canvas."""
    path = os.path.join(HERE, svg_name)
    with open(path, encoding="utf-8") as f:
        svg = f.read()
    problems = []
    # rect: x, y, width, height
    for m in re.finditer(r"<rect\b[^>]*>", svg):
        tag = m.group(0)
        def num(attr):
            mm = re.search(attr + r'="(-?[\d.]+)"', tag)
            return float(mm.group(1)) if mm else None
        x, y = num("x") or 0.0, num("y") or 0.0
        w, h = num("width") or 0.0, num("height") or 0.0
        if x + w > W + 0.5:
            problems.append(f"rect right edge {x + w:.0f} > {W}  :: {tag[:60]}")
        if y + h > H + 0.5:
            problems.append(f"rect bottom edge {y + h:.0f} > {H}  :: {tag[:60]}")
    # text: x, y
    for m in re.finditer(r"<text\b[^>]*>", svg):
        tag = m.group(0)
        def num(attr):
            mm = re.search(attr + r'="(-?[\d.]+)"', tag)
            return float(mm.group(1)) if mm else None
        x, y = num("x") or 0.0, num("y") or 0.0
        if x > W - 20:
            problems.append(f"text x={x:.0f} near/over right edge  :: {tag[:60]}")
        if y > H - 4:
            problems.append(f"text y={y:.0f} at/over bottom edge  :: {tag[:60]}")
    if problems:
        print(f"BOUNDS FAIL {svg_name}")
        for p in problems:
            print("   " + p)
        sys.exit(1)
    print(f"BOUNDS OK  {svg_name}")


def wrapper(svg_path: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>"
        "html,body{margin:0;padding:0;width:680px;height:450px;"
        "overflow:hidden;background:#0f172a}"
        "img{display:block;width:680px;height:450px}"
        "</style></head><body>"
        f"<img src='file://{html.escape(svg_path)}' width='680' height='450'>"
        "</body></html>"
    )


def render(svg_name: str) -> None:
    svg_path = os.path.join(HERE, svg_name)
    if not os.path.exists(svg_path):
        print(f"MISSING {svg_path}")
        sys.exit(1)
    html_path = os.path.join(HERE, svg_name.replace(".svg", ".html"))
    png_path = os.path.join(HERE, svg_name.replace(".svg", "@2x.png"))
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(wrapper(svg_path))
    subprocess.run(
        [
            CHROME,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            "--force-device-scale-factor=2",
            "--window-size=680,450",
            f"--screenshot={png_path}",
            html_path,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"RENDERED {png_path}")


if __name__ == "__main__":
    for name in SVG_FILES:
        bounds_check(name)
        render(name)
    print("ALL DONE")
