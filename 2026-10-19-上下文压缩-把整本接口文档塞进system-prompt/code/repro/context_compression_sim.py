#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上下文压缩仿真：提示缓存省多少 + 三种策略的上下文规模与准确率。

纯标准库，零外部依赖，确定性可复现。
用法：
  python3 context_compression_sim.py            # 打印仿真表
  python3 context_compression_sim.py --self-test   # 断言自检

成本口径为教学归一化模型；厂商真实价目见 README 来源（非承诺）。
"""
import sys
import context_compression_core as core

# ---------------------------------------------------------------------------
# 提示缓存成本模型（教学归一化：以 base 输入单价为 1.0）
#   不缓存：每轮都重发静态前缀(prefix) + 本轮新内容
#   缓存：前缀写一次(1.25x)，之后每轮读(0.1x)，本轮新内容全价
#   对应 Anthropic 公开口径：写 1.25x / 读 0.1x（90% off）。详见 README。
# ---------------------------------------------------------------------------
BASE_INPUT_RATE = 1.0
CACHE_WRITE_RATE = 1.25
CACHE_READ_RATE = 0.10


def cost_no_cache(prefix_tokens, per_turn_tokens, n_turns):
    return n_turns * (prefix_tokens + per_turn_tokens) * BASE_INPUT_RATE


def cost_with_cache(prefix_tokens, per_turn_tokens, n_turns):
    write = prefix_tokens * CACHE_WRITE_RATE
    reads = (n_turns - 1) * prefix_tokens * CACHE_READ_RATE
    fresh = n_turns * per_turn_tokens * BASE_INPUT_RATE
    return write + reads + fresh


# ---------------------------------------------------------------------------
# 三种策略在"第 8 轮"时，对一个"第 4 轮(居中)提到的关键约束"的命中情况
#   这里把对话块单独建模（文档作为独立的静态前缀由缓存处理），
#   相关事实在第 4 轮、共 8 轮，正处对话块正中 -> 中间遗忘最弱点。
# ---------------------------------------------------------------------------
def accuracy_at_turn8():
    fact_turn = 4
    n_conv = core.N_TURNS  # 8 轮都在上下文里（不压缩时）

    # 不压缩：事实在、但位于对话块正中 -> 中间遗忘最弱
    acc_none = core.answer_accuracy(True, pos=fact_turn - 1, n=n_conv)

    # 滑动窗口(K=2)：第 8 轮时第 4 轮事实已被挤出 -> 0
    present_window = (core.N_TURNS - fact_turn) <= core.WINDOW_K
    acc_window = core.answer_accuracy(present_window)

    # compaction：旧轮次进摘要，关键约束被摘要捕获 -> 0.95
    acc_compact = core.answer_accuracy(True, summarized=True)

    return {
        "none": (core.context_size_none(core.N_TURNS), acc_none),
        "window": (core.context_size_window(core.N_TURNS), acc_window),
        "compact": (core.context_size_compact(core.N_TURNS), acc_compact),
    }


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------
def self_test():
    ok = True

    def check(name, cond):
        nonlocal ok
        if cond:
            print("  ok:   " + name)
        else:
            ok = False
            print("  FAIL: " + name)

    # 1. 缓存静态前缀：8 轮会话约省 4 倍（标题"账单翻 4 倍"的案例依据）
    no_c = cost_no_cache(core.DOC_TOKENS, core.TURN_USER, core.N_TURNS)
    with_c = cost_with_cache(core.DOC_TOKENS, core.TURN_USER, core.N_TURNS)
    ratio = no_c / with_c
    check("缓存静态前缀省约 4 倍 (ratio>3.5)", ratio > 3.5)

    # 2. 不压缩累计输入 > compaction（增长被约束）
    check("none 累计 > compact 累计",
          core.cumulative_input(core.context_size_none) >
          core.cumulative_input(core.context_size_compact))

    # 3. 滑动窗口在第 8 轮丢失居中事实 -> 准确率 0
    res = accuracy_at_turn8()
    check("window 在第8轮丢失居中事实 (acc=0)", res["window"][1] == 0.0)

    # 4. compaction 保留居中事实 -> 准确率 0.95
    check("compact 保留居中事实 (acc=0.95)", abs(res["compact"][1] - 0.95) < 1e-9)

    # 5. 不压缩的居中事实受中间遗忘影响，弱于 compaction
    check("none 居中事实弱于 compact", res["none"][1] < res["compact"][1])

    # 6. 中间遗忘 U 形：中心 < 两端
    check("U 形 center<edge", core.middle_penalty(3, 8) < core.middle_penalty(0, 8))

    print()
    print("self-test PASS" if ok else "self-test FAIL")
    return 0 if ok else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        return self_test()

    print("== 提示缓存：8K 静态前缀 × 8 轮（归一化成本单位） ==")
    no_c = cost_no_cache(core.DOC_TOKENS, core.TURN_USER, core.N_TURNS)
    with_c = cost_with_cache(core.DOC_TOKENS, core.TURN_USER, core.N_TURNS)
    print("  不缓存: %.0f" % no_c)
    print("  缓存:   %.0f" % with_c)
    print("  省:     %.2f 倍" % (no_c / with_c))
    print()
    print("== 每轮上下文规模（token） ==")
    print("  turn |   不压缩 | 滑动窗口 | compaction")
    for t in range(1, core.N_TURNS + 1):
        print("  %4d | %8d | %8d | %8d" % (
            t,
            core.context_size_none(t),
            core.context_size_window(t),
            core.context_size_compact(t),
        ))
    print()
    print("== 第 8 轮对'第 4 轮(居中)关键约束'的命中 ==")
    res = accuracy_at_turn8()
    for k in ["none", "window", "compact"]:
        size, acc = res[k]
        print("  %-8s 上下文=%5d token  准确率=%.2f" % (k, size, acc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
