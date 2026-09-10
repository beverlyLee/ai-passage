#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""《后西游记》资产复用率驱动的边际成本模型（对应正文 问题 4 / 坑 3 / 三层治理·编排层）。

用法:
    python3 02-cost-estimator.py --self-test
    python3 02-cost-estimator.py --c0 210 --overhead 8 --discount 0.72 --reuse-rate 0.85
    python3 02-cost-estimator.py --reuse-rate 0.30 --budget 100

为什么需要这个脚本:
    长剧独有的「资产生息」曲线：把 109 个角色资产、143 个场景资产沉淀入库，跨集复用，
    复用率越高，单集新增生成成本越低 → 边际成本递减。短剧没有集数规模，享受不到。
    《后西游记》单集约 90 万、每分钟 2–3 万、约传统动画 1/10，正是这条曲线跑出来的结果。

成本模型（正文公式的资产生息版）:
    单集成本 = c0 × (1 − 资产复用率 × 复用折扣系数) + 固定开销(存储/基础算力)
    资产复用率 ↑  →  单集成本 ↓  （边际成本递减，验证「资产生息」）

门禁:
    --budget 给出单集预算上限，超出即告警（坑 3：抽卡无门禁则成本雪崩；复用率低则成本失控）。

已知边界:
    - c0(零复用全量生成成本)、overhead、discount 为后西游记公开口径的近似拟合参数，
      用于演示「复用率→成本」的递减关系；真实落地以剧组实际账本为准。
    - 未含音频/合规/宣发，仅为 AI 生成侧的边际成本下限估算。
"""
import argparse


DEFAULT_C0 = 210.0        # 零复用全量生成成本（万元/集，拟合上限）
DEFAULT_OVERHEAD = 8.0    # 固定开销（存储 + 基础算力，万元/集）
DEFAULT_DISCOUNT = 0.72   # 复用折扣系数（每 1.0 复用率可省下的成本比例）
DEFAULT_REUSE = 0.85      # 《后西游记》跨集资产复用率（公开口径近似）
DEFAULT_BUDGET = 100.0    # 单集预算门禁（万元）


def episode_cost(c0, overhead, discount, reuse_rate):
    """复用率越高，单集成本越低。"""
    return c0 * (1.0 - reuse_rate * discount) + overhead


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--c0", type=float, default=DEFAULT_C0, help="零复用全量生成成本(万元/集)")
    p.add_argument("--overhead", type=float, default=DEFAULT_OVERHEAD, help="固定开销(万元/集)")
    p.add_argument("--discount", type=float, default=DEFAULT_DISCOUNT, help="复用折扣系数")
    p.add_argument("--reuse-rate", type=float, default=DEFAULT_REUSE, help="资产复用率(0~1)")
    p.add_argument("--budget", type=float, default=DEFAULT_BUDGET, help="单集预算门禁(万元)")
    p.add_argument("--self-test", action="store_true", help="跑内置多复用率对比")
    args = p.parse_args()

    if args.self_test:
        print(f"{'复用率':<10}{'单集成本(万)':<16}{'vs 零复用':<14}边际趋势")
        print("-" * 60)
        base = episode_cost(args.c0, args.overhead, args.discount, 0.0)
        prev = None
        for rr in (0.30, 0.45, 0.60, 0.75, 0.85, 0.92):
            cost = episode_cost(args.c0, args.overhead, args.discount, rr)
            delta = ((cost - base) / base * 100)
            trend = ""
            if prev is not None:
                margin = cost - prev
                trend = f"↓ {prev - cost:.1f}万" if margin > 0 else f"↑ {-margin:.1f}万"
            print(f"{rr*100:>6.0f}%  {cost:>12.1f}   {delta:>10.1f}%   {trend}")
            prev = cost
        print("-" * 60)
        final = episode_cost(args.c0, args.overhead, args.discount, args.reuse_rate)
        print(f"《后西游记》复用率 {args.reuse_rate*100:.0f}% → 单集约 {final:.1f} 万（≈ 官方披露 90 万量级）")
        print("→ 复用率每升一档，单集成本持续下降：这就是「资产生息」的边际成本递减曲线。")
        return

    cost = episode_cost(args.c0, args.overhead, args.discount, args.reuse_rate)
    print(f"零复用全量成本 : {args.c0:.1f} 万/集")
    print(f"固定开销       : {args.overhead:.1f} 万/集")
    print(f"复用折扣系数   : {args.discount}")
    print(f"资产复用率     : {args.reuse_rate*100:.0f}%")
    print(f"单集成本       : {cost:.1f} 万  = {args.c0} × (1 − {args.reuse_rate} × {args.discount}) + {args.overhead}")

    if cost > args.budget:
        over = cost - args.budget
        print(f"⚠️  单集 {cost:.1f} 万 > 门禁 {args.budget:.0f} 万，超限 {over:.1f} 万")
        print("    → 坑 3：复用率不足 / 抽卡无门禁，成本失控；先抬资产复用率再谈投入。")
    else:
        print(f"✅ 单集 {cost:.1f} 万 ≤ 门禁 {args.budget:.0f} 万，资产生息达标")


if __name__ == "__main__":
    main()
