#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""之六正文 QC：中文字数区间、禁用符号（破折号/粗体）、配图引用存在性。

用法：python3 code/qc_article.py
"""

import os
import re
import sys

CN_LOW = 400
CN_HIGH = 4000

ARTICLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README.md")
DIAGRAM_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "diagram")


def count_cn(text):
    return len(re.findall(r"[一-鿿]", text))


def main():
    with open(ARTICLE, "r", encoding="utf-8") as fh:
        text = fh.read()

    cn = count_cn(text)
    ok = True

    # 中文字数区间
    if CN_LOW <= cn <= CN_HIGH:
        print("中文字数：%d（区间 [%d, %d]）" % (cn, CN_LOW, CN_HIGH))
    else:
        print("中文字数：%d（超出区间 [%d, %d]）" % (cn, CN_LOW, CN_HIGH))
        ok = False

    # 禁用符号：破折号（—— / — / –）与粗体（** / __）
    bad = []
    if "——" in text:
        bad.append("双破折号 ——")
    if "—" in text:
        bad.append("em dash —")
    if "–" in text:
        bad.append("en dash –")
    if "**" in text:
        bad.append("双星号粗体 **")
    if "__" in text:
        bad.append("双下划线粗体 __")
    if bad:
        print("发现禁用符号：" + "，".join(bad))
        ok = False
    else:
        print("禁用符号（破折号/粗体）：无")

    # 配图引用存在性：![...](diagram/xxx@2x.png)
    refs = re.findall(r"!\[[^\]]*\]\((diagram/[^)]+)\)", text)
    missing = []
    for ref in refs:
        target = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ref)
        if not os.path.exists(target):
            missing.append(ref)
    if refs:
        print("配图引用 %d 张，缺失 %d 张" % (len(refs), len(missing)))
        for m in missing:
            print("  缺失：" + m)
        if missing:
            ok = False
    else:
        print("配图引用：0 张")
        ok = False

    if ok:
        print("qc PASS")
        return 0
    print("qc FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
