#!/usr/bin/env python3
# 把 diagram/ 下所有 .svg 用 baoyu-diagram 渲染成 @2x.png（1360x900，无白边）
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.expanduser("~/.workbuddy/skills/baoyu-diagram/scripts/main.ts")
BUN = os.path.expanduser("~/.bun/bin/bun")


def main():
    svgs = sorted(f for f in os.listdir(HERE) if f.endswith(".svg"))
    if not svgs:
        print("no svg found")
        sys.exit(1)
    for s in svgs:
        out = subprocess.run(
            [BUN, SCRIPT, s, "--json"],
            cwd=HERE,
            capture_output=True,
            text=True,
        )
        if out.returncode != 0:
            print("FAIL", s)
            print(out.stderr)
            sys.exit(1)
        print("rendered", s.replace(".svg", "@2x.png"))


if __name__ == "__main__":
    main()
