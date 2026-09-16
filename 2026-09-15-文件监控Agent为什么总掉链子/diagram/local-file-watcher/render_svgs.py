#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""渲染本目录所有 SVG 为 @2x PNG（1360x900）。

依赖：Chrome / Chromium headless。macOS 标准路径见 CHROME。
用法：python3 render_svgs.py
"""
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# 回退候选
CANDIDATES = [
    CHROME,
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]


def find_chrome() -> str:
    for c in CANDIDATES:
        if os.path.exists(c):
            return c
    # 兜底：依赖 PATH
    return "google-chrome"


def render(svg: str) -> None:
    png = svg[:-4] + "@2x.png"
    cmd = [
        find_chrome(),
        "--headless", "--disable-gpu", "--no-sandbox",
        "--hide-scrollbars", "--force-device-scale-factor=2",
        "--window-size=680,450",
        "--screenshot=" + png,
        "file://" + svg,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("rendered", os.path.basename(png))


def main() -> int:
    svgs = sorted(glob.glob(os.path.join(HERE, "*.svg")))
    if not svgs:
        print("no svg found")
        return 1
    for s in svgs:
        render(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
