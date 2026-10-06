"""之八 正文 QC：剥离代码块后查禁用符号与粗体、查必需小节、查配图引用、跑 self-test。

运行：/tmp/lc132/bin/python qc_article.py
"""

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARTICLE = os.path.join(HERE, "正文.md")
CODE = os.path.join(HERE, "code", "streaming_and_passthrough.py")

# 禁用符号（全角破折号、半角破折号、双连）
BANNED_CHARS = ["\u2014", "\u2013", "\u2014\u2014"]
# 夸张承诺关键词（铁律 #6：严禁夸大 / 量化承诺）
CLAIM_WORDS = ["省90%", "节省90%", "提升10倍", "10倍", "一定", "绝对不会", "永不"]


def strip_code_blocks(text: str) -> str:
    # 先去围栏代码块 ``` ... ```
    no_fence = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    # 再去行内代码 ` ... `
    no_inline = re.sub(r"`[^`]*`", "", no_fence)
    return no_inline


def check_banned_chars(clean: str) -> list[str]:
    hits = []
    for ch in BANNED_CHARS:
        if ch in clean:
            hits.append(f"正文（去代码块）含禁用符号 {ch!r}")
    return hits


def check_bold(clean: str) -> list[str]:
    hits = []
    # 去代码块后若仍有 ** 或 __ 连续，视为粗体违规
    if "**" in clean:
        hits.append("正文（去代码块）含 ** 疑似粗体")
    if "__" in clean:
        hits.append("正文（去代码块）含 __ 疑似粗体")
    return hits


def check_required_sections(text: str) -> list[str]:
    required = ["## 结尾钩子", "## 复现模块", "三个真踩过的坑"]
    hits = []
    for sec in required:
        if sec not in text:
            hits.append(f"缺必需小节：{sec}")
    return hits


def check_diagram_refs(text: str) -> list[str]:
    # ![...](diagram/xxx@2x.png)
    pat = re.compile(r"!\[[^\]]*\]\((diagram/[^)]+)\)")
    refs = pat.findall(text)
    hits = []
    if len(refs) < 2:
        hits.append(f"配图引用不足 2 张，实际 {len(refs)} 张")
    for ref in refs:
        if "@" not in ref:
            hits.append(f"配图引用未含 @ 标记：{ref}")
        if not ref.endswith("@2x.png"):
            hits.append(f"配图引用未指向 @2x.png：{ref}")
        p = os.path.join(HERE, ref)
        if not os.path.exists(p):
            hits.append(f"配图引用文件不存在：{ref}")
    return hits


def check_chinese_count(clean: str) -> list[str]:
    cn = re.findall(r"[\u4e00-\u9fff]", clean)
    hits = []
    if len(cn) < 4000:
        hits.append(f"正文中文字数不足 4000，实际 {len(cn)}")
    return hits


def check_claim_words(clean: str) -> list[str]:
    hits = []
    for w in CLAIM_WORDS:
        if w in clean:
            hits.append(f"疑似夸张承诺词：{w}")
    return hits


def run_self_test() -> list[str]:
    hits = []
    if not os.path.exists(CODE):
        hits.append(f"复现脚本不存在：{CODE}")
        return hits
    try:
        out = subprocess.run(
            [sys.executable, CODE, "--self-test"],
            capture_output=True,
            text=True,
            cwd=HERE,
            timeout=120,
        )
    except Exception as e:  # noqa: BLE001
        hits.append(f"运行 self-test 异常：{e}")
        return hits
    if out.returncode != 0:
        hits.append(f"self-test 非零退出：{out.stderr.strip()}")
    if "ALL self-test PASS" not in out.stdout:
        hits.append(f"self-test 未输出全绿：{out.stdout.strip()}")
    return hits


def main() -> int:
    if not os.path.exists(ARTICLE):
        print(f"正文不存在：{ARTICLE}")
        return 1
    text = open(ARTICLE, encoding="utf-8").read()
    clean = strip_code_blocks(text)

    errors: list[str] = []
    errors += check_banned_chars(clean)
    errors += check_bold(clean)
    errors += check_required_sections(text)
    errors += check_diagram_refs(text)
    errors += check_chinese_count(clean)
    errors += check_claim_words(clean)
    errors += run_self_test()

    if errors:
        print("QC FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("QC PASS: 禁用符号/粗体/必需小节/配图引用(含@与@2x.png且文件存在)/中文字数/self-test 全绿")
    return 0


if __name__ == "__main__":
    sys.exit(main())
