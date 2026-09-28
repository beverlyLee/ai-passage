#!/usr/bin/env python3
"""第33篇之四配套脚本：直接加载 laya/lang.py 真实源码，跑语言/脚本检测。

laya/lang.py 是纯标准库（re / unicodedata），没有任何 torch 依赖，所以这里用 importlib
直接按文件加载，不被 laya 包的其他重型 import 拖下水。你看到的输出就是仓库里真实跑出来的。

运行：
    python3 demo_lang.py --self-test     # 断言与真实输出对齐，全过打印 self-test PASS
    python3 demo_lang.py                 # 打印一组检测样例

源码对照：laya/lang.py 的 analyse(575-627) / is_english(630-632)。
检测只在意一件事：这是英文拉丁文本，还是英文 checkpoint 读不了的东西。脚本检测是精确的
（25 个 Unicode 范围），拉丁脚本下的语言猜测是停用词/变音符号启发式，明确是 best-effort。
"""

import importlib.util
import os
import sys

# laya 源码仓库里 lang.py 的绝对路径；如果你的 laya 源码在别处，改这一行即可。
_LANG_PATH = os.environ.get(
    "LAYA_LANG_PATH",
    "/tmp/laya-src/laya/lang.py",
)


def _load_lang():
    if not os.path.exists(_LANG_PATH):
        raise RuntimeError(
            "找不到 laya/lang.py：请把 LAYA_LANG_PATH 指向你的 laya 源码仓库里的 lang.py\n"
            "（例：export LAYA_LANG_PATH=/path/to/laya/laya/lang.py）"
        )
    spec = importlib.util.spec_from_file_location("laya_lang_real", _LANG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_lang = _load_lang()

# 把真实函数暴露给外部调用，便于在文章正文里直接引用。
analyse = _lang.analyse
is_english = _lang.is_english


def _demo():
    samples = [
        "I was charged twice for the same order.",
        "Mein Konto wurde zweimal belastet.",
        "Bonjour, je voudrais annuler ma commande.",
        "机器眼里没有脸，只有4096个数。",
        "Quero cancelar minha assinatura agora.",
        "C",  # 不命名语言的 $LANG 值 -> 弃权，整个 state 无字母时走 default
    ]
    print("== 真实 lang.analyse 输出 ==")
    for s in samples:
        a = analyse(s)
        print("  文本: %-44r" % (s[:44]))
        print("    脚本=%s 语言=%s 是英文=%s 非拉丁占比=%.2f 语言未定=%s"
              % (a["script"], a["language"], a["is_english"],
                 float(a["non_latin_fraction"]), a["language_undecided"]))

    # 混合片段：葡萄牙语工单 + 英文堆栈，整体会被英文淹没，但逐段扫描能抓住葡语那一行
    print("\n== 混合片段检测（葡语工单 + 英文堆栈）==")
    state = {
        "message": "Quero cancelar minha assinatura, cobranca duplicada.",
        "stack": "Traceback (most recent call last):\n  File \"app.py\", line 12\nValueError: already cancelled",
    }
    a = analyse(state)
    print("    脚本=%s 是英文=%s 语言=%s" % (a["script"], a["is_english"], a["language"]))
    print("    被抓出的非英文段: %r" % (a.get("mixed_segment"),))


def _self_test():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    # 这些期望值来自本机真实运行 lang.py 的输出（见上文 _demo 的同类输入）
    check(analyse("I was charged twice for the same order.")["is_english"] is True,
          "英文句子应判为英文")
    check(analyse("Mein Konto wurde zweimal belastet.")["is_english"] is False,
          "德文句子应判为非英文")
    check(analyse("Bonjour, je voudrais annuler ma commande.")["is_english"] is False,
          "法文句子应判为非英文")
    check(analyse("Quero cancelar minha assinatura agora.")["is_english"] is False,
          "葡文句子应判为非英文")
    # 中文：脚本是非拉丁（han），is_english 必然 False
    zh = analyse("机器眼里没有脸，只有4096个数。")
    check(zh["script"] != "latin", "中文脚本应为非拉丁（实际 %r）" % zh["script"])
    check(zh["is_english"] is False, "中文应判为非英文")
    # is_english 包装
    check(is_english("Hello world") is True, "is_english('Hello world') 应为 True")
    # 较长的法文句子才足以被停用词启发式识别为 fr；过短的 "Bonjour le monde" 证据不足会判 language_undecided
    check(is_english("Bonjour, je voudrais annuler ma commande.") is False,
          "is_english(法文长句) 应为 False")
    # 混合片段：英文主体 + 一段葡语短字段。整体被英文淹没判为英文，但逐段扫描抓出葡语那一行
    state = {
        "body": ("I was charged twice for the same order and opened a ticket. "
                 "The system shows the error below. Please review the billing entry and let me know. "
                 "I have attached the logs. This has happened three times this month."),
        "note": "Quero cancelar minha assinatura.",
    }
    a = analyse(state)
    check(a["is_english"] is False, "英文主体+葡语短字段混合态应判为非英文")
    check(bool(a.get("mixed_segment")), "应抓出非英文段 mixed_segment")

    if fails:
        print("self-test FAIL")
        for f in fails:
            print("  - " + f)
        return 1
    print("self-test PASS")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    _demo()
