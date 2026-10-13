#!/usr/bin/env python3
"""Render dark-theme SVGs to @2x PNGs (1360x900) via Chrome headless.

Pipeline: each SVG is embedded in a 680x450 HTML wrapper, then captured at
device scale factor 2 so the output is exactly 1360x900 with no white border.
"""
import html
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

SVG_FILES = [
    "01_declare_graph.svg",
    "02_conditional_routing.svg",
    "03_subgraph.svg",
]


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
        render(name)
    print("ALL DONE")
