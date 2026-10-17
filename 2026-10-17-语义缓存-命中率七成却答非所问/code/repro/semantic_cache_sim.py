#!/usr/bin/env python3
# 语义缓存仿真：不同相似度阈值下的命中率与假阳性权衡（纯标准库，免 key）
#
# 用一批带真实意图标注的查询，扫描阈值 τ，直观展示：
#   阈值过低 -> 命中率虚高，但假阳性（答错）飙升；
#   阈值过高 -> 假阳性消失，但语义缓存退化为精确缓存，命中率骤降。
#
# 这个脚本还暴露了「词袋向量」的先天短板：它对同义词无能为力
# （「显卡」和「GPU」在词袋里毫无交集），这正是真实系统改用 embedding 模型的理由。
#
# 运行：
#   python semantic_cache_sim.py
#   python semantic_cache_sim.py --self-test

import argparse

from semantic_cache_core import SemanticCache


# 冷启动语料：第一轮查询，写回缓存。
COLD = [
    "Python 入门教程推荐",
    "深度学习需要什么显卡",
    "北京今天天气怎么样",
    "怎么用 Redis 做缓存",
    "Transformer 和 RNN 区别",
]

# 热查询：(查询, 真实意图是否应命中, 说明)
# 真实意图由人标注：是否和某个 COLD 条目在语义上问的是同一件事。
WARM = [
    ("Python 入门教程推荐", True, "完全重复 -> 应精确命中"),
    ("Python 入门教程推荐一下", True, "近义追加 -> 应语义命中"),
    ("北京明天天气怎么样", False, "今天改明天 -> 语义不同，应未命中"),
    ("深度学习要用什么 GPU", True, "显卡/GPU 同义 -> 应语义命中（词袋会漏）"),
    ("怎么用 Redis 缓存热点数据", True, "近义 -> 应语义命中"),
    ("Transformer 和 LSTM 区别", False, "RNN 改 LSTM -> 关键词变了，应未命中"),
]


def run_sweep(threshold):
    cache = SemanticCache(threshold=threshold, ttl=10 ** 9)
    for q in COLD:
        cache.get(q)
    tp = fp = tn = fn = 0
    for q, should_hit, _note in WARM:
        _resp, src = cache.get(q)
        hit = src in ("exact", "semantic")
        if hit and should_hit:
            tp += 1
        elif hit and not should_hit:
            fp += 1
        elif (not hit) and (not should_hit):
            tn += 1
        else:
            fn += 1
    total = len(WARM)
    hit_rate = (tp + fp) / total
    fp_rate = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    return {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "hit_rate": hit_rate, "fp_rate": fp_rate,
    }


def print_sweep():
    print("=== 阈值权衡仿真（语料：5 冷启动 + 6 热查询，已标注真实意图）===\n")
    print("%6s | %6s | %5s | %7s | %5s" % ("阈值", "命中率", "假阳性", "假阳性率", "漏命中"))
    print("-" * 42)
    for t in [0.60, 0.70, 0.75, 0.85, 0.95]:
        r = run_sweep(t)
        print("%6.2f | %6.2f | %5d | %7.2f | %5d"
              % (t, r["hit_rate"], r["fp"], r["fp_rate"], r["fn"]))
    print("\n说明：假阳性 = 把『意图不同』的查询当成命中（答错，最危险）；")
    print("      漏命中 = 真实同义查询未被识别（词袋对同义词无能为力，属能力上限）。")
    print("      你会发现 τ 从 0.85 降到 0.66 附近，命中率跳升的同时假阳性率冲到 1.0。")


def self_test():
    # 低阈值必有假阳性（今天/明天 或 RNN/LSTM 这类相似但不同意图的碰撞）
    fp_low = run_sweep(0.66)["fp"]
    assert fp_low >= 1, "低阈值应出现至少一次假阳性"
    # 高阈值假阳性归零
    fp_high = run_sweep(0.95)["fp"]
    assert fp_high == 0, "高阈值不应有假阳性"
    # 低阈值命中率高于高阈值（高阈值退化为精确匹配）
    hr_low = run_sweep(0.66)["hit_rate"]
    hr_high = run_sweep(0.95)["hit_rate"]
    assert hr_low > hr_high, "低阈值命中率应高于高阈值"
    print("self-test: 阈值权衡不变量 PASS")
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        return self_test()
    print_sweep()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
