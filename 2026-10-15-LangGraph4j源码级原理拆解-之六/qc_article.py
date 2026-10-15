#!/usr/bin/env python3
# 机检：中文字数、禁用符（破折号/粗体）、配图齐全且存在、精确预期输出子序列匹配
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
README = os.path.join(HERE, "README.md")
EXP = os.path.join(HERE, "code", "repro", "EXPECTED_OUT.txt")


def check_basic():
    ok = True
    text = open(README, encoding="utf-8").read()

    chinese = re.findall(r"[一-鿿]", text)
    if len(chinese) < 1500:
        print(f"FAIL 中文字数 {len(chinese)} < 1500")
        ok = False
    else:
        print(f"PASS 中文字数 {len(chinese)}")

    bads = [("—", "em dash"), ("–", "en dash"), ("——", "double dash"), ("**", "bold")]
    hit = False
    for ch, name in bads:
        if ch in text:
            print(f"FAIL 含禁用符 {name}")
            hit = True
            ok = False
    if not hit:
        print("PASS 无禁用符（破折号/粗体）")

    refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    pngs = [r for r in refs if r.endswith(".png")]
    if len(pngs) < 3:
        print(f"FAIL 配图数 {len(pngs)} < 3")
        ok = False
    else:
        print(f"PASS 配图数 {len(pngs)}")
    for r in pngs:
        p = os.path.join(HERE, r)
        if not os.path.exists(p):
            print(f"FAIL 配图缺失 {r}")
            ok = False
        else:
            print(f"PASS 配图存在 {r}")
    return ok


def check_output():
    text = open(README, encoding="utf-8").read()
    if "精确预期输出" not in text:
        print("FAIL 缺「精确预期输出」标记")
        return False
    expected = open(EXP, encoding="utf-8").read().strip().splitlines()
    blocks = re.findall(r"```[^\n]*\n(.*?)```", text, re.S)
    found = []
    for b in blocks:
        for line in b.splitlines():
            line = line.strip()
            if line in expected:
                found.append(line)
    missing = [e for e in expected if e not in found]
    if not missing:
        print("PASS 预期输出子序列匹配")
        return True
    else:
        print("FAIL 预期输出未匹配:", missing)
        return False


if __name__ == "__main__":
    a = check_basic()
    b = check_output()
    if a and b:
        print("QC ALL PASS")
        sys.exit(0)
    else:
        print("QC FAIL")
        sys.exit(1)
