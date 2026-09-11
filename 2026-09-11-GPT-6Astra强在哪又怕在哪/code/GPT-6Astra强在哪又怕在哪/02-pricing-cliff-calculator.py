#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02-pricing-cliff-calculator.py
==============================

GPT-6 Astra 原理文配套脚本（第19篇）。

把文章里那条「272K 计费悬崖」算清楚。
核心事实（已 WebSearch 一手核实，5 源一致）：

  gpt-6-astra 定价（每百万 token）：  [输入, 缓存输入, 缓存写, 输出]
    Standard (≤272K 输入) :    $10 / $1   / $12.50 / $50
    Standard (>272K 输入)  :    $20 / $2   / $25    / $75     ← 整请求翻倍
    Batch / Flex (=Standard 50%)：
        ≤272K  :  $5  / $0.50 / $6.25  / $25
        >272K  :  $10 / $1    / $12.50 / $50
    Fast (=Standard 2x)：
        ≤272K  :  $20 / $2   / $25    / $100
        >272K  :  $40 / $4   / $50    / $150

关键规则：
  1. 阈值 272,000 看的是「输入 token 数」（文章采用的口径：缓存输入单独按便宜
     费率计费，不计入悬崖判定）。超过后，*整条请求*（不只是超出部分）按 >272K
     档计费——所以刚跨过阈值，成本就直接翻倍。
  2. 缓存输入 $1/M 是 agent 循环的主费率（命中缓存的那部分最便宜）。
  3. 两个不同口径的倍数，别混：
       - 同形状同 token 量下，快慢档差价 = 「总费用倍数」（本脚本算出 ~4.0x）；
       - 文章标题里那个「8x」是输入费率之比：Fast 长上下文 $40/M ÷
         Batch 短上下文 $5/M。两者不可直接互换。

运行：
    python3 02-pricing-cliff-calculator.py
    python3 02-pricing-cliff-calculator.py --req 273000 271000 0 60000 --tier standard
    python3 02-pricing-cliff-calculator.py --json examples/request_samples.jsonl

无第三方依赖。
"""

import argparse
import json
import sys
import unicodedata

THRESHOLD = 272_000  # 输入侧 token 阈值

# 每档四元组顺序: (输入$/M, 缓存输入$/M, 缓存写$/M, 输出$/M)
TIERS = {
    "standard": {
        "le": (10.0, 1.0, 12.50, 50.0),
        "gt": (20.0, 2.0, 25.0, 75.0),
    },
    "batch": {  # = standard 50%
        "le": (5.0, 0.5, 6.25, 25.0),
        "gt": (10.0, 1.0, 12.50, 37.50),
    },
    "flex": {   # = standard 50%
        "le": (5.0, 0.5, 6.25, 25.0),
        "gt": (10.0, 1.0, 12.50, 37.50),
    },
    "fast": {
        "le": (20.0, 2.0, 25.0, 100.0),
        "gt": (40.0, 4.0, 50.0, 150.0),
    },
}


def compute_cost(input_tok, cached_tok, cached_write_tok, output_tok, tier="standard"):
    """返回 (总费, 是否超过阈值, 命中档四元组)。"""
    if tier not in TIERS:
        raise ValueError(f"未知档位: {tier}，可选 {list(TIERS)}")
    # 悬崖判定只看「输入 token 数」；缓存输入另按便宜费率计费，不计入阈值。
    over = input_tok > THRESHOLD
    inp, cin, cw, out = TIERS[tier]["gt" if over else "le"]
    cost = (
        input_tok / 1e6 * inp
        + cached_tok / 1e6 * cin
        + cached_write_tok / 1e6 * cw
        + output_tok / 1e6 * out
    )
    return cost, over, (inp, cin, cw, out)


def fmt(cost):
    return f"${cost:,.2f}"


def dwidth(s):
    """终端显示宽度：CJK 全角字符按 2 列计，否则列会错位。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def ljust_d(s, width):
    return s + " " * max(0, width - dwidth(s))


