#!/usr/bin/env python3
"""
机检：LangGraph4j 源码级原理拆解 之一
校验项：
1) 禁用符号：中文破折号 —— / — / – 不得出现
2) 不得出现 Markdown 粗体 **...**
3) 正文配图引用必须为 diagram/*.@2x.png 且文件真实存在
4) 中文字数统计（仅报告，不低于 1500 视为达标）
5) 正文「精确预期输出」代码块与实际 stdout 逐行子序列匹配
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTICLE = os.path.join(ROOT, "README.md")
DIAGRAM_DIR = os.path.join(ROOT, "diagram")
REPRO_DIR = os.path.join(ROOT, "code", "repro")

EM_DASH = "—"   # U+2014
EN_DASH = "–"   # U+2013

def main():
    errors = []
    with open(ARTICLE, encoding="utf-8") as f:
        text = f.read()

    # 1) 禁用符号
    if EM_DASH in text:
        n = text.count(EM_DASH)
        errors.append(f"出现中文破折号(—)共 {n} 处")
    if EN_DASH in text:
        n = text.count(EN_DASH)
        errors.append(f"出现短破折号(–)共 {n} 处")

    # 2) 粗体 **...**
    if re.search(r"\*\*", text):
        n = len(re.findall(r"\*\*", text))
        errors.append(f"出现 Markdown 粗体标记(**)共 {n} 处")

    # 3) 配图引用真实存在
    refs = re.findall(r"!\[[^\]]*\]\((diagram/[^)]+)\)", text)
    if not refs:
        errors.append("未找到任何配图引用")
    for ref in refs:
        p = os.path.join(ROOT, ref)
        if not ref.endswith("@2x.png"):
            errors.append(f"配图引用未按 @2x.png 命名: {ref}")
        if not os.path.isfile(p):
            errors.append(f"配图文件不存在: {ref}")

    # 4) 中文字数
    han = re.findall(r"[一-鿿]", text)
    han_count = len(han)
    if han_count < 1500:
        errors.append(f"中文字数 {han_count} 低于 1500")

    # 5) 预期输出与实跑 stdout 逐行子序列匹配
    # 提取「精确预期输出」小节内的代码块
    m = re.search(r"精确预期输出：\s*```\n(.*?)```", text, re.S)
    if not m:
        errors.append("未找到「精确预期输出」代码块")
    else:
        expected_lines = [ln.rstrip() for ln in m.group(1).splitlines() if ln.strip() != ""]
        # 实跑 Demo1 取 stdout
        cp = os.path.join(REPRO_DIR, "cp.txt")
        if not os.path.isfile(cp):
            errors.append("cp.txt 不存在，先 build-classpath")
        else:
            cmd = f'java -cp "target/classes:$(cat cp.txt)" org.example.langgraph4j.Demo1'
            try:
                out = subprocess.run(cmd, shell=True, cwd=REPRO_DIR,
                                     capture_output=True, text=True, timeout=120)
                stdout = out.stdout
            except Exception as e:
                errors.append(f"实跑 Demo1 失败: {e}")
                stdout = ""
            actual_lines = [ln.rstrip() for ln in stdout.splitlines() if ln.strip() != ""]
            # 预期块每行应为实际输出的子序列（顺序一致、可间隔）
            ai = 0
            for el in expected_lines:
                found = False
                while ai < len(actual_lines):
                    if actual_lines[ai] == el:
                        found = True
                        ai += 1
                        break
                    ai += 1
                if not found:
                    errors.append(f"预期输出行未在实际 stdout 中找到: {el}")

    # 报告
    print(f"配图引用数量: {len(refs)}")
    for ref in refs:
        print(f"  - {ref}  {'OK 存在' if os.path.isfile(os.path.join(ROOT, ref)) else '缺失'}")
    print(f"中文字数: {han_count}")
    if errors:
        print("\nQC FAIL:")
        for e in errors:
            print(f"  [x] {e}")
        sys.exit(1)
    print("\nQC PASS: 无禁用符号、无粗体、配图齐全、中文字数达标、预期输出与实跑一致")

if __name__ == "__main__":
    main()
