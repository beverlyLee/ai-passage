#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CED prefill 算力复杂度对比：传统 O(N·L) vs CED O(N·L/2 + n·L/2)。

纯标准库实现，--self-test 校验复杂度公式。

CED（Causal Encoder-Decoder）= 20 层因果编码器 + 20 层解码器（共 40 层）。
解码器全局 KV 由编码器末层隐状态经各解码层专有线性投影矩阵一次性映射生成，
不逐层重算。因此 prefill 阶段只需：
  - 编码器对 N 个输入 token 做因果处理：O(N · 20)
  - 解码器对 n 个新 token 做因果 decode：O(n · 20)
合计 ≈ O(N·L/2 + n·L/2)，长上下文(N 很大)时相对传统 O(N·L) 近乎减半。
"""

import sys

L_TOTAL = 40   # 总层数
L_ENC = 20     # 编码器层数
L_DEC = 20     # 解码器层数


def traditional_prefill_cost(N: int, L: int = L_TOTAL) -> int:
    """传统：N 个 token 在 L 层逐层做全注意力 + 写 KV。"""
    return N * L


def ced_prefill_cost(N: int, n: int, L_enc: int = L_ENC, L_dec: int = L_DEC) -> int:
    """CED：编码器对 N 做因果 prefill + 解码器对 n 做因果 decode。"""
    return N * L_enc + n * L_dec


def speedup(N: int, n: int) -> float:
    trad = traditional_prefill_cost(N)
    ced = ced_prefill_cost(N, n)
    return trad / ced


def main():
    print("== CED prefill 算力对比 ==")
    for (N, n) in [(1_000_000, 1), (1_000_000, 1_000), (128_000, 1)]:
        trad = traditional_prefill_cost(N)
        ced = ced_prefill_cost(N, n)
        print(f"  N={N:>9,} n={n:>6,} : 传统={trad:>12,}  CED={ced:>12,}  "
              f"提速≈{speedup(N, n):.3f}x")
    print()
    print("长上下文(N=1M, n=1) 理论接近 2x —— 编码器/解码器各占一半层数，")
    print("解码器仅处理少量新 token，其算力相对 N 可忽略。")


def self_test() -> bool:
    ok = True
    N, n = 1_000_000, 1
    trad = traditional_prefill_cost(N)
    ced = ced_prefill_cost(N, n)
    eff = speedup(N, n)
    print(f"N={N:,} n={n}: 传统={trad:,} CED={ced:,} 提速≈{eff:.4f}x")
    if not (1.9 < eff < 2.1):
        print(f"FAIL: efficiency {eff}"); ok = False
    eff2 = speedup(1_000_000, 1_000_000)
    if not (1.9 < eff2 < 2.1):
        print(f"FAIL: efficiency2 {eff2}"); ok = False
    # 解码层数是编码层数一半 → 公式正确性
    if ced_prefill_cost(100, 0) != 100 * L_ENC:
        print("FAIL: ced cost formula"); ok = False
    if ok:
        print("SELF-TEST PASS")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if self_test() else 1)
    main()
