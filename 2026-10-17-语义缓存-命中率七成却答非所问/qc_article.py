#!/usr/bin/env python3
# 语义缓存文章机检：中文字数、禁用符、配图引用、self-test 输出子序列比对、脚本实跑。
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
README = os.path.join(HERE, "README.md")
REPRO = os.path.join(HERE, "code", "repro")
PY = "/Users/liboyang/.workbuddy/binaries/python/versions/3.13.12/bin/python3"

fail = []


def check_chinese_words():
    txt = open(README, encoding="utf-8").read()
    n = len(re.findall(r"[一-鿿]", txt))
    print("中文字数: %d" % n)
    if n < 1500:
        fail.append("中文字数不足 1500")


def check_forbidden():
    txt = open(README, encoding="utf-8").read()
    if "——" in txt or "—" in txt or "–" in txt:
        fail.append("出现破折号（——/—/–）")
    if "**" in txt:
        fail.append("出现加粗标记（**）")
    print("禁用符检查: %s" % ("OK" if not fail else "FAIL"))


def check_images():
    txt = open(README, encoding="utf-8").read()
    imgs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", txt)
    print("配图引用数: %d -> %s" % (len(imgs), imgs))
    if len(imgs) < 3:
        fail.append("配图引用少于 3 张")
    for rel in imgs:
        p = os.path.join(HERE, rel)
        if not os.path.exists(p):
            fail.append("配图文件不存在: " + rel)


def check_selftest_block():
    txt = open(README, encoding="utf-8").read()
    # 抽取所有 fenced 代码块
    blocks = re.findall(r"```[^\n]*\n(.*?)```", txt, re.DOTALL)
    target = None
    for b in blocks:
        if "ALL SELF-TESTS PASSED" in b:
            target = b
            break
    if target is None:
        fail.append("未找到含 ALL SELF-TESTS PASSED 的预期输出块")
        return
    block_lines = [ln.strip() for ln in target.splitlines() if ln.strip()]
    # 实跑两个脚本的 --self-test 并合并 stdout
    outs = []
    for script in ["semantic_cache_core.py", "semantic_cache_sim.py"]:
        r = subprocess.run([PY, os.path.join(REPRO, script), "--self-test"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            fail.append("脚本 self-test 非零退出: " + script)
            return
        outs.append(r.stdout)
    combined = "\n".join(outs)
    combined_lines = [ln.strip() for ln in combined.splitlines()]
    # 子序列逐行匹配：block 的每一行按序出现在 combined 中
    i = 0
    for bl in block_lines:
        found = False
        while i < len(combined_lines):
            if combined_lines[i] == bl:
                found = True
                i += 1
                break
            i += 1
        if not found:
            fail.append("预期输出行未在脚本实跑 stdout 中匹配: " + bl)
            return
    print("self-test 块子序列比对: OK")


def check_scripts_run():
    for script in ["semantic_cache_core.py", "semantic_cache_sim.py"]:
        r = subprocess.run([PY, os.path.join(REPRO, script)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            fail.append("脚本演示运行非零退出: " + script)
    print("脚本演示运行: %s" % ("OK" if not fail else "FAIL"))


def main():
    check_chinese_words()
    check_forbidden()
    check_images()
    check_selftest_block()
    check_scripts_run()
    print("-" * 40)
    if fail:
        print("QC FAILED:")
        for f in fail:
            print("  - " + f)
        return 1
    print("QC ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
