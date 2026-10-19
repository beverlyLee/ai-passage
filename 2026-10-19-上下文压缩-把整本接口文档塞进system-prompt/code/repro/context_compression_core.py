#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上下文压缩核心模型：KV cache 成本 + 中间遗忘 + 三种上下文策略。

纯标准库，零外部依赖，确定性可复现。
用法：
  python3 context_compression_core.py            # 打印核心演示数据
  python3 context_compression_core.py --self-test   # 断言自检

所有数字均为教学模型或公开文档规格，非厂商承诺口径；厂商成本请看 README 来源。
"""
import sys

# ---------------------------------------------------------------------------
# 确定性字符级词袋嵌入（教学用，替代真实 embedding，保证零依赖可复现）
# ---------------------------------------------------------------------------
def char_bow_embed(text, dim=64):
    vec = [0] * dim
    for ch in text:
        vec[ord(ch) % dim] += 1
    return vec


# ---------------------------------------------------------------------------
# KV cache 成本模型
#   每 token 字节数 = 2(K,V) * 层数 * KV头数 * 头维度 * 每元素字节
#   来源：公开推理成本资料（见 README 来源），公式为业界通用记法。
# ---------------------------------------------------------------------------
def kv_cache_mb_per_token(num_layers, num_kv_heads, head_dim, bytes_per_elem=2):
    elems = 2 * num_layers * (num_kv_heads * head_dim)
    return elems * bytes_per_elem / (1024.0 * 1024.0)


# 公开文档化的模型规格（教学计算用，非承诺）
SPECS = {
    "llama2-7b":  dict(num_layers=32, num_kv_heads=32, head_dim=128),
    "llama3-8b":  dict(num_layers=32, num_kv_heads=8,  head_dim=128),  # GQA 共享 KV 头
    "llama2-70b": dict(num_layers=80, num_kv_heads=80, head_dim=128),
}


def spec_mb_per_token(name):
    s = SPECS[name]
    return kv_cache_mb_per_token(s["num_layers"], s["num_kv_heads"], s["head_dim"])


# ---------------------------------------------------------------------------
# 中间遗忘（lost-in-the-middle）：位置敏感度
#   刘等人 2023（arXiv:2307.03172）发现准确率随相关信息的"位置"呈 U 形：
#   在开头（首因偏差）和结尾（近因偏差）最高，在中间最低。
#   下面用确定性函数近似这条 U 形曲线（纯教学，非测量值）。
# ---------------------------------------------------------------------------
def middle_penalty(pos, n):
    """返回 0..1 的"检索成功乘子"。pos in [0, n-1]，中心处最低。"""
    if n <= 1:
        return 1.0
    center = (n - 1) / 2.0
    dist = abs(pos - center) / center   # 中心 0，两端 1
    return 0.4 + 0.6 * dist             # 中心 ~0.4，两端 ~1.0


def answer_accuracy(fact_present, pos=None, n=None, summarized=False):
    """给定一个事实在当前上下文中的状态，返回被正确使用的概率(0..1)。"""
    if not fact_present:
        return 0.0
    if summarized:
        return 0.95                     # 压进摘要后视为被强化提及
    return middle_penalty(pos, n)


# ---------------------------------------------------------------------------
# 案例常量：把整本接口文档(8K token)塞进 system prompt 的 8 轮调试会话
# ---------------------------------------------------------------------------
DOC_TOKENS = 8000        # 整本接口文档
TURN_USER = 150          # 每轮用户消息
TURN_ASSIST = 250        # 每轮助手回复
ROUND = TURN_USER + TURN_ASSIST   # 每轮往返 400
N_TURNS = 8
COMPACT_AFTER = 3        # 比这更早的轮次被摘要
SUMMARY_TOKENS = 600     # 摘要固定预算
WINDOW_K = 2             # 滑动窗口保留最近 K 轮


def context_size_none(turn):
    """不压缩：doc 全量 + 之前所有轮次 + 当前用户消息。"""
    prior = (turn - 1) * ROUND
    return DOC_TOKENS + prior + TURN_USER


def context_size_window(turn):
    """滑动窗口：doc + 最近 K 轮 + 当前。"""
    recent = min(turn - 1, WINDOW_K) * ROUND
    return DOC_TOKENS + recent + TURN_USER


def context_size_compact(turn):
    """compaction：doc + 固定摘要 + 最近 COMPACT_AFTER 轮 + 当前。"""
    if turn <= COMPACT_AFTER + 1:
        prior = (turn - 1) * ROUND
        return DOC_TOKENS + prior + TURN_USER
    # 更早的轮次被摘要替代为固定预算
    return DOC_TOKENS + SUMMARY_TOKENS + COMPACT_AFTER * ROUND + TURN_USER


def cumulative_input(strategy):
    return sum(strategy(t) for t in range(1, N_TURNS + 1))


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

    # 1. KV 公式：llama2-7b ≈ 0.5 MB/token
    mb7 = kv_cache_mb_per_token(32, 32, 128, 2)
    check("llama2-7b KV ~0.5MB/token", abs(mb7 - 0.5) < 0.01)

    # 2. GQA 让每 token KV 变小（llama3-8b 8 个 KV 头 < llama2-7b 32 个）
    check("GQA 缩小 KV (llama3-8b < llama2-7b)",
          spec_mb_per_token("llama3-8b") < spec_mb_per_token("llama2-7b"))

    # 3. 128K 上下文 KV 远超权重（7B 权重 FP16 ~14GB）
    check("128K 上下文 KV > 14GB 权重", mb7 * 128000 > 14.0)

    # 4. 中间遗忘：中心 < 两端（U 形）
    n = 21
    check("middle < edge (U 形)", middle_penalty(10, n) < middle_penalty(0, n))

    # 5. 不压缩累计输入 > compaction 累计输入（增长被约束）
    check("none 累计 > compact 累计",
          cumulative_input(context_size_none) > cumulative_input(context_size_compact))

    # 6. 滑动窗口在第 8 轮会丢掉第 1 轮的事实
    def present_window(turn, fact_turn):
        return (turn - fact_turn) <= WINDOW_K
    check("window 在第8轮丢失第1轮事实", not present_window(8, 1))

    print()
    print("self-test PASS" if ok else "self-test FAIL")
    return 0 if ok else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        return self_test()

    print("== KV cache 成本（每 token, FP16） ==")
    for name in SPECS:
        print("  %-12s %.4f MB/token" % (name, spec_mb_per_token(name)))
    print("  llama2-7b @128K 上下文 KV = %.1f GB" % (spec_mb_per_token("llama2-7b") * 128000))
    print()
    print("== 中间遗忘 U 形（n=21 个候选位置） ==")
    for pos in [0, 5, 10, 15, 20]:
        print("  pos=%2d: 检索成功乘子=%.2f" % (pos, middle_penalty(pos, 21)))
    print()
    print("== 8 轮对话累计输入 token（案例：8K 文档塞 system prompt） ==")
    print("  不压缩:    %d" % cumulative_input(context_size_none))
    print("  滑动窗口:  %d" % cumulative_input(context_size_window))
    print("  compaction:%d" % cumulative_input(context_size_compact))
    return 0


if __name__ == "__main__":
    sys.exit(main())
