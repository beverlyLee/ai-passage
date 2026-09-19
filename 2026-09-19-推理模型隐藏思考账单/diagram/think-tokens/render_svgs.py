#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""渲染本目录下的全部 *.svg 为 @2x PNG（1360x900），校验尺寸后输出。

用法：python render_svgs.py
依赖：Chrome headless（macOS 路径见 CHROME）。无需网络、无需第三方库。
"""
import glob
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TARGET_W, TARGET_H = 1360, 900  # 680x450 @2x


def png_size(path):
    with open(path, "rb") as f:
        data = f.read(33)
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def render(svg_path):
    name = os.path.splitext(os.path.basename(svg_path))[0]
    out = os.path.join(HERE, name + "@2x.png")
    html_path = os.path.join(HERE, "_render.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<style>html,body{margin:0;padding:0;background:#0f172a;}"
            "svg{display:block;}</style></head><body>"
            f"<img src='{os.path.basename(svg_path)}'></body></html>"
        )
    subprocess.run(
        [
            CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--hide-scrollbars", "--force-device-scale-factor=2",
            "--window-size=680,450", "--screenshot=" + out, html_path,
        ],
        check=True,
    )
    if os.path.exists(html_path):
        os.remove(html_path)
    w, h = png_size(out)
    if (w, h) != (TARGET_W, TARGET_H):
        raise SystemExit(f"尺寸不符：{out} -> {w}x{h}，期望 {TARGET_W}x{TARGET_H}")
    print(f"OK  {name}  ({w}x{h})")


def main():
    svgs = sorted(glob.glob(os.path.join(HERE, "*.svg")))
    if not svgs:
        print("没有找到 svg 文件", file=sys.stderr)
        return 1
    for s in svgs:
        render(s)
    print(f"\n全部 {len(svgs)} 张渲染完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
