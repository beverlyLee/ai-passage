#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向量检索篇 机检脚本（qc_article.py）

检查项：
  1. 正文中文字数 >= 1500
  2. 禁用符：破折号（—/–/――）、粗体（**）
  3. 配图引用 >= 3 且指向真实存在的 @2x.png
  4. 正文里 self-test 输出块与实际脚本 stdout 逐行子序列匹配
  5. 两个脚本实跑：self-test 全 PASS，demo / sim 无异常
"""

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
README = os.path.join(HERE, "README.md")
REPRO = os.path.join(HERE, "code", "repro")
PY = "/Users/liboyang/.workbuddy/binaries/python/versions/3.13.12/bin/python3"

DASHES = ["\u2014", "\u2013", "\u2015", "\u2012"]  # — – ― ‒


def cjk_count(text):
    return sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")


def check_chinese_chars(text):
    n = cjk_count(text)
    ok = n >= 1500
    print("  [字数] 中文字数=%d  (要求>=1500)  %s" % (n, "PASS" if ok else "FAIL"))
    return ok


def check_banned_chars(text):
    found = {d: text.count(d) for d in DASHES if text.count(d) > 0}
    bold = text.count("**")
    ok = (not found) and (bold == 0)
    print("  [禁用符] 破折号=%s 粗体**=%d  %s" % (found if found else "无", bold, "PASS" if ok else "FAIL"))
    return ok


def check_diagrams(text):
    refs = re.findall(r"!\[[^\]]*\]\(([^)]*@2x\.png)\)", text)
    exist = [r for r in refs if os.path.exists(os.path.join(HERE, r))]
    ok = len(exist) >= 3
    print("  [配图] 引用=%d 真实存在=%d  (要求>=3)  %s" % (len(refs), len(exist), "PASS" if ok else "FAIL"))
    return ok


def extract_self_test_block(text):
    blocks = re.findall(r"```[^\n]*\n(.*?)```", text, re.DOTALL)
    for b in blocks:
        if "self-test PASS" in b:
            return b
    return None


def subsequence_match(block, stdout):
    block_lines = [l.rstrip() for l in block.splitlines() if l.strip()]
    out_lines = [l.rstrip() for l in stdout.splitlines() if l.strip()]
    i = 0
    for line in out_lines:
        if i < len(block_lines) and line == block_lines[i]:
            i += 1
    ok = i == len(block_lines)
    print("  [self-test块] 正文行数=%d 命中=%d  %s" % (len(block_lines), i, "PASS" if ok else "FAIL"))
    return ok


def run_script(rel, args):
    cmd = [PY, os.path.join(REPRO, rel)] + args
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=REPRO)
    return p.returncode, p.stdout, p.stderr


def main():
    with open(README, encoding="utf-8") as f:
        text = f.read()

    print("===== 向量检索篇 QC =====")
    results = []
    results.append(check_chinese_chars(text))
    results.append(check_banned_chars(text))
    results.append(check_diagrams(text))

    # self-test 块子序列比对
    block = extract_self_test_block(text)
    if block is None:
        print("  [self-test块] 未找到包含 self-test PASS 的代码块  FAIL")
        results.append(False)
    else:
        rc, out, err = run_script("vector_retrieval_core.py", ["--self-test"])
        if rc != 0:
            print("  [self-test块] 脚本运行失败: %s" % err)
            results.append(False)
        else:
            results.append(subsequence_match(block, out))

    # 脚本实跑
    rc1, _, err1 = run_script("vector_retrieval_core.py", [])
    print("  [脚本] core demo  rc=%d  %s" % (rc1, "PASS" if rc1 == 0 else "FAIL " + err1))
    rc2, _, err2 = run_script("vector_retrieval_sim.py", [])
    print("  [脚本] sim       rc=%d  %s" % (rc2, "PASS" if rc2 == 0 else "FAIL " + err2))
    results.append(rc1 == 0 and rc2 == 0)

    print("===== 汇总 =====")
    print("ALL PASS" if all(results) else "SOME FAIL")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
