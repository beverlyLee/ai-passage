#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01-dit-attention-complexity.py
------------------------------------------------------------------
论点 1「算力墙被击穿」的可复现测算：Video DiT 注意力的复杂度分级。

把三种注意力方案的"单卡单步注意力开销"按复杂度类建模，复现正文中
"dense softmax 是 O(N^2)，线性注意力是 O(N)，稀疏滑窗是 O(N·w)"的
量级结论。注意：这是复杂度类比率，不是墙钟时间（墙钟还受 FlashAttention、
kernel fusion、显存带宽影响；正文的 13.06s / 3.53x 是厂商实测）。

事实来源：
  - 5s/720p 视频 ≈ 115K tokens（HunyuanVideo 实测，FastVideo/STA 论文）
  - STA：占总空间 15.52% 的局部窗口捕获 70% 注意力（STA 论文）

自检门控（铁律：只在全默认或显式 --self-test 时断言，避免误伤正常用法）：
  python3 01-dit-attention-complexity.py --self-test
"""

import argparse

# dense softmax 注意力单步开销 ∝ N^2（忽略与 N 无关的常数）
# 线性注意力单步开销 ∝ N * d
# 稀疏滑窗（STA 类）单步开销 ∝ N * w，w = 局部窗口 token 数

DEFAULT_TOKENS = 115_000      # 5s/720p 视频的 latent token 数（HunyuanVideo 实测）
DEFAULT_DIM = 2_048           # DiT 典型隐维度
DEFAULT_LOCAL_FRAC = 0.1552    # STA：局部窗口占总空间的 15.52%


def attention_cost(tokens, dim, local_frac):
    """返回三种方案的注意力开销（相对单位，省略与 N 无关的常数）。"""
    dense = tokens * tokens                       # O(N^2)
    linear = tokens * dim                          # O(N*d)
    window_tokens = int(round(tokens * local_frac))
    sparse = tokens * window_tokens                # O(N*w)
    return {
        "dense": dense,
        "linear": linear,
        "sparse": sparse,
        "window_tokens": window_tokens,
    }


def fmt(n):
    if n >= 1e9:
        return f"{n / 1e9:.2f}B"
    if n >= 1e6:
        return f"{n / 1e6:.2f}M"
    if n >= 1e3:
        return f"{n / 1e3:.1f}K"
    return str(n)


def run(tokens, dim, local_frac):
    c = attention_cost(tokens, dim, local_frac)
    dense_vs_linear = c["dense"] / c["linear"]
    dense_vs_sparse = c["dense"] / c["sparse"]
    print("=" * 60)
    print(f"Video DiT 注意力复杂度分级（tokens={fmt(tokens)}, dim={dim}）")
    print("=" * 60)
    print(f"  dense  softmax   O(N^2)      : {fmt(c['dense'])}  (基准 1x)")
    print(f"  linear attention O(N*d)      : {fmt(c['linear'])}  "
          f"({dense_vs_linear:.1f}x 更省)")
    print(f"  STA 局部窗口   O(N*w) w={fmt(c['window_tokens'])}: "
          f"{fmt(c['sparse'])}  ({dense_vs_sparse:.2f}x 更省)")
    print("-" * 60)
    print("  说明：复杂度类比率，非墙钟时间。")
    print("  正文厂商实测：SANA-Video 2.0 单 H100 5s/720p=13.06s；")
    print("  STA 端到端最高 3.53x（无训练、无质量损失）。")
    print("=" * 60)
    return c


def self_check():
    """仅在 --self-test 或全默认场景运行；失败即非零退出，可挂 CI。"""
    c = attention_cost(DEFAULT_TOKENS, DEFAULT_DIM, DEFAULT_LOCAL_FRAC)
    # 不变式 1：复杂度类顺序 dense >> sparse >> linear
    assert c["dense"] > c["sparse"] > c["linear"], "复杂度类顺序异常"
    # 不变式 2：线性注意力对长序列应是数量级更省（N/d >> 1）
    assert c["dense"] / c["linear"] > 10, "线性注意力未体现 O(N) 优势"
    # 不变式 3：局部窗口确实远小于全量
    assert c["window_tokens"] < DEFAULT_TOKENS, "窗口 token 数异常"
    assert DEFAULT_LOCAL_FRAC < 0.2, "局部占比不应过大（与 STA 论文 15.52% 矛盾）"
    # 不变式 4：token 数落在 5s/720p 的合理区间
    assert 100_000 <= DEFAULT_TOKENS <= 130_000, "tokens 数超出 5s/720p 实测区间"
    print("[SELF-CHECK] 01 通过：复杂度类顺序 dense>sparse>linear，"
          "线性注意力为 O(N)，局部窗口 15.52% 成立。")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokens", type=int, default=DEFAULT_TOKENS)
    ap.add_argument("--dim", type=int, default=DEFAULT_DIM)
    ap.add_argument("--local-frac", type=float, default=DEFAULT_LOCAL_FRAC)
    ap.add_argument("--self-test", action="store_true",
                    help="强制回到默认场景并跑断言")
    args = ap.parse_args()

    run(args.tokens, args.dim, args.local_frac)

    # 仅在「全默认」或显式 --self-test 时跑断言
    run_check = args.self_test or (
        args.tokens == DEFAULT_TOKENS
        and args.dim == DEFAULT_DIM
        and abs(args.local_frac - DEFAULT_LOCAL_FRAC) < 1e-9
    )
    if run_check:
        self_check()
