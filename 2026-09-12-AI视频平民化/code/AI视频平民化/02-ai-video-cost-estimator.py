#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02-ai-video-cost-estimator.py
------------------------------------------------------------------
论点 5「分发平民化闭环」的成本量级估算：同样一段视频，AI 生成侧 vs
传统专业制作，成本在什么量级。

重要：这是基于公开 API 刊例价的**量级估算**，不是精确报价。
实际成本取决于分辨率、时长、是否含实拍/演员/场地、后期复杂度。
正文与本文都**不承诺"成本下降 90%"之类的精确数字**——只给可复现的
计算口径，让你自己代入假设。

公开 API 刊例价（已核实）：
  - 通义万相 Wan3.0 API：480P 0.3 / 720P 0.6 / 1080P 1.2 元/秒
  - 可灵 Kling：5s/720p ≈ 10 credits，单条 5–15s 约 $2.10–4.20
    （本脚本用近似每秒价，标注为"近似"，以通义万相为精确基准）
  - 传统专业制作：本脚本用 --traditional-per-min 参数，默认 30000 元/分钟
    （经验下限，含演员/场地/后期；请按需替换）

自检门控（铁律：只在全默认或显式 --self-test 时断言）：
  python3 02-ai-video-cost-estimator.py --self-test
"""

import argparse

# 通义万相 Wan3.0 API 官方刊例价（元/秒），已核实
WAN_PRICE_PER_SEC = {480: 0.3, 720: 0.6, 1080: 1.2}
# 可灵 Kling 近似每秒价（元/秒，标注为近似，非官方精确口径）
KLING_PRICE_PER_SEC = {480: 0.3, 720: 0.5, 1080: 0.7}

DEFAULT_TRADITIONAL_PER_MIN = 30_000  # 元/分钟，传统专业制作经验下限


def ai_cost(seconds, res, provider):
    if provider == "wan":
        price = WAN_PRICE_PER_SEC[res]
        exact = True
    elif provider == "kling":
        price = KLING_PRICE_PER_SEC[res]
        exact = False
    else:
        raise ValueError(f"unknown provider: {provider}")
    return seconds * price, exact, price


def run(seconds, res, provider, trad_per_min):
    cost, exact, price = ai_cost(seconds, res, provider)
    trad = (seconds / 60.0) * trad_per_min
    ratio = trad / cost if cost > 0 else float("inf")
    tag = "（精确，通义万相刊例）" if exact else "（近似，可灵）"
    print("=" * 62)
    print(f"AI 视频成本量级估算：{seconds}s / {res}P / {provider}{tag}")
    print("=" * 62)
    print(f"  AI 生成侧        : {cost:.2f} 元  ({price} 元/秒)")
    print(f"  传统专业制作(估) : {trad:,.0f} 元  ({trad_per_min:,} 元/分钟 × {seconds/60:.2f}分)")
    print(f"  量级比值         : 传统 / AI ≈ {ratio:,.0f}x")
    print("-" * 62)
    print("  ⚠ 量级估算，非精确报价；传统侧依赖 --traditional-per-min 假设")
    print("  ⚠ 本文不承诺'成本下降 90%'之类的精确数字")
    print("=" * 62)
    return cost, trad, ratio


def self_check():
    """仅在 --self-test 或全默认场景运行；失败即非零退出，可挂 CI。"""
    # 不变式 1：通义万相刊例价内部关系（防手抄错误，对应第19篇教训）
    assert WAN_PRICE_PER_SEC[1080] == 4 * WAN_PRICE_PER_SEC[480], "1080P 应为 480P 的 4 倍"
    assert WAN_PRICE_PER_SEC[720] == 2 * WAN_PRICE_PER_SEC[480], "720P 应为 480P 的 2 倍"
    # 不变式 2：分辨率越高单价越高
    assert (WAN_PRICE_PER_SEC[480] < WAN_PRICE_PER_SEC[720]
            < WAN_PRICE_PER_SEC[1080]), "分辨率-单价单调性异常"
    # 不变式 3：默认场景数值（直接算，避免重复打印表格）
    cost, _exact, _price = ai_cost(60, 1080, "wan")
    trad = (60 / 60.0) * DEFAULT_TRADITIONAL_PER_MIN
    ratio = trad / cost
    assert abs(cost - 72.0) < 1e-6, f"默认 AI 成本应为 72.00，实际 {cost}"
    assert abs(trad - 30_000.0) < 1e-6, f"默认传统成本应为 30000，实际 {trad}"
    assert ratio > 100, "默认场景量级下降应 >100x（量级）"
    print(f"[SELF-CHECK] 02 通过：60s/1080P 通义万相=72.00元，传统≈30000元，"
          f"量级比值≈{ratio:,.0f}x（量级，非精确降幅）。")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--res", type=int, choices=[480, 720, 1080], default=1080)
    ap.add_argument("--provider", type=str, choices=["wan", "kling"], default="wan")
    ap.add_argument("--traditional-per-min", type=float,
                    default=DEFAULT_TRADITIONAL_PER_MIN)
    ap.add_argument("--self-test", action="store_true",
                    help="强制回到默认场景并跑断言")
    args = ap.parse_args()

    run(args.seconds, args.res, args.provider, args.traditional_per_min)

    run_check = args.self_test or (
        args.seconds == 60.0
        and args.res == 1080
        and args.provider == "wan"
        and args.traditional_per_min == DEFAULT_TRADITIONAL_PER_MIN
    )
    if run_check:
        self_check()
