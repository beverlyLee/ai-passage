#!/usr/bin/env python3
# 文章 QC 流水线（Spring AI Alibaba 系列）
# 校验：中文字数区间、禁用符号（破折号 —— / — / –）、禁用粗体（** / __）、配图引用真实存在。
# 纯标准库，零依赖。python3 qc_article.py
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = ROOT / "README.md"

CN_LOW = 400
CN_HIGH = 4000


def main() -> int:
    text = README.read_text(encoding="utf-8")
    errors = []

    cn = len(re.findall(r"[一-鿿]", text))
    if cn < CN_LOW:
        errors.append(f"中文字数过少: {cn} < {CN_LOW}")
    if cn > CN_HIGH:
        errors.append(f"中文字数过多: {cn} > {CN_HIGH}")

    if "——" in text:
        errors.append("含双破折号 ——")
    if "—" in text:
        errors.append("含 em dash —（破折号）")
    if "–" in text:
        errors.append("含 en dash –（破折号）")
    if "**" in text or "__" in text:
        errors.append("含粗体标记 ** / __")

    refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    for ref in refs:
        if not (ROOT / ref).exists():
            errors.append(f"配图缺失: {ref}")

    print(f"中文字数 : {cn}")
    print(f"配图引用 : {len(refs)} -> {refs}")

    if errors:
        print("QC 失败:")
        for e in errors:
            print(" -", e)
        return 1
    print("QC PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
