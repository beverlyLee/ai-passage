#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_svgs.py —— 把手写深色 SVG 渲染为 @2x.png（1360×900）
本机无 baoyu-diagram / rsvg / inkscape / cairosvg / sharp，
唯一可行方案：Chrome headless --screenshot。

用法：
  python3 render_svgs.py
校验：产出 01-..@2x.png ~ 06-..@2x.png，尺寸必须 1360×900。
"""
import os
import struct
import subprocess

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SVG_DIR = "/Users/liboyang/WorkBuddy/2026-08-14-17-18-24/ai-passage/2026-09-12-AI视频平民化/diagram/AI视频平民化"

# 顺序 == 阅读顺序 == 图注号 == 配图 CDN 清单（四同步）
SVGS = [
    "01-dit-compute-wall.svg",
    "02-joint-audiovisual.svg",
    "03-ar-dit-streaming.svg",
    "04-reference-conditioning.svg",
    "05-distribution-closure.svg",
    "06-five-pillars.svg",
]


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(26)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def main():
    for svg in SVGS:
        src = os.path.join(SVG_DIR, svg)
        out = os.path.join(SVG_DIR, svg[:-4] + "@2x.png")
        cmd = [
            CHROME, "--headless", "--disable-gpu", "--no-sandbox",
            "--hide-scrollbars", "--force-device-scale-factor=2",
            "--window-size=680,450", f"--screenshot={out}", src,
        ]
        print(f"rendering {svg} ...")
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        size = png_size(out)
        ok = size == (1360, 900)
        print(f"  -> {os.path.basename(out)} size={size} {'OK' if ok else 'BAD'}")
        if not ok:
            raise SystemExit(f"尺寸异常：{out} = {size} (期望 1360x900)")


if __name__ == "__main__":
    main()
