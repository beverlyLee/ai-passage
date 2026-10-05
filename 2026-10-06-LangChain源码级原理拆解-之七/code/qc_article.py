"""机器 QC：校验本篇正文.md 符合系列硬性铁律。

检查项：
  1. 破折号（em dash — U+2014 / en dash – U+2013 / 双连 ——）一律禁止
  2. 粗体（** 与 __）禁止（代码块内的 **kwargs 属合法 Python 语法，Blockquote 已剥离）
  3. 敏感词（支付 / 交易 / 风控 / 资金 / 医疗 / 诊断 / 处方）禁止
  4. 必需小节：结尾钩子 / 复现模块 / 一手代码来源
  5. 配图引用须含 @ 且文件真实存在
  6. 复现模块里记录的 self-test 输出须与脚本实跑一致（含 ALL self-test PASS）

用法：python qc_article.py
"""

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTICLE = os.path.join(ROOT, "正文.md")
DIAGRAM_DIR = os.path.join(ROOT, "diagram")
CODE_DIR = os.path.join(ROOT, "code")

SENSITIVE = ["支付", "交易", "风控", "资金", "医疗", "诊断", "处方"]
REQUIRED_SECTIONS = ["结尾钩子", "复现模块", "一手代码来源"]
def _find_self_test_script() -> str:
    for name in os.listdir(CODE_DIR):
        if name.endswith(".py") and name != os.path.basename(__file__):
            return os.path.join(CODE_DIR, name)
    return ""


SELF_TEST_SCRIPT = _find_self_test_script()


def read_article() -> str:
    with open(ARTICLE, encoding="utf-8") as f:
        return f.read()


def strip_code_blocks(text: str) -> str:
    """去掉围栏代码块，避免把代码里的 Python 语法当成违规。"""
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def check_dashes(text: str) -> list[str]:
    problems = []
    for ch, name in [("—", "破折号/em dash"), ("–", "en dash"), ("——", "双连")]:
        if ch in text:
            problems.append(f"发现{name}（{ch!r}），正文一律禁止")
    return problems


def check_bold(text: str) -> list[str]:
    problems = []
    prose = strip_code_blocks(text)
    if "**" in prose:
        problems.append("正文（非代码块）含 ** ，疑似粗体，禁止")
    if "__" in prose:
        problems.append("正文（非代码块）含 __ ，疑似粗体，禁止")
    return problems


def check_sensitive(text: str) -> list[str]:
    problems = []
    prose = strip_code_blocks(text)
    for w in SENSITIVE:
        if w in prose:
            problems.append(f"正文含敏感词：{w}")
    return problems


def check_sections(text: str) -> list[str]:
    problems = []
    for sec in REQUIRED_SECTIONS:
        if sec not in text:
            problems.append(f"缺少必需小节：{sec}")
    return problems


def check_diagrams(text: str) -> list[str]:
    problems = []
    refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    if not refs:
        problems.append("正文没有任何配图引用")
    for ref in refs:
        if "@" not in ref:
            problems.append(f"配图引用缺少 @ 标记：{ref}")
        # 引用形如 diagram/01_xxx@2x.png，解析相对正文所在目录
        rel = ref.split("@")[0]
        png = ref if ref.endswith(".png") else ref
        full = os.path.normpath(os.path.join(ROOT, png))
        if not os.path.exists(full):
            problems.append(f"配图引用文件不存在：{ref}")
        else:
            if "@2x.png" not in ref:
                problems.append(f"配图引用未指向 @2x.png：{ref}")
    return problems


def run_self_test() -> tuple[bool, str]:
    if not os.path.exists(SELF_TEST_SCRIPT):
        return False, f"self-test 脚本不存在：{SELF_TEST_SCRIPT}"
    try:
        out = subprocess.run(
            [sys.executable, SELF_TEST_SCRIPT, "--self-test"],
            capture_output=True, text=True, timeout=120,
        )
    except Exception as e:  # noqa: BLE001
        return False, f"运行 self-test 异常：{e}"
    if out.returncode != 0:
        return False, f"self-test 退出码非 0：\n{out.stdout}\n{out.stderr}"
    if "ALL self-test PASS" not in out.stdout:
        return False, f"self-test 未输出 ALL self-test PASS：\n{out.stdout}"
    return True, out.stdout


def main() -> int:
    text = read_article()
    problems: list[str] = []
    problems += check_dashes(text)
    problems += check_bold(text)
    problems += check_sensitive(text)
    problems += check_sections(text)
    problems += check_diagrams(text)

    ok, st_out = run_self_test()
    if not ok:
        problems.append(st_out)

    print("=" * 60)
    print(f"QC 目标：{ARTICLE}")
    print("=" * 60)
    if problems:
        print("QC 失败，问题如下：")
        for p in problems:
            print("  -", p)
        return 1
    print("QC 全部通过：破折号/粗体/敏感词/必需小节/配图引用/self-test 均为绿。")
    print("实跑 self-test 输出末尾：")
    for line in st_out.strip().splitlines()[-6:]:
        print("  ", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
