#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qc_article.py — 机检本篇是否符合写作铁律（纯标准库，免 key）

检查项：
  1. 中文字数 >= 2500
  2. 禁用符：无破折号（——）、无 Markdown 粗体（**）
  3. 三张配图均存在于 diagram/ 且为 @2x.png（1360x900 由渲染保证）
  4. 预期输出块与 code/repro/EXPECTED_OUT.txt 的关键行逐行子序列比对
  5. 必备小节齐全：概念澄清一/二/三、结尾钩子、复现模块、三句话总结、来源
  6. 未出现禁用小节：本篇做了什么 / 本文不承诺什么

用法：
  python3 qc_article.py
"""

from __future__ import annotations

import os
import re
import sys

HERE = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
README = os.path.join(HERE, "README.md")
DIAG_DIR = os.path.join(HERE, "diagram")
EXPECTED = os.path.join(HERE, "code", "repro", "EXPECTED_OUT.txt")

REQUIRED_HEADINGS = [
    "## 概念澄清一", "## 概念澄清二", "## 概念澄清三",
    "## 结尾钩子", "## 复现模块", "## 三句话总结", "## 来源",
]
FORBIDDEN_HEADINGS = ["本篇做了什么", "本文不承诺什么"]
REQUIRED_IMAGES = [
    "diagram/01-dataflow@2x.png",
    "diagram/02-blindspots@2x.png",
    "diagram/03-average-vs-percentile@2x.png",
]
MIN_CN_CHARS = 2500


def load(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def count_cn(text: str) -> int:
    return sum(1 for c in text if "\u4e00" <= c <= "\u9fff")


def check_chinese_count(text: str) -> tuple[bool, str]:
    n = count_cn(text)
    ok = n >= MIN_CN_CHARS
    return ok, f"中文字数 = {n}（要求 >= {MIN_CN_CHARS}）"


def check_forbidden_chars(text: str) -> tuple[bool, str]:
    problems = []
    if "——" in text:
        problems.append("破折号(——)")
    if "**" in text:
        problems.append("Markdown 粗体(**)")
    ok = not problems
    return ok, ("无禁用符" if ok else "发现禁用符：" + "、".join(problems))


def check_images(text: str) -> tuple[bool, str]:
    ok = True
    msgs = []
    for img in REQUIRED_IMAGES:
        ref = img.replace("diagram/", "diagram/")
        referenced = ref in text
        exists = os.path.isfile(os.path.join(HERE, img))
        if not referenced:
            msgs.append(f"正文未引用 {img}")
            ok = False
        if not exists:
            msgs.append(f"文件缺失 {img}")
            ok = False
    # 统计正文中图片引用总数（应 >=3）
    refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    if len(refs) < 3:
        msgs.append(f"配图引用数 = {len(refs)}（要求 >=3）")
        ok = False
    return ok, ("配图齐全（%d 张）" % len(refs)) if ok else "；".join(msgs)


def check_headings(text: str) -> tuple[bool, str]:
    ok = True
    msgs = []
    for h in REQUIRED_HEADINGS:
        if h not in text:
            msgs.append(f"缺小节 {h}")
            ok = False
    for f in FORBIDDEN_HEADINGS:
        if f in text:
            msgs.append(f"出现禁用小节 {f}")
            ok = False
    return ok, "必备小节齐全" if ok else "；".join(msgs)


def extract_metrics_lines(expected: str) -> list[str]:
    """从 EXPECTED_OUT.txt 抽取 metrics_collector 表的 4 行（表头 + 3 租户）。"""
    lines = expected.splitlines()
    out = []
    capture = False
    for ln in lines:
        if "metrics_collector.py (normal)" in ln:
            capture = True
            continue
        if capture and ln.strip().startswith("====="):
            break
        if capture and ln.strip():
            # 取表头行与三个租户行
            if ln.lstrip().startswith("tenant") or ln.lstrip().startswith(("acme", "globex", "inyo")):
                out.append(ln.strip())
    return out


def check_expected_subsequence(text: str, expected: str) -> tuple[bool, str]:
    needles = extract_metrics_lines(expected)
    if len(needles) < 4:
        return False, f"未能从 EXPECTED_OUT 抽取到 4 行表（实际 {len(needles)}）"
    hay = [ln.strip() for ln in text.splitlines()]
    i = 0
    for ln in hay:
        if i < len(needles) and ln == needles[i]:
            i += 1
    ok = i == len(needles)
    return ok, (f"预期输出逐行子序列比对通过（{len(needles)} 行）"
                if ok else f"预期输出比对失败，仅匹配 {i}/{len(needles)} 行")


def main() -> int:
    text = load(README)
    expected = load(EXPECTED) if os.path.isfile(EXPECTED) else ""
    checks = []

    c1, m1 = check_chinese_count(text); checks.append(("中文字数", c1, m1))
    c2, m2 = check_forbidden_chars(text); checks.append(("禁用符", c2, m2))
    c3, m3 = check_images(text); checks.append(("配图", c3, m3))
    c4, m4 = check_headings(text); checks.append(("必备小节", c4, m4))
    c5, m5 = check_expected_subsequence(text, expected); checks.append(("预期输出比对", c5, m5))

    print("=" * 56)
    all_ok = True
    for name, ok, msg in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name:<10} | {msg}")
        all_ok = all_ok and ok
    print("=" * 56)
    print("QC: " + ("ALL PASS" if all_ok else "FAILED"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
