#!/usr/bin/env python3
"""qc_article.py

对《流式网关与限流》正文做机器自检：
  1. 中文字数 >= 2500
  2. 禁用符：不含破折号（——）与 markdown 粗体（**）
  3. 配图引用文件真实存在（3 张 @2x.png）
  4. 正文 ``` 包裹的输出块（非运行命令块）逐行作为子序列出现在 EXPECTED_OUT.txt
  5. 必备小节齐全：结尾钩子 / 复现模块 / 如果你要把它讲给别人听 / 来源

运行: python3 qc_article.py
"""

import os
import re
import sys
from pathlib import Path

ARTICLE_DIR = Path(__file__).resolve().parent
if "ARTICLE_DIR" in os.environ:
    ARTICLE_DIR = Path(os.environ["ARTICLE_DIR"]).resolve()
README = ARTICLE_DIR / "README.md"
EXPECTED = ARTICLE_DIR / "code" / "repro" / "EXPECTED_OUT.txt"

REQUIRED_SECTIONS = ["结尾钩子", "复现模块", "如果你要把它讲给别人听", "来源"]
DIAGRAM_REFS = [
    "diagram/01_algorithms@2x.png",
    "diagram/02_streaming_admission@2x.png",
    "diagram/03_gateway_arch@2x.png",
]
MIN_CJK = 2500


def count_cjk(text: str) -> int:
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def extract_fenced_blocks(text: str):
    """返回所有 ``` 代码块内容列表（去掉围栏行）。"""
    blocks = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("```"):
            buf = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            blocks.append("\n".join(buf))
            i += 1  # 跳过结束围栏
        else:
            i += 1
    return blocks


def is_subsequence(needle_lines, hay_lines):
    """needle_lines 是否按序作为 hay_lines 的子序列（逐行精确匹配）。"""
    it = iter(hay_lines)
    for n in needle_lines:
        n = n.rstrip("\n")
        if n == "":
            continue
        found = False
        for h in it:
            if h.rstrip("\n") == n:
                found = True
                break
        if not found:
            return False
    return True


def main():
    fails = []
    readme = README.read_text(encoding="utf-8")
    expected_text = EXPECTED.read_text(encoding="utf-8")
    expected_lines = expected_text.splitlines()

    # 1. 中文字数
    cjk = count_cjk(readme)
    print(f"[check] 中文字数 = {cjk} (>= {MIN_CJK})")
    if cjk < MIN_CJK:
        fails.append(f"中文字数不足：{cjk} < {MIN_CJK}")

    # 2. 禁用符
    if "——" in readme:
        fails.append("正文中出现破折号（——）")
    if "**" in readme:
        fails.append("正文中出现 markdown 粗体（**）")
    print("[check] 禁用符 破折号/粗体：已扫描")

    # 3. 配图文件存在
    for ref in DIAGRAM_REFS:
        p = ARTICLE_DIR / ref
        if not p.exists():
            fails.append(f"配图缺失：{ref}")
        else:
            print(f"[check] 配图存在：{ref}")
    # 正文是否引用了这些配图
    for ref in DIAGRAM_REFS:
        if ref not in readme:
            fails.append(f"正文未引用配图：{ref}")

    # 4. 输出块子序列比对（跳过含 python3 的运行命令块）
    blocks = extract_fenced_blocks(readme)
    checked = 0
    for b in blocks:
        if "python3" in b:
            continue
        if b.strip() == "":
            continue
        checked += 1
        if not is_subsequence(b.splitlines(), expected_lines):
            fails.append("输出块与 EXPECTED_OUT.txt 逐行比对失败：\n" + b[:200])
        else:
            print(f"[check] 输出块子序列比对通过（{len(b.splitlines())} 行）")
    if checked == 0:
        fails.append("未找到任何可比对的正文输出块")

    # 5. 必备小节
    for sec in REQUIRED_SECTIONS:
        if sec not in readme:
            fails.append(f"缺失必备小节：{sec}")
        else:
            print(f"[check] 必备小节存在：{sec}")

    print("-" * 40)
    if fails:
        print("QC FAIL")
        for f in fails:
            print("  - " + f)
        return 1
    print("QC PASS: 全部检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
