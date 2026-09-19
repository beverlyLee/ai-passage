#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01_think_billing.py —— 推理模型「thinking tokens」计费模拟器（纯标准库）

你要解决的真问题：
  推理模型（o1 / o3 / DeepSeek R1 这类）在回答之前，会在内部先走一段「思考链」
  （thinking / reasoning tokens）。这段思考链对调用方**默认不可见**，但账单上它
  **按输出 token 计费**。于是你看到接口只返回 300 个可见 token，账单却按 8000 个
  输出 token 收钱——这就是「看不见的账单」。

本脚本用纯标准库复现这个量级关系，并且：
  - 后端可注入（FakeReasoningBackend），CI 里不依赖任何真实 API。
  - --self-test 跑断言，全绿才算通过。
  - --n 批量跑，打印多个真实 / 模拟问题的账单，验证「effort 越高、隐藏思考越多、
    账单越贵」这个单调关系。

注：价格数字取自各厂商公开定价页（OpenAI o-series、DeepSeek），只用于量级演示，
不保证实时准确；用 --price 可覆盖。
"""

import argparse
import importlib.util
import random
import sys


# ----------------------------------------------------------------------------
# 1. 后端接口（可注入）
# ----------------------------------------------------------------------------
class ReasoningBackend:
    """真实后端的抽象。子类只需实现 chat()，返回隐藏思考 token 数与可见 token 数。

    这里给出基类；CI 与演示全部用 FakeReasoningBackend。真正的 OpenAI / DeepSeek
    客户端只要实现同样的 chat() 即可无缝替换。
    """

    def chat(self, question, effort="medium", seed=0):
        raise NotImplementedError


class FakeReasoningBackend(ReasoningBackend):
    """用确定性伪随机，模拟「思考越深、隐藏 token 越多」的后端。

    effort 决定思考深度档位：
        low    -> 思考短（约 400 隐藏 token）
        medium -> 思考中（约 2000 隐藏 token）
        high   -> 思考长（约 8000 隐藏 token）
    可见回答长度与 effort 弱相关（想得越多，往往也多写一点），但远小于隐藏部分。
    """

    # 各档位隐藏思考 token 的均值
    EFFORT_HIDDEN = {"low": 400, "medium": 2000, "high": 8000}
    EFFORT_VISIBLE = {"low": 180, "medium": 260, "high": 340}

    def chat(self, question, effort="medium", seed=0):
        base_hidden = self.EFFORT_HIDDEN.get(effort, 2000)
        base_visible = self.EFFORT_VISIBLE.get(effort, 260)
        # 用 (seed, len(question), effort) 做确定性扰动，保证同输入同输出
        rnd = random.Random(f"{seed}:{len(question)}:{effort}")
        hidden = int(base_hidden * (0.85 + 0.3 * rnd.random()))
        visible = int(base_visible * (0.9 + 0.2 * rnd.random()))
        return {"hidden_think_tokens": hidden, "visible_tokens": visible}


# ----------------------------------------------------------------------------
# 2. 计费逻辑：隐藏思考 token 按「输出 token」收费
# ----------------------------------------------------------------------------
# 公开定价（USD / 1M tokens），仅用于量级演示。
DEFAULT_PRICES = {
    # 模型: (输入价, 输出价)，输出价同时覆盖可见 token 与隐藏思考 token
    "o1": (15.0, 60.0),
    "o3": (2.0, 8.0),
    "deepseek-r1": (0.55, 2.19),
}


def bill_request(backend, model, question, effort="medium", input_tokens=1200, prices=None):
    """对一次请求出账单。

    关键：billed_output_tokens = visible_tokens + hidden_think_tokens。
    隐藏思考 token 你看不见，但和可见 token 用同一个输出价计费。
    """
    prices = prices or DEFAULT_PRICES
    if model not in prices:
        raise ValueError(f"未知模型 {model!r}，已知：{sorted(prices)}")
    inp_price, out_price = prices[model]

    # 用问题文本长度派生一个稳定的 seed，避免每次跑都不同
    seed = sum(ord(c) for c in question) % 100000
    resp = backend.chat(question, effort=effort, seed=seed)

    visible = resp["visible_tokens"]
    hidden = resp["hidden_think_tokens"]
    billed_output = visible + hidden  # ← 隐藏部分照样计费

    cost_input = input_tokens * inp_price / 1_000_000.0
    cost_output = billed_output * out_price / 1_000_000.0
    total = cost_input + cost_output

    return {
        "model": model,
        "effort": effort,
        "input_tokens": input_tokens,
        "visible_tokens": visible,
        "hidden_think_tokens": hidden,
        "billed_output_tokens": billed_output,
        "cost_input_usd": cost_input,
        "cost_output_usd": cost_output,
        "total_usd": total,
    }


def fmt_money(x):
    return f"${x:,.4f}"


# ----------------------------------------------------------------------------
# 3. 报告
# ----------------------------------------------------------------------------
def report_one(r):
    line = "=" * 56
    print(line)
    print(f"模型={r['model']}  effort={r['effort']}")
    print(f"  输入 token     : {r['input_tokens']:>6}")
    print(f"  可见输出 token : {r['visible_tokens']:>6}   <- 你接口里看到的")
    print(f"  隐藏思考 token : {r['hidden_think_tokens']:>6}   <- 你看不见，但照收")
    print(f"  计费输出 token : {r['billed_output_tokens']:>6}   = 可见 + 隐藏")
    print(f"  输入费用       : {fmt_money(r['cost_input_usd'])}")
    print(f"  输出费用       : {fmt_money(r['cost_output_usd'])}")
    print(f"  本次总账单     : {fmt_money(r['total_usd'])}")
    print(line)


def run_batch(backend, model, questions, efforts, input_tokens=1200):
    rows = []
    for q in questions:
        for ef in efforts:
            r = bill_request(backend, model, q, effort=ef, input_tokens=input_tokens)
            rows.append(r)
            report_one(r)
    return rows


# ----------------------------------------------------------------------------
# 4. 自检
# ----------------------------------------------------------------------------
def _self_test():
    backend = FakeReasoningBackend()

    # (1) 隐藏思考 token 必须被计入账单（这是「看不见的账单」的核心事实）
    r = bill_request(backend, "o3", "1+1 等于几？", effort="high", input_tokens=500)
    assert r["billed_output_tokens"] == r["visible_tokens"] + r["hidden_think_tokens"], \
        "计费输出 token 必须等于 可见 + 隐藏"
    assert r["hidden_think_tokens"] > 0, "high 档位应产生隐藏思考 token"
    assert r["billed_output_tokens"] > r["visible_tokens"], \
        "计费输出必须多于可见输出（隐藏部分被收费）"

    # (2) 同一问题，effort 越高，隐藏 token 越多 -> 输出账单越贵（单调关系）
    low = bill_request(backend, "o3", "今天天气如何", effort="low")
    high = bill_request(backend, "o3", "今天天气如何", effort="high")
    assert high["hidden_think_tokens"] > low["hidden_think_tokens"], \
        "high 应比 low 思考更多"
    assert high["total_usd"] > low["total_usd"], \
        "high 应比 low 更贵"

    # (3) 输出价更高的模型，同样隐藏 token 下账单更贵（o1 输出 $60 vs o3 $8）
    r1 = bill_request(backend, "o1", "解释相对论", effort="high", input_tokens=500)
    r3 = bill_request(backend, "o3", "解释相对论", effort="high", input_tokens=500)
    assert r1["total_usd"] > r3["total_usd"], \
        "o1 输出单价更高，相同量级下应更贵"

    # (4) 确定性：同输入同输出
    a = bill_request(backend, "o3", "x", effort="medium")
    b = bill_request(backend, "o3", "x", effort="medium")
    assert a == b, "相同输入必须产出相同账单"

    print("SELF-TEST PASS")
    return True


# ----------------------------------------------------------------------------
# 5. 入口
# ----------------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(description="推理模型 thinking tokens 计费模拟器")
    p.add_argument("--self-test", action="store_true", help="跑断言自检")
    p.add_argument("--n", type=int, default=0, help="批量跑 N 个内置问题（0=不跑批量）")
    p.add_argument("--model", default="o3", help="o1 / o3 / deepseek-r1")
    p.add_argument("--effort", default="high", help="low / medium / high")
    p.add_argument("--input-tokens", type=int, default=1200)
    args = p.parse_args(argv)

    if args.self_test:
        _self_test()
        return 0

    backend = FakeReasoningBackend()

    if args.n > 0:
        qs = [
            "1+1 等于几？",
            "用一句话介绍 Kubernetes。",
            "把这段 JSON 格式化。",
            "解释一下 transformer 的注意力机制。",
            "帮我写一封请假邮件。",
            "为什么天是蓝的？",
            "计算 23 * 47。",
            "总结一下《三体》的主旨。",
        ][: args.n]
        run_batch(backend, args.model, qs, efforts=["low", "high"],
                  input_tokens=args.input_tokens)
        return 0

    # 默认：演示单个请求
    r = bill_request(backend, args.model, "解释一下上下文窗口是什么。",
                     effort=args.effort, input_tokens=args.input_tokens)
    report_one(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
