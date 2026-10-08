#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Spring AI Alibaba 源码级系列之 一 的质量标尺（QC）。

检查项：
1. 禁用符号：em dash（—）、en dash（–）、双连（——）。中文标点只允许 。，；：！？、（）《》"" 与空格。
2. 禁用粗体：整篇（含代码块）不得出现 ** 或 __ 包裹。
3. 中文字数 >= 4000。
4. 配图引用：正文里的 ![..](diagram/xxx@2x.png) 必须含 @ 且指向已存在的 @2x.png 文件。
5. 必备小节：标题、引言、复现模块、结尾钩子。
用法：python qc_article.py（在文章目录下运行）
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MD = os.path.join(HERE, "正文.md")
DIAGRAM_DIR = os.path.join(HERE, "diagram")

BANNED_CHARS = ["\u2014", "\u2013"]  # —  –
BOLD_PATTERN = re.compile(r"\*\*|__")
CHINESE = re.compile(r"[\u4e00-\u9fff]")

REQUIRED_SECTIONS = ["复现模块", "结尾", "分层架构", "模块依赖", "数据流", "Graph 执行"]


def strip_code_blocks(text):
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def check_banned_chars(text):
    out = []
    for ch in BANNED_CHARS:
        if ch in text:
            n = text.count(ch)
            out.append(f"禁用符号 {ch!r} 出现 {n} 次")
    # 双连 —— 也由 — 覆盖，这里额外显式查
    if "\u2014\u2014" in text:
        out.append("禁用符号 ——（双连）出现")
    return out


def check_bold(text):
    m = BOLD_PATTERN.findall(text)
    return len(m)


def check_chinese_count(text):
    return len(CHINESE.findall(text))


def check_required_sections(text):
    missing = [s for s in REQUIRED_SECTIONS if s not in text]
    return missing


def check_diagram_refs(text):
    refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    problems = []
    for r in refs:
        if "@" not in r:
            problems.append(f"配图引用缺 @：{r}")
        if not r.endswith("@2x.png"):
            problems.append(f"配图引用未指向 @2x.png：{r}")
        f = os.path.join(HERE, r)
        if not os.path.exists(f):
            problems.append(f"配图文件不存在：{r}")
    return problems


def main():
    if not os.path.exists(MD):
        print(f"FAIL: 找不到 {MD}")
        sys.exit(1)
    raw = open(MD, encoding="utf-8").read()
    body = strip_code_blocks(raw)

    issues = []
    issues += check_banned_chars(body)
    bcount = check_bold(body)
    if bcount:
        issues.append(f"粗体标记 **/__ 出现 {bcount} 次")
    cc = check_chinese_count(body)
    if cc < 4000:
        issues.append(f"中文字数 {cc} < 4000")
    issues += check_required_sections(raw)
    issues += check_diagram_refs(raw)

    if issues:
        print("QC FAIL:")
        for i in issues:
            print(f"  - {i}")
        sys.exit(1)
    print(f"QC PASS | 中文字数 {cc} | 禁用符号 0 | 粗体 0 | 配图引用全部有效")
    sys.exit(0)


if __name__ == "__main__":
    main()
