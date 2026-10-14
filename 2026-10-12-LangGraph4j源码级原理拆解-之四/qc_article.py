#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qc_article.py —— 之四 正文机检。
检查项：
  1. 中文字数 >= 1500
  2. 禁用符号：em dash（—, U+2014）、en dash（–, U+2013）、双连（——）、粗体标记（**）
  3. 配图引用齐全：正文里 @2x.png 引用都真实存在
  4. 精确预期输出：正文 ``` 块抽出后与 EXPECTED_OUT.txt 做逐行子序列匹配
用法：
    python3 qc_article.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))    # 之四 根目录（本脚本所在）
README = os.path.join(HERE, "README.md")              # 之四 正文（与脚本同级）
EXPECTED = os.path.join(HERE, "code", "repro", "EXPECTED_OUT.txt")

MIN_CN = 1500


def count_cn(text: str) -> int:
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def check_forbidden(text: str):
    bad = []
    if "\u2014" in text:
        bad.append("em dash（—）")
    if "\u2013" in text:
        bad.append("en dash（–）")
    if "——" in text:
        bad.append("双连（——）")
    if "**" in text:
        bad.append("粗体标记（**）")
    return bad


def check_images(text: str):
    refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    missing = []
    for ref in refs:
        if ref.endswith("@2x.png") or ref.endswith(".png"):
            p = os.path.join(HERE, ref)
            if not os.path.exists(p):
                missing.append(ref)
    return refs, missing


def extract_expected_block(text: str):
    # 找到「精确预期输出」之后第一个 ``` 包裹的代码块
    idx = text.find("精确预期输出")
    if idx == -1:
        return None
    rest = text[idx:]
    m = re.search(r"```\n(.*?)```", rest, re.DOTALL)
    if not m:
        return None
    return [ln for ln in m.group(1).splitlines()]


def subsequence_match(block, actual_lines):
    # block 的每一行（非空）必须按顺序出现在 actual_lines 中（精确整行匹配）
    ai = 0
    for bl in block:
        if bl.strip() == "":
            continue
        found = False
        while ai < len(actual_lines):
            if actual_lines[ai] == bl:
                found = True
                ai += 1
                break
            ai += 1
        if not found:
            return False, bl
    return True, None


def main() -> int:
    if not os.path.exists(README):
        print(f"[FAIL] 找不到 {README}")
        return 1
    text = open(README, encoding="utf-8").read()

    fails = 0

    # 1) 字数
    cn = count_cn(text)
    if cn >= MIN_CN:
        print(f"[OK] 中文字数 {cn} >= {MIN_CN}")
    else:
        print(f"[FAIL] 中文字数 {cn} < {MIN_CN}")
        fails += 1

    # 2) 禁用符
    bad = check_forbidden(text)
    if not bad:
        print("[OK] 无禁用符号（em/en dash、双连、粗体）")
    else:
        print(f"[FAIL] 检测到禁用符号：{bad}")
        fails += 1

    # 3) 配图
    refs, missing = check_images(text)
    if not missing:
        print(f"[OK] 配图引用齐全（{len(refs)} 张 @2x.png 均存在）")
    else:
        print(f"[FAIL] 配图缺失：{missing}")
        fails += 1

    # 4) 预期输出
    block = extract_expected_block(text)
    if block is None:
        print("[FAIL] 未找到「精确预期输出」代码块")
        fails += 1
    else:
        if not os.path.exists(EXPECTED):
            print(f"[FAIL] 找不到实测输出 {EXPECTED}")
            fails += 1
        else:
            actual = open(EXPECTED, encoding="utf-8").read().splitlines()
            ok, line = subsequence_match(block, actual)
            if ok:
                print("[OK] 精确预期输出与实测 stdout 逐行子序列匹配通过")
            else:
                print(f"[FAIL] 预期输出某行未匹配到实测输出：{line!r}")
                fails += 1

    print()
    if fails == 0:
        print("QC ALL PASS")
        return 0
    print(f"QC FAIL ({fails} 项)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
