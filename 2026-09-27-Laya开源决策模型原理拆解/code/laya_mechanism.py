#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
laya_mechanism.py
=================

用一个能跑的最小实现，把 Laya 决策模型的「核心机制」讲清楚。

Laya 是 Convai Innovations 开源的判断引擎（Apache 2.0，约 421M 参数，非自回归）。
它的关键不是「生成文字」，而是「对一组预先给定的选项打分，再用 softmax 变成分布」。
本文件不加载真实模型，用一个确定性的假 encoder（教学替身）复现这条链路：

    指令在前 -> 每个选项前放一个 [MASK] -> state 放在最后
    一次前向，在每个 [MASK] 位置取出一个打分
    同一个问题的选项之间做 softmax，得到概率分布

真实模型用 ModernBERT-large 当 encoder，本文件用「哈希噪声 + 关键词加权」当替身，
只为了让人看清机制长什么样、三原语（choice/score/noul）的输出形状差在哪。

三种输出形状对齐 HuggingFace 模型卡 convaiinnovations/laya 与 PyPI laya 的 Quickstart：
    choice: {"choice": str, "probabilities": {...}, "confidence": float}
    score : {"score": float, "legend": {...}, "probabilities": {...}, "confidence": float}
    noul  : {"noul": float}   # 只有 0~1 的概率，没有独立的 confidence

用法：
    python3 laya_mechanism.py --self-test
    python3 laya_mechanism.py --demo
    python3 laya_mechanism.py --router
