#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_svgs.py —— 把 diagram/ 目录下的所有 SVG 渲染成 @2x.png（1360x900）。

渲染管线：baoyu-diagram 技能的 main.ts（用 sharp 按 SVG viewBox 放大 2 倍，
0 0 680 450 -> 1360x900，无白边）。本脚本只是把这一步自动化，方便复现。

用法：
    python3 render_svgs.py
依赖：
    - bun（默认 ~/.bun/bin/bun）
    - baoyu-diagram 技能：~/.workbuddy/skills/baoyu-diagram/scripts/main.ts
    - sharp（由 baoyu-diagram 技能自带，无需另行安装）
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN_TS = os.path.expanduser("~/.workbuddy/skills/baoyu-diagram/scripts/main.ts")
BUN = os.path.expanduser("~/.bun/bin/bun")


def main() -> int:
    if not os.path.exists(MAIN_TS):
        print(f"[ERR] 找不到渲染脚本：{MAIN_TS}")
        return 1
    if not os.path.exists(BUN):
        print(f"[ERR] 找不到 bun：{BUN}")
        return 1

    svgs = sorted(f for f in os.listdir(HERE) if f.endswith(".svg"))
    if not svgs:
        print("[ERR] diagram/ 目录下没有 .svg 文件")
        return 1

    ok = 0
    for svg in svgs:
        path = os.path.join(HERE, svg)
        out = os.path.join(HERE, svg.replace(".svg", "@2x.png"))
        print(f"[render] {svg} -> {os.path.basename(out)}")
        r = subprocess.run(
            [BUN, MAIN_TS, path, "--json"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if r.returncode != 0:
            print(f"[FAIL] {svg}\n{r.stderr.decode('utf-8', 'ignore')}")
            return 1
        if not os.path.exists(out):
            print(f"[FAIL] 未生成 {out}")
            return 1
        ok += 1

    print(f"\n[OK] 共渲染 {ok} 张 @2x.png（1360x900，无白边）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