def main():
    ap = argparse.ArgumentParser(description="GPT-6 Astra 272K 计费悬崖计算器")
    ap.add_argument("--req", type=int, nargs=4, metavar=("INPUT", "CACHED", "CACHED_WRITE", "OUTPUT"),
                    help="单条请求: 输入 缓存输入 缓存写 输出 (token)")
    ap.add_argument("--tier", default="standard", choices=list(TIERS))
    ap.add_argument("--json", default=None, help="JSONL 批量样本，每行 {name,tier,input,cached,cached_write,output}")
    args = ap.parse_args()

    if args.json:
        with open(args.json, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                o = json.loads(line)
                c, over, rate = compute_cost(
                    o["input"], o.get("cached", 0), o.get("cached_write", 0), o["output"], o.get("tier", "standard")
                )
                flag = " >272K(整请求翻倍)" if over else " ≤272K"
                print(f"{ljust_d(o.get('name','?'), 30)} "
                      f"{ljust_d(o.get('tier','standard'), 9)} {fmt(c):>12}  {flag}")
        return 0

    if args.req:
        c, over, rate = compute_cost(*args.req, args.tier)
        print(f"档位={args.tier}  输入侧={args.req[0]+args.req[1]:,}tok  "
              f"超过阈值={over}")
        print(f"命中费率 $/M (输入,缓存输入,缓存写,输出) = {rate}")
        print(f"本次请求费用 = {fmt(c)}")
        return 0

    # 默认演示：仅输入 token 跨过 272K 阈值，成本直接翻倍
    print("演示：同一请求，仅「输入 token」从 271K 跨到 273K（约 +0.7% 量）")
    print("（隔离实验：输出置 0，只为单独看输入侧的整请求重定价）")
    print("-" * 64)
    for label, inp in [("A: 271K 输入(≤272K)", 271_000), ("B: 273K 输入(>272K)", 273_000)]:
        c, over, _ = compute_cost(inp, 0, 0, 0, "standard")
        print(f"{ljust_d(label, 22)} 超过阈值={ljust_d(str(over), 5)} 费用={fmt(c)}")
    a, _, _ = compute_cost(271_000, 0, 0, 0, "standard")
    b, _, _ = compute_cost(273_000, 0, 0, 0, "standard")
    mult = b / a
    print("-" * 64)
    print(f"倍数: B / A = {mult:.2f}x   （仅多 0.7% 输入量，成本翻 ~{mult:.1f} 倍）")
    print()

    # 缓存输入 $1/M 是 agent 循环主费率：对比「全量重算」vs「命中缓存」
    print("演示：agent 循环 30 轮，每轮输入 200K（其中 190K 命中缓存）+ 输出 60K")
    print("-" * 64)
    no_cache, _, _ = compute_cost(200_000, 0, 0, 60_000, "standard")
    with_cache, _, _ = compute_cost(10_000, 190_000, 0, 60_000, "standard")
    print(f"单轮 全量重算(无缓存) : {fmt(no_cache)}")
    print(f"单轮 命中缓存($1/M)   : {fmt(with_cache)}")
    print(f"单轮 省下            : {fmt(no_cache - with_cache)}  ({(1 - with_cache/no_cache)*100:.1f}%)")
    print(f"30 轮合计 无缓存      : {fmt(no_cache * 30)}")
    print(f"30 轮合计 命中缓存    : {fmt(with_cache * 30)}")
    print(f"30 轮合计 省下        : {fmt((no_cache - with_cache) * 30)}")
    print()

    # 最坏组合：Fast + 长上下文，对比同形状的 Batch
    print("演示：最坏 vs 最省（同为 300K 输入 + 150K 输出的 token 形状）")
    print("-" * 64)
    worst, _, rw = compute_cost(300_000, 0, 0, 150_000, "fast")        # >272K fast
    best, _, rb = compute_cost(300_000, 0, 0, 150_000, "batch")        # >272K batch
    print(f"Fast  长上下文 : {fmt(worst)}   输入费率 ${rw[0]:.0f}/M")
    print(f"Batch 长上下文 : {fmt(best)}   输入费率 ${rb[0]:.0f}/M")
    print(f"总费用倍数: {worst/best:.2f}x")
    # 文章引用的「8x」出自输入费率：Fast 长上下文 $40/M vs Batch 短上下文 $5/M
    rate_fast_long = TIERS["fast"]["gt"][0]      # 40
    rate_batch_short = TIERS["batch"]["le"][0]   # 5
    print(f"输入费率倍数（Fast 长上下文 $40/M ÷ Batch 短上下文 $5/M）: "
          f"{rate_fast_long/rate_batch_short:.0f}x")

    # 自检
    a2, over_a, _ = compute_cost(271_000, 0, 0, 0, "standard")
    b2, over_b, _ = compute_cost(273_000, 0, 0, 0, "standard")
    assert over_a is False and over_b is True, "自检失败：阈值判定错误"
    assert b2 / a2 > 1.9, "自检失败：悬崖倍数应接近 2x"
    # 缓存输入不计入阈值：即便缓存很大，只要输入侧 ≤272K 仍按便宜档
    _, over_c, _ = compute_cost(100_000, 500_000, 0, 0, "standard")
    assert over_c is False, "自检失败：缓存输入不应计入悬崖阈值"
    # 缓存主费率检查
    _, _, rate_le = compute_cost(10_000, 190_000, 0, 0, "standard")
    assert rate_le[1] == 1.0, "自检失败：缓存输入应为 $1/M"
    # 不变量：Batch / Flex 必须严格等于 Standard 的一半（对全部四费率 × 两档）
    for t in ("batch", "flex"):
        for band in ("le", "gt"):
            for i, (s, half) in enumerate(zip(TIERS["standard"][band], TIERS[t][band])):
                assert abs(half - s / 2) < 1e-9, (
                    f"自检失败：{t}/{band} 第{i}项应为 Standard 的一半 "
                    f"（Standard={s}，期望={s/2}，实际={half}）"
                )
    # 不变量：Fast 必须严格等于 Standard 的两倍
    for band in ("le", "gt"):
        for i, (s, dbl) in enumerate(zip(TIERS["standard"][band], TIERS["fast"][band])):
            assert abs(dbl - s * 2) < 1e-9, (
                f"自检失败：fast/{band} 第{i}项应为 Standard 的两倍 "
                f"（Standard={s}，期望={s*2}，实际={dbl}）"
            )
    print("\n[SELF-CHECK] OK：阈值判定 / 悬崖 ~2x / 缓存不计阈值 / 缓存输入 $1/M / "
          "Batch·Flex=½Standard / Fast=2×Standard 均正确。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
