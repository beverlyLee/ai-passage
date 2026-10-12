#!/usr/bin/env python3
"""qc_article.py — 之九（Agent 运行时与多轮记忆）文章 QC。

检查项：
    1. 禁用符号：em dash ——、en dash —、en dash –、粗体 ** 与 __
    2. 中文正文字数落在 [CN_LOW, CN_HIGH] 区间
    3. 配图引用 ![]() 中存在且文件名含 @2x.png

用法：
    python3 code/qc_article.py [文章md路径]
默认校验同级目录的 ../README.md
"""
import os
import re
import sys

CN_LOW = 400
CN_HIGH = 4000

ARTICLE = os.path.join(os.path.dirname(__file__), "..", "README.md")


def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def count_cn(text):
    return len(re.findall(r"[一-鿿]", text))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else ARTICLE
    if not os.path.exists(path):
        print(f"[FAIL] 文章文件不存在: {path}")
        sys.exit(1)
    text = read_text(path)
    errors = []

    for sym, label in [("——", "双连 em dash"), ("—", "em dash"), ("–", "en dash"),
                       ("**", "粗体 **"), ("__", "粗体 __")]:
        if sym in text:
            errors.append(f"发现禁用符号 [{label}]")

    cn = count_cn(text)
    if cn < CN_LOW or cn > CN_HIGH:
        errors.append(f"中文字数 {cn} 超出区间 [{CN_LOW}, {CN_HIGH}]")

    refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    at2x = [r for r in refs if "@2x.png" in r]
    if not refs:
        errors.append("未找到任何配图引用 ![]()")
    elif not at2x:
        errors.append("配图引用未使用 @2x.png 命名")
    else:
        missing = []
        for r in at2x:
            local = r.split("#")[0]
            if not os.path.isabs(local):
                local = os.path.normpath(os.path.join(os.path.dirname(path), local))
            if not os.path.exists(local):
                missing.append(r)
        if missing:
            errors.append(f"配图文件不存在: {missing}")

    if errors:
        print("[FAIL] QC 未通过：")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print(f"[PASS] 之九 QC 通过：中文字数 {cn}，配图引用 {len(at2x)} 张（均 @2x.png 且文件存在）")
    sys.exit(0)


if __name__ == "__main__":
    main()
