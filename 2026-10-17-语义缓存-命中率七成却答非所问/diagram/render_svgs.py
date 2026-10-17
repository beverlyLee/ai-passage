#!/usr/bin/env python3
# 把 diagram/ 下的 SVG 渲染为 1360x900 的 @2x PNG（无白边）。
# 依赖：bun + ~/.workbuddy/skills/baoyu-diagram/scripts/main.ts（用 sharp 渲染）。
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SVGS = [
    "01_three_tier_arch.svg",
    "02_query_dataflow.svg",
    "03_threshold_and_eviction.svg",
]
BUN = "/Users/liboyang/.bun/bin/bun"
MAIN = str(Path.home() / ".workbuddy/skills/baoyu-diagram/scripts/main.ts")


def main():
    for name in SVGS:
        svg = HERE / name
        if not svg.exists():
            print("missing:", svg)
            return 1
        out = subprocess.run([BUN, MAIN, str(svg), "--json"],
                             capture_output=True, text=True)
        if out.returncode != 0:
            print("FAIL", name, out.stderr)
            return 1
        print(out.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
