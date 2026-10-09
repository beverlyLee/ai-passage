#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文章质量自检：禁用符号、中文字数区间、配图引用是否真实存在。

数据源路径约定：脚本位于 <文章目录>/code/，文章为 <文章目录>/README.md，
配图引用相对 <文章目录> 解析。

运行：python3 code/qc_article.py
"""

import pathlib
import re

CN_LOW = 400
CN_HIGH = 4000

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARTICLE = ROOT / "README.md"


def count_cn(text):
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def main():
    if not ARTICLE.exists():
        print("文章不存在：%s" % ARTICLE)
        return 1

    text = ARTICLE.read_text(encoding="utf-8")
    problems = []

    # 1. 禁用符号
    for bad in ["——", "—", "–", "**", "__"]:
        if bad in text:
            problems.append("发现禁用符号：%r" % bad)

    # 2. 中文字数区间
    cn = count_cn(text)
    if cn < CN_LOW or cn > CN_HIGH:
        problems.append("中文字数 %d 不在 [%d, %d]" % (cn, CN_LOW, CN_HIGH))
    else:
        print("中文字数：%d（区间 [%d, %d]）" % (cn, CN_LOW, CN_HIGH))

    # 3. 配图引用存在性
    refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    missing = []
    for ref in refs:
        if not (ROOT / ref).exists():
            missing.append(ref)
    if missing:
        problems.append("配图引用缺失：%s" % ", ".join(missing))

    print("配图引用 %d 张，缺失 %d 张" % (len(refs), len(missing)))

    if problems:
        print("")
        for p in problems:
            print("[FAIL] %s" % p)
        print("qc FAIL")
        return 1

    print("qc PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
