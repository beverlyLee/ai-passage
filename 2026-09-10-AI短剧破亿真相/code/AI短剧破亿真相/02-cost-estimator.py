#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 短剧单集算力成本估算 + 抽卡门禁（对应正文 问题 3 / 坑 3）。

用法:
    python3 02-cost-estimator.py --seconds 15 --price 1.0 --draws 10
    python3 02-cost-estimator.py --seconds 15 --price 1.0 --draws 300 --budget 30

成本模型（正文公式）:
    单次生成成本 = 时长(秒) × 单价(元/秒)
    单集成本     = 抽卡次数 × 单次生成成本
    （抽卡次数已含不合格重抽；重抽无上限 = 成本滚雪球）

门禁:
    --budget 给出每镜头抽卡上限，超出即告警（坑 3：无门禁一部剧亏数万）。

已知边界:
    - 单价取中值（Seedance ~1 元/秒、Sora2 ~1.5、Veo3 ~2.8），落地以厂商最新报价为准。
    - 未含音频/合规/人力，仅为算力侧下限估算。
"""
import argparse


def estimate(seconds, price, draws):
    unit = seconds * price
    cost = draws * unit
    return unit, cost


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seconds", type=float, default=15.0, help="单条视频时长(秒)")
    p.add_argument("--price", type=float, default=1.0, help="单价(元/秒)")
    p.add_argument("--draws", type=int, default=10, help="抽卡次数(含重抽)")
    p.add_argument("--budget", type=int, default=30, help="每镜头抽卡上限门禁")
    args = p.parse_args()

    unit, cost = estimate(args.seconds, args.price, args.draws)
    print(f"单次生成成本 : {unit:.2f} 元  (={args.seconds}s × {args.price} 元/s)")
    print(f"抽卡次数     : {args.draws}")
    print(f"单集算力成本 : {cost:.2f} 元")

    if args.draws > args.budget:
        over = args.draws - args.budget
        print(f"⚠️  抽卡 {args.draws} > 门禁 {args.budget}，超限 {over} 次")
        print("    → 坑 3：无抽卡门禁，成本滚雪球；建议自动降级参考方案而非无限重抽")
    else:
        print(f"✅ 抽卡 {args.draws} ≤ 门禁 {args.budget}，成本可控")

    # 演示「抽卡×10 翻倍」
    big = estimate(args.seconds, args.price, args.draws * 10)
    print(f"对比：抽卡 ×10 → 单集 {big[1]:.2f} 元（{args.draws*10} 次）")


if __name__ == "__main__":
    main()
