#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
latency_percentile.py — 平均值如何掩盖长尾延迟（纯标准库，免 key）

文章场景重现：
  网关延迟看板只挂了一个「平均响应时间」曲线。三个月里平均值一直 192ms，
  团队以为很健康。直到有客户投诉「偶尔要点七八秒」，才发现 p99 是 1500ms。

为什么平均会骗人：90% 的请求 30ms 就返回，9% 卡在 1500ms，
1% 卡在 3000ms。平均数被「多数快」拉低，但那 10% 的慢请求才是
用户真正能感知、也最容易导致重试风暴和限流雪崩的部分。

本脚本用一份确定性的延迟样本演示：
  平均值 < p50 < p95 ≈ p99 的阶梯形失真，并打印直方图分桶，
说明为什么埋点要把 Duration 记成「分布（直方图）」而不是「一个数」。

运行：
  python3 latency_percentile.py            # 打印平均 / 分位数 / 直方图
  python3 latency_percentile.py --self-test  # 断言分位数关系正确
"""

from __future__ import annotations

import sys
from typing import List


def percentile(sorted_vals: List[float], p: float) -> float:
    """线性插值分位数（与 numpy 默认 linear 口径一致）。

    rank = p * (n - 1)，向下取整得到下界索引 i，剩余小数部分 frac 在
    sorted_vals[i] 与 sorted_vals[i+1] 之间线性插值。
    """
    if not sorted_vals:
        raise ValueError("empty list")
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    rank = p * (n - 1)
    i = int(rank)            # 下界索引
    frac = rank - i
    if i + 1 < n:
        return sorted_vals[i] + frac * (sorted_vals[i + 1] - sorted_vals[i])
    return sorted_vals[i]


def build_latency_sample() -> List[float]:
    """构造确定性延迟样本：90 个 30ms，9 个 1500ms，1 个 3000ms。"""
    sample: List[float] = []
    sample.extend([30.0] * 90)
    sample.extend([1500.0] * 9)
    sample.extend([3000.0] * 1)
    return sample


def histogram(sample: List[float], edges: List[float]) -> List[int]:
    """按给定右边界 edges 统计分桶计数（含最后 +Inf）。"""
    counts = [0] * (len(edges) + 1)
    for v in sample:
        placed = False
        for idx, edge in enumerate(edges):
            if v <= edge:
                counts[idx] += 1
                placed = True
                break
        if not placed:
            counts[-1] += 1
    return counts


def print_report(sample: List[float]) -> None:
    s = sorted(sample)
    avg = sum(s) / len(s)
    p50 = percentile(s, 0.50)
    p95 = percentile(s, 0.95)
    p99 = percentile(s, 0.99)

    print(f"样本数        : {len(s)}")
    print(f"平均值        : {avg:.1f} ms")
    print(f"p50 (中位)    : {p50:.1f} ms")
    print(f"p95          : {p95:.1f} ms")
    print(f"p99          : {p99:.1f} ms")
    print()
    print(f"读取方式对比：")
    print(f"  看平均值  {avg:.0f}ms  -> 团队结论：'很健康，不用管'")
    print(f"  看 p99    {p99:.0f}ms  -> 真实结论：每 100 次有 1 次等 1.5 秒以上")
    print()
    edges = [50.0, 100.0, 500.0, 1000.0, 2000.0]
    counts = histogram(s, edges)
    labels = [f"<={e:.0f}" for e in edges] + ["∞"]
    print("延迟直方图（埋点应存的就是这种分桶，而非一个数）：")
    for lab, c in zip(labels, counts):
        bar = "#" * c
        print(f"  {lab:>8}ms : {c:3d} {bar}")


def self_test() -> int:
    s = sorted(build_latency_sample())
    avg = sum(s) / len(s)
    p50 = percentile(s, 0.50)
    p95 = percentile(s, 0.95)
    p99 = percentile(s, 0.99)

    checks = []
    # 分位数必须单调递增
    checks.append(("p50 <= p95 <= p99", p50 <= p95 <= p99))
    # 平均值必须被长尾拉高、但仍远小于 p99（这就是「平均骗人」）
    checks.append(("平均值 < p99", avg < p99))
    # 中位数必须远小于平均值（多数请求很快）
    checks.append(("p50 < 平均值", p50 < avg))
    # 长尾足够夸张：p99 至少是平均值的 5 倍
    checks.append(("p99 >= 5 * 平均值", p99 >= 5 * avg))
    # 单点校验：p99 应落在 1500ms 量级（100 个样本里第 99 个在 1500 桶）
    checks.append(("p99 >= 1500", p99 >= 1500.0))

    ok = True
    for label, passed in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed

    print()
    print(f"（参考值） avg={avg:.1f} p50={p50:.1f} p95={p95:.1f} p99={p99:.1f}")
    print("SELF-TEST: " + ("ALL PASS" if ok else "FAILED"))
    return 0 if ok else 1


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    sample = build_latency_sample()
    print_report(sample)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
