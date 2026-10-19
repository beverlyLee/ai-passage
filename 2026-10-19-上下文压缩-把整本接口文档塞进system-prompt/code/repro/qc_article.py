#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上下文压缩篇 QC：机检字数、禁用符、配图引用、self-test 子序列比对、必备小节。"""
import re
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
README = os.path.join(ROOT, "README.md")
EXPECTED = os.path.join(ROOT, "code", "repro", "EXPECTED_OUT.txt")


def cn_count(text):
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def main():
    ok = True
    readme = open(README, encoding="utf-8").read()

    # 1. 中文字数
    n = cn_count(readme)
    print("中文字数: %d" % n)
    if n < 2500:
        ok = False
        print("  FAIL: 中文字数 < 2500")
    else:
        print("  ok: 中文字数 >= 2500")

    # 2. 禁用符
    if "——" in readme:
        ok = False
        print("  FAIL: 含破折号 ——")
    else:
        print("  ok: 无破折号 ——")
    if "**" in readme:
        ok = False
        print("  FAIL: 含粗体 **")
    else:
        print("  ok: 无粗体 **")

    # 3. 配图引用真实存在
    refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", readme)
    print("配图引用数: %d" % len(refs))
    for r in refs:
        p = os.path.join(ROOT, r)
        if not os.path.exists(p):
            ok = False
            print("  FAIL: 配图缺失 %s" % r)
        else:
            print("  ok: 配图存在 %s" % r)

    # 4. self-test 块子序列比对
    blocks = re.findall(r"```[^\n]*\n(.*?)```", readme, re.S)
    st_blocks = [b for b in blocks if "self-test PASS" in b]
    expected = open(EXPECTED, encoding="utf-8").read()
    if not st_blocks:
        ok = False
        print("  FAIL: 未找到 self-test 块")
    else:
        merged = "\n".join(st_blocks)
        exp_lines = [l for l in expected.splitlines() if l.strip() != ""]
        idx = 0
        for line in merged.splitlines():
            if idx < len(exp_lines) and line.strip() == exp_lines[idx].strip():
                idx += 1
        if idx == len(exp_lines):
            print("  ok: self-test 块与 EXPECTED_OUT 逐行一致 (%d 行)" % idx)
        else:
            ok = False
            print("  FAIL: self-test 块仅匹配 %d/%d 行" % (idx, len(exp_lines)))

    # 5. 必备小节
    for sec in ["结尾钩子", "复现模块", "讲给别人听", "来源"]:
        if ("## " + sec) not in readme:
            ok = False
            print("  FAIL: 缺小节 ## %s" % sec)
        else:
            print("  ok: 含小节 ## %s" % sec)

    print()
    print("QC PASS" if ok else "QC FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
