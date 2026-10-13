#!/usr/bin/env python3
"""机检之三 README：配图存在 / 中文字数 / 禁用符号 / 预期输出与实跑 stdout 子序列匹配。"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
README = os.path.join(ROOT, "README.md")
DIAGRAM = os.path.join(ROOT, "diagram")
REPRO = os.path.join(ROOT, "code", "repro")

REQUIRED_PNG = [
    "01_state_is_map@2x.png",
    "02_channel_strategies@2x.png",
    "03_update_state@2x.png",
]


def step1_png():
    missing = [p for p in REQUIRED_PNG if not os.path.exists(os.path.join(DIAGRAM, p))]
    assert not missing, f"缺失配图: {missing}"
    print(f"[1] 配图齐全: {len(REQUIRED_PNG)} 张 @2x.png")


def step2_chinese():
    text = open(README, encoding="utf-8").read()
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    print(f"[2] 中文字数: {len(cjk)}")
    assert len(cjk) >= 1500, "中文字数偏少，疑似未完成正文"


def step3_forbidden():
    text = open(README, encoding="utf-8").read()
    for ch in ["—", "–", "——"]:
        assert ch not in text, f"正文含禁用符号 {ch!r}"
    assert "**" not in text, "正文含 ** 粗体语法"
    print("[3] 无破折号 / 无粗体语法")


def step4_expected_match():
    text = open(README, encoding="utf-8").read()
    segments = text.split("```")
    blocks = [segments[i] for i in range(1, len(segments), 2)]
    expected = None
    for b in blocks:
        if "final.messages" in b:
            expected = [ln for ln in b.strip().splitlines() if ln.strip()]
            break
    assert expected, "未在 README 找到预期输出代码块"

    cp_txt = os.path.join(REPRO, "cp.txt")
    if not os.path.exists(cp_txt):
        subprocess.run(
            ["mvn", "-q", "-o", "dependency:build-classpath", "-Dmdep.outputFile=cp.txt"],
            cwd=REPRO, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    cmd = (
        f"cd {REPRO} && mvn -q -o compile "
        f"&& CP=\"target/classes:$(cat cp.txt)\" "
        f"&& java -cp \"$CP\" org.example.langgraph4j.Demo3 2>/dev/null"
    )
    out = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    stdout = [ln for ln in out.stdout.strip().splitlines() if ln.strip()]

    idx = 0
    for eline in expected:
        found = False
        while idx < len(stdout):
            if eline == stdout[idx]:
                found = True
                idx += 1
                break
            idx += 1
        assert found, f"预期输出未在实跑 stdout 中按序匹配: {eline!r}"
    print(f"[4] 预期输出 {len(expected)} 行与实跑 stdout 子序列匹配通过")


if __name__ == "__main__":
    try:
        step1_png()
        step2_chinese()
        step3_forbidden()
        step4_expected_match()
    except AssertionError as e:
        print(f"QC FAIL: {e}")
        sys.exit(1)
    print("QC ALL PASS")
