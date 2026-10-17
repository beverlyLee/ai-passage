#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 diagram/ 下的 SVG 渲染成 @2x.png（1360x900）。

用 baoyu-diagram 提供的 bun 管线：bun <skill>/scripts/main.ts <svg> --json
main.ts 会在同目录产出 <svg>@2x.png（无白边，背景由 SVG 自身 #0f172a 提供）。
"""

from pathlib import Path
import subprocess
import sys

SKILL_MAIN = Path.home() / ".workbuddy/skills/baoyu-diagram/scripts/main.ts"
BUN = Path.home() / ".bun/bin/bun"
HERE = Path(__file__).resolve().parent

SVGS = [
    "01_bruteforce_vs_ann.svg",
    "02_ivf_hnsw_mechanics.svg",
    "03_recall_latency_embedding.svg",
]


def main():
    if not BUN.exists():
        print("bun 未找到:", BUN)
        sys.exit(1)
    for name in SVGS:
        svg = HERE / name
        if not svg.exists():
            print("跳过缺失文件:", svg)
            continue
        cmd = [str(BUN), str(SKILL_MAIN), str(svg), "--json"]
        print("渲染:", name)
        subprocess.run(cmd, check=True, cwd=str(HERE))


if __name__ == "__main__":
    main()
