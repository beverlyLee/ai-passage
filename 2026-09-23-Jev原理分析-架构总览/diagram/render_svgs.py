#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
篇1 配图渲染管线（本地、无网络依赖）
把 diagram/*.svg 渲染成 @2x.png（1360x900）。

原理：用 Chrome headless 打开一个 680x450 的 HTML 包裹页，
页面里用 <img> 精确铺满 SVG，再以 device-scale-factor=2 截图。
这样产出的 PNG 严格等于 1360x900，没有白边、没有缩放错位。

前置：系统已装 Google Chrome（macOS 默认路径）。
字体：SVG 用 Noto Sans SC / PingFang SC 字体栈，headless 下回退到本机 PingFang SC。
"""
import pathlib
import subprocess
import sys
import tempfile

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SVG_DIR = pathlib.Path(__file__).resolve().parent

# 本篇 6 张图，顺序即渲染顺序
NAMES = [
    "01_mental_model",
    "02_speed_cost",
    "03_fault_tree",
    "04_naming",
    "05_architecture",
    "06_dataflow",
]

SCALE = 2
WIN_W, WIN_H = 680, 450  # 与 SVG viewBox 一致


def build_html(svg_file: pathlib.Path) -> str:
    # 用绝对 file:// 引用，scale 由 Chrome 负责；body 精确锁 680x450
    src = svg_file.resolve().as_uri()
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<style>"
        "html,body{margin:0;padding:0;width:680px;height:450px;overflow:hidden;"
        "background:#0f172a}"
        "img{display:block;width:680px;height:450px;border:0}"
        "</style></head><body>"
        "<img src='" + src + "'>"
        "</body></html>"
    )


def render_one(name: str) -> pathlib.Path:
    svg = SVG_DIR / (name + ".svg")
    if not svg.exists():
        raise SystemExit("缺少 SVG: " + str(svg))
    out = SVG_DIR / (name + "@2x.png")
    html_text = build_html(svg)

    with tempfile.NamedTemporaryFile(
        "w", suffix=".html", delete=False, encoding="utf-8"
    ) as f:
        f.write(html_text)
        html_path = f.name

    cmd = [
        CHROME,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        "--force-device-scale-factor=" + str(SCALE),
        "--window-size=" + str(WIN_W) + "," + str(WIN_H),
        "--virtual-time-budget=2500",
        "--screenshot=" + str(out),
        "file://" + html_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out


def main() -> int:
    if not pathlib.Path(CHROME).exists():
        raise SystemExit("未找到 Chrome: " + CHROME)
    for name in NAMES:
        out = render_one(name)
        print("rendered:", out.name)
    print("全部完成，每张应为 %dx%d" % (WIN_W * SCALE, WIN_H * SCALE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