"""

import sys
import json
import math
import hashlib
import unicodedata


# --------------------------------------------------------------------------- #
# 1. 确定性假 encoder：把 (问题, 选项, 状态) 映射成一个 logit（打分）
#    真实 Laya 这一步是 ModernBERT-large 在 [MASK] 位置吐出的隐向量，再过一个线性头。
#    这里用「小哈希噪声 + 关键词加权」当替身，保证可复现、可解释。
# --------------------------------------------------------------------------- #

def _hash_float(key: str) -> float:
    """把任意字符串稳定地映射成 [-0.6, 0.6] 之间的浮点数。"""
    h = hashlib.sha256(key.encode("utf-8")).digest()
    value = int.from_bytes(h[:8], "big") / (2 ** 64)
    return (value * 2 - 1) * 0.6


def _state_signature(state: str) -> str:
    """状态签名：只取正文，忽略大小写与前后空白，保证同一句话打分稳定。"""
    return state.strip().lower()


# choice / noul 选项的关键词：命中越多，该选项的 logit 越高
_KEYWORDS = {
    "department": {
        "billing":  ["bill", "charged", "invoice", "payment", "refund", "double"],
        "technical": ["error", "bug", "crash", "broken", "down", "timeout"],
        "account":   ["login", "password", "account", "locked", "sign in"],
        "sales":     ["buy", "upgrade", "price", "plan", "quote"],
    },
    "is_real_fault": {
        "yes": ["down", "outage", "broken", "crash", "cannot", "can't", "error", "unreachable"],
        "no":  ["question", "how", "wondering", "curious", "idea", "suggestion"],
    },
}

# score（紧急度）的关键词：命中越多，越偏向高刻度
_URGENCY_KEYWORDS = {
    0.0: ["sometime", "whenever", "minor", "later", "no rush"],
    0.5: ["small", "low", "little"],
    1.0: ["soon", "please", "help"],
    1.5: ["urgent", "asap", "important", "blocked"],
    2.0: ["critical", "down", "outage", "broken", "cannot", "can't", "emergency"],
}


def _keyword_logit(state_sig: str, keywords) -> float:
    """统计命中关键词的次数，每个命中加权 +0.9。"""
    words = state_sig.split()
    total = 0.0
    for kw in keywords:
        if kw in words:
            total += 0.9
    return total


def _option_logit(qid: str, option, state_sig: str) -> float:
    base = _hash_float(f"{qid}|{option}|{state_sig}")
    if qid == "department":
        boost = _keyword_logit(state_sig, _KEYWORDS["department"].get(option, []))
        return base + boost
    if qid == "is_real_fault":
        boost = _keyword_logit(state_sig, _KEYWORDS["is_real_fault"].get(option, []))
        return base + boost
    if qid == "urgency":
        # options 是刻度锚点 [0.0, 0.5, 1.0, 1.5, 2.0]
        boost = _keyword_logit(state_sig, _URGENCY_KEYWORDS.get(option, []))
        return base + boost
    return base


def softmax(logits) -> list:
    m = max(logits)
    exps = [math.exp(x - m) for x in logits]
    s = sum(exps)
    return [e / s for e in exps]


# --------------------------------------------------------------------------- #
# 2. 三原语的输出形状
# --------------------------------------------------------------------------- #

def predict(state: str, questions: dict) -> dict:
    """
    对齐 PyPI laya 的 agent.predict(state, questions)：
    一次调用，questions 里所有问题并行打分，返回 result["answers"]。

    output_tokens 恒为 0 是 Laya 的核心卖点之一：判断不要钱，只有输入要计费。
    """
    state_sig = _state_signature(state)
    answers = {}

    for qid, spec in questions.items():
        qtype = spec["type"]
        options = spec["options"]

        logits = [_option_logit(qid, opt, state_sig) for opt in options]
        probs = softmax(logits)

        if qtype == "choice":
            best = max(range(len(options)), key=lambda i: probs[i])
            answers[qid] = {
                "choice": options[best],
                "probabilities": {str(o): round(p, 4) for o, p in zip(options, probs)},
                "confidence": round(max(probs), 4),
            }
        elif qtype == "score":
            # score = 各刻度锚点的概率加权平均；legend 取概率最大的刻度
            score_val = sum(p * o for p, o in zip(probs, options))
            best = max(range(len(options)), key=lambda i: probs[i])
            legend = spec.get("legend", {})
            answers[qid] = {
                "score": round(score_val, 4),
                "legend": legend,
                "probabilities": {str(o): round(p, 4) for o, p in zip(options, probs)},
                "confidence": round(max(probs), 4),
            }
        elif qtype == "noul":
            # noul 只返回 0~1 的概率（"yes" 的概率），没有独立的 confidence。
            yes_idx = options.index("yes") if "yes" in options else 0
            answers[qid] = {"noul": round(probs[yes_idx], 4)}

    input_tokens = len(state_sig) // 4 + len(questions) + 1
    return {
        "answers": answers,
        "usage": {"input_tokens": input_tokens, "output_tokens": 0},
    }


# --------------------------------------------------------------------------- #
# 3. Demo：一条用户反馈消息做工单初筛
#    department (choice) + urgency (score) + is_real_fault (noul)
# --------------------------------------------------------------------------- #

DEMO_QUESTIONS = {
    "department": {
        "type": "choice",
        "options": ["billing", "technical", "account", "sales"],
    },
    "urgency": {
        "type": "score",
        "options": [0.0, 0.5, 1.0, 1.5, 2.0],
        "legend": {0.0: "none", 0.5: "low", 1.0: "medium", 1.5: "high", 2.0: "critical"},
    },
    "is_real_fault": {
        "type": "noul",
        "options": ["yes", "no"],
    },
}


def run_demo():
    state = "My bill was charged twice and I can't reach support, this is urgent!"
    result = predict(state, DEMO_QUESTIONS)
    print("state: " + state)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


# --------------------------------------------------------------------------- #
# 4. 真实接入片段（对照 PyPI laya 的 Quickstart，需联网下载约 808MB 模型）
# --------------------------------------------------------------------------- #

PYPI_QUICKSTART = '''# 真实环境（需 pip install laya，首次会下载约 808MB 的 ModernBERT-large 权重）
# pip install laya
# import laya
# agent = laya.load("convaiinnovations/laya")
#
# state = {"message": "My bill was charged twice and I can't reach support, this is urgent!"}
# questions = {
#     "department": {"type": "choice", "options": ["billing", "technical", "account", "sales"]},
#     "urgency":    {"type": "score",  "options": [0, 1, 2], "legend": {0: "low", 1: "mid", 2: "high"}},
#     "is_real_fault": {"type": "noul"},
# }
# result = agent.predict(state, questions)
# answers = result["answers"]
# # answers["department"]["choice"]      -> "billing"
# # answers["department"]["confidence"]  -> 0.9x
# # answers["urgency"]["score"]          -> 1.x
# # answers["is_real_fault"]["noul"]     -> 0~1 的概率
'''


# --------------------------------------------------------------------------- #
# 5. Router 灾难演示：英文 checkpoint 在 Khmer 上 confident 但全错
# --------------------------------------------------------------------------- #

def _has_khmer(text: str) -> bool:
    """检测是否含有高棉文（Unicode U+1780-U+17FF）。"""
    for ch in text:
        if 0x1780 <= ord(ch) <= 0x17FF:
            return True
    return False


def _has_latin(text: str) -> bool:
    for ch in text:
        if "LATIN" in unicodedata.name(ch, ""):
            return True
    return False


def english_checkpoint_on_foreign(state: str) -> dict:
    """
    模拟「英文专用 checkpoint 碰到高棉文」的文档化灾难：
    它仍然吐出一个高置信度的分布（softmax 永远和为 1，max 就是 confidence），
    但这是在它根本没见过的书写系统上，预测准确率是 0.000。
    这里用退化分布（全部质量压在第一个选项）复现「0.952 信心、0.000 正确」的形态。
    """
    qids = ["department", "urgency", "is_real_fault"]
    answers = {
        "department": {"choice": "billing", "confidence": 0.952,
                       "probabilities": {"billing": 0.952, "technical": 0.016, "account": 0.016, "sales": 0.016}},
        "urgency": {"score": 1.0, "confidence": 0.952,
                    "probabilities": {"0.0": 0.2, "0.5": 0.2, "1.0": 0.952, "1.5": 0.2, "2.0": 0.2},
                    "legend": {0.0: "none", 0.5: "low", 1.0: "medium", 1.5: "high", 2.0: "critical"}},
        "is_real_fault": {"noul": 0.5},
    }
    return {"answers": answers, "usage": {"input_tokens": 999, "output_tokens": 0},
            "_simulated": True, "_note": "英文 checkpoint 在高棉文上实测准确率 0.000，但 confidence 仍报 0.952"}


def router_demo():
    khmer = "គណនីរបស់ខ្ញុំមិនអាចចូលបានទេ សូមជួយដោះស្រាយបន្ទាន់"
    print("收到一条高棉文反馈：")
    print(khmer)
    print()
    print("[不使用 Router] 直接丢给英文 checkpoint：")
    bad = english_checkpoint_on_foreign(khmer)
    print(json.dumps(bad["answers"], ensure_ascii=False, indent=2))
    print("  note: " + bad["_note"])
    print()
    print("[使用 Router] 纯 Python 前置按书写系统选 checkpoint（耗时 < 0.5ms）：")
    if _has_khmer(khmer):
        chosen = "laya-multilingual  (mmBERT-base, 100+ 语言)"
    elif _has_latin(khmer):
        chosen = "laya  (ModernBERT-large, 英文)"
    else:
        chosen = "laya  (ModernBERT-large, 英文)"
    print("  检测到非拉丁书写系统 -> 路由到 " + chosen)
    print("  -> 高棉文走多语言 checkpoint，避免英文权重在陌生脚本上胡说八道")
    return chosen


# --------------------------------------------------------------------------- #
# 6. self-test：把正文要引用的不变量先跑绿
# --------------------------------------------------------------------------- #

def _assert(cond, msg):
    if not cond:
        raise AssertionError("self-test FAILED: " + msg)
    print("  PASS: " + msg)


def run_self_test():
    print("self-test 开始（纯标准库，假 encoder，无需下载模型）")
    # 1) 概率和为 1
    st = "account login password locked"
    r = predict(st, DEMO_QUESTIONS)
    s = sum(r["answers"]["department"]["probabilities"].values())
    _assert(abs(s - 1.0) < 1e-9, "choice 概率分布和为 1")

    # 2) 加选项不破坏机制（第四项是个明显更差的诱饵，argmax 不变、和仍 1）
    base_q = {"department": {"type": "choice", "options": ["billing", "technical", "account"]}}
    decoy_q = {"department": {"type": "choice", "options": ["billing", "technical", "account", "zzz_irrelevant"]}}
    r1 = predict(st, base_q)
    r2 = predict(st, decoy_q)
    _assert(r1["answers"]["department"]["choice"] == r2["answers"]["department"]["choice"],
            "加入诱饵选项后，原三项的 argmax 不变")
    _assert(abs(sum(r2["answers"]["department"]["probabilities"].values()) - 1.0) < 1e-9,
            "加入选项后概率仍和为 1（选项空间请求时定义，加选项不重训）")

    # 3) Noul 没有独立 confidence
    st2 = "the site is down and I cannot reach support"
    r3 = predict(st2, DEMO_QUESTIONS)
    _assert("confidence" not in r3["answers"]["is_real_fault"],
            "noul 输出只含 noul 概率，没有 confidence 键")
    _assert(0.0 <= r3["answers"]["is_real_fault"]["noul"] <= 1.0,
            "noul 取值落在 0~1 区间")

    # 4) 输出免费：output_tokens 恒为 0
    _assert(r3["usage"]["output_tokens"] == 0, "output_tokens == 0（判断不花钱）")

    # 5) Score 落在刻度区间内
    sc = r3["answers"]["urgency"]["score"]
    _assert(min(DEMO_QUESTIONS["urgency"]["options"]) <= sc <= max(DEMO_QUESTIONS["urgency"]["options"]),
            "score 加权值落在刻度最小~最大之间（" + str(min(DEMO_QUESTIONS["urgency"]["options"])) +
            "~" + str(max(DEMO_QUESTIONS["urgency"]["options"])) + "）")

    # 6) 一次调用三问并行，返回三种形状
    ans = r3["answers"]
    _assert(set(ans.keys()) == {"department", "urgency", "is_real_fault"}, "一次调用并行返回三问")
    _assert("choice" in ans["department"] and "confidence" in ans["department"], "choice 形状含 choice+confidence")
    _assert("score" in ans["urgency"] and "legend" in ans["urgency"], "score 形状含 score+legend")
    _assert("noul" in ans["is_real_fault"] and "confidence" not in ans["is_real_fault"], "noul 形状只含 noul")

    print("self-test 全部通过。")


def main():
    args = sys.argv[1:]
    if "--self-test" in args:
        run_self_test()
    elif "--demo" in args:
        run_demo()
    elif "--router" in args:
        router_demo()
    else:
        print("用法: python3 laya_mechanism.py [--self-test | --demo | --router]")
        print("真实接入片段（PyPI laya）：")
        print(PYPI_QUICKSTART)


if __name__ == "__main__":
    main()
