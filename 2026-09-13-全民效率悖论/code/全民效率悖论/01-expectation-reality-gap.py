#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01-expectation-reality-gap.py
期望-现实鸿沟模拟器：把你"用 AI 省下的时间"和"花在核验/纠偏上的时间"对冲，
算出真实净增益与 botsitting 占比，判断到底是"省了"还是"净亏"。

对应正文机制①（期望-现实鸿沟）与图2。

用法：
  python3 01-expectation-reality-gap.py            # 跑自检 + 两个真实案例
  python3 01-expectation-reality-gap.py --self-test
  python3 01-expectation-reality-gap.py --saved 11 --botsit 6.4 --fail-rate 0.34
    --saved     每周 AI 帮你"省下"的小时数（毛数）
    --botsit    每周花在 botsitting（核验/纠偏/清理）的小时数
    --fail-rate 直接失败的 AI 会话占比（0~1，用于折算重做成本；可选）

纯标准库，无第三方依赖。
"""
import argparse
import sys


def net_gain(saved, botsit, fail_rate=0.0):
    """返回净增益与诊断字典。fail_rate 用于把"重做"粗略折算进 botsitting。"""
    # 失败会话需要重做：把重做时间近似为 saved 的一部分（重做 = 重新生成 + 重新核验）
    redo_cost = saved * fail_rate * 0.5  # 重的那一半需要返工，保守系数 0.5
    effective_botsit = botsit + redo_cost
    net = saved - effective_botsit
    botsit_ratio = effective_botsit / saved if saved > 0 else float("inf")
    if net <= 0:
        verdict = "净亏 —— 你不是在提效，是在给 AI 当免费质检员"
    elif botsit_ratio >= 0.5:
        verdict = "纸面盈利 —— 过半省时被核验吃掉，组织大概率无感"
    else:
        verdict = "真赚 —— 核验占比可控，增益能落进产能"
    return {
        "saved": saved,
        "botsit_raw": botsit,
        "redo_cost": redo_cost,
        "botsit_eff": effective_botsit,
        "net": net,
        "botsit_ratio": botsit_ratio,
        "verdict": verdict,
    }


def fmt(d):
    return (
        f"  毛省时        : {d['saved']:.2f} h/周\n"
        f"  核验/纠偏     : {d['botsit_raw']:.2f} h/周\n"
        f"  失败重做折算   : {d['redo_cost']:.2f} h/周\n"
        f"  有效核验成本   : {d['botsit_eff']:.2f} h/周\n"
        f"  净增益        : {d['net']:+.2f} h/周\n"
        f"  核验占比       : {d['botsit_ratio']*100:.1f}%\n"
        f"  结论          : {d['verdict']}"
    )


def self_test():
    print("== 自检 1: Foxit 高管案例 ==")
    d = net_gain(saved=4.6, botsit=4.33, fail_rate=0.0)
    print(fmt(d))
    # Foxit: 省 4.6h, 校验 4h20m=4.33h -> 净得约 0.27h ≈ 16 分钟
    assert abs(d["net"] - 0.27) < 0.05, f"Foxit 净增益应为≈0.27, got {d['net']}"
    assert d["botsit_ratio"] > 0.9, "Foxit 核验占比应 >90%"

    print("\n== 自检 2: Glean 知识工作者 ==")
    d = net_gain(saved=11.0, botsit=6.4, fail_rate=0.34)
    print(fmt(d))
    # Glean: 省 11h, botsitting 6.4h, 1/3 失败 -> 净约 2.7h，但组织仅 13% 见增益
    assert d["net"] > 0, "Glean 应纸面盈利"
    assert d["botsit_ratio"] >= 0.5, "Glean 核验占比应过半"

    print("\n== 自检 3: 终端用户净亏 ==")
    d = net_gain(saved=4.6, botsit=4.77, fail_rate=0.0)
    print(fmt(d))
    assert d["net"] < 0, "终端用户应净亏"

    print("\n所有自检通过 ✅")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--saved", type=float, default=None, help="每周省下小时数")
    p.add_argument("--botsit", type=float, default=None, help="每周核验小时数")
    p.add_argument("--fail-rate", type=float, default=0.0, help="失败会话占比 0~1")
    p.add_argument("--self-test", action="store_true", help="跑内置自检后退出")
    args = p.parse_args()

    if args.self_test or args.saved is None:
        self_test()
        return

    d = net_gain(args.saved, args.botsit, args.fail_rate)
    print(f"== 你的期望-现实鸿沟（saved={args.saved}, botsit={args.botsit}, fail={args.fail_rate}）==")
    print(fmt(d))


if __name__ == "__main__":
    main()
