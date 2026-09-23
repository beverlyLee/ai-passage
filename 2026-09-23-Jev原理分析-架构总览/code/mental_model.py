#!/usr/bin/env python3
# 心智模型路由与成本/延迟对比：把正文里的 System1/System2 分工跑成可验证数据。
#
# 重要边界（与正文一致）：
#   Jev 模型未开源，这里的成本/延迟是"教学用对比模型"，不是 Jev 内部基准。
#   锚点数字来自一手或独立可核查来源：Jev 官方定价 0.042 美元/百万输入 token、
#   输出免费、端到端 70~500ms；独立测试 Every 的单次中位 0.35s、对照 LLM 8.83s。
#   其余为示意常量，仅用于演示"判断 vs 生成"的架构性差距方向，非性能承诺。
#
# 用法：
#   python3 mental_model.py --self-test
#   python3 mental_model.py --demo
import argparse


# 锚点：Jev 官方定价与延迟区间（一手口径）。
JEV_INPUT_PRICE_PER_1M = 0.042      # 美元 / 百万输入 token
JEV_LATENCY_MIN, JEV_LATENCY_MAX = 0.070, 0.500  # 秒，官方 70~500ms

# 锚点：独立测试 Every 的单次中位延迟对比（Jev 0.35s vs 前沿 LLM 8.83s）。
LLM_DECISION_LATENCY = 8.83         # 秒，LLM 做同等决策（含生成+解析）的代表性中位
LLM_DECISION_OUTPUT_COST = 0.0020   # 美元，LLM 生成+解析一次决策的代表性输出成本（示意）

# 教学用：Jev 单条输入约 200 token（一段 state + 几个问题）。
JEV_INPUT_TOKENS_PER_CALL = 200


def route(task):
    """System1/System2 路由：判断任务该交给 Jev 还是 LLM。

    规则（与正文故障树一致）：
      - 需要开放生成（写文本/摘要/回复） -> LLM（Jev 不会生成 token）
      - 答案空间事先可枚举的窄决策     -> JEV
      - 否则（需多步开放推理）          -> LLM
    """
    if task["needs_generation"]:
        return "LLM"          # System2：慢生成
    if task["answer_space_enumerable"]:
        return "JEV"          # System1：快判断
    return "LLM"             # System2：开放推理回退


def cost_latency_for_decision(use_jev, n_primitives=1):
    """同一个窄决策，走 Jev 还是 LLM，成本与延迟对比。

    关键架构事实（parallel sampler）：Jev 一次前向并行算出多个原语，
    所以 n_primitives 个判断在 Jev 上≈一次调用成本；而 LLM 要么调 n 次、
    要么一次生成长 JSON 再解析，成本随判断数上升。
    """
    if use_jev:
        # 输出免费 + 输入按 token 计费；并行采样使 n 个原语≈1 次调用。
        cost = JEV_INPUT_PRICE_PER_1M * JEV_INPUT_TOKENS_PER_CALL / 1_000_000
        # 取官方区间中值当代表性延迟。
        latency = (JEV_LATENCY_MIN + JEV_LATENCY_MAX) / 2
        return {"cost_usd": cost, "latency_s": latency}
    else:
        # LLM 生成+解析：成本与延迟都随原语数上升（每次决策一次生成）。
        cost = LLM_DECISION_OUTPUT_COST * n_primitives
        latency = LLM_DECISION_LATENCY * n_primitives
        return {"cost_usd": cost, "latency_s": latency}


def _self_test():
    # 1) 路由逻辑：开放生成必须回 LLM；可枚举窄决策走 JEV。
    gen = {"needs_generation": True, "answer_space_enumerable": False}
    typed = {"needs_generation": False, "answer_space_enumerable": True}
    openr = {"needs_generation": False, "answer_space_enumerable": False}
    assert route(gen) == "LLM", "需要生成必须走 LLM"
    assert route(typed) == "JEV", "可枚举窄决策走 JEV"
    assert route(openr) == "LLM", "开放推理回退 LLM"

    # 2) 同一窄决策：Jev 比 LLM 又快又便宜（方向来自独立测试 Every 的锚点）。
    j = cost_latency_for_decision(use_jev=True, n_primitives=1)
    l = cost_latency_for_decision(use_jev=False, n_primitives=1)
    assert j["cost_usd"] < l["cost_usd"], "Jev 决策成本应低于 LLM"
    assert j["latency_s"] < l["latency_s"], "Jev 决策延迟应低于 LLM"

    # 3) parallel sampler：3 个原语在 Jev 上≈1 次调用成本（不因原语数翻倍）。
    j3 = cost_latency_for_decision(use_jev=True, n_primitives=3)
    assert abs(j3["cost_usd"] - j["cost_usd"]) < 1e-12, \
        "Jev 并行采样：3 原语成本≈1 原语（一次前向）"
    l3 = cost_latency_for_decision(use_jev=False, n_primitives=3)
    assert l3["cost_usd"] > l["cost_usd"], "LLM 做 3 决策成本应随次数上升"

    print("self-test PASS: System1/System2 路由与成本/延迟方向均成立")


def _demo():
    print("任务路由示例：")
    for name, t in [
        ("写一封投诉回信", {"needs_generation": True, "answer_space_enumerable": False}),
        ("信派给哪个部门(3选1)", {"needs_generation": False, "answer_space_enumerable": True}),
        ("紧急程度打分(0~2)", {"needs_generation": False, "answer_space_enumerable": True}),
        ("判断这封是不是漏洞报告", {"needs_generation": False, "answer_space_enumerable": True}),
    ]:
        print(f"  {name:<22} -> {route(t)}")

    print("\n同一窄决策：Jev vs LLM（1 个原语）")
    j = cost_latency_for_decision(True, 1)
    l = cost_latency_for_decision(False, 1)
    print(f"  JEV  : 成本 ${j['cost_usd']:.6f}  延迟 {j['latency_s']*1000:.0f}ms")
    print(f"  LLM  : 成本 ${l['cost_usd']:.6f}  延迟 {l['latency_s']*1000:.0f}ms")

    print("\nparallel sampler：3 个原语合并为一次 Jev 调用 vs 3 次 LLM 生成")
    j3 = cost_latency_for_decision(True, 3)
    l3 = cost_latency_for_decision(False, 3)
    print(f"  JEV x3 原语: 成本 ${j3['cost_usd']:.6f}  延迟 {j3['latency_s']*1000:.0f}ms  (≈1次调用)")
    print(f"  LLM x3 决策: 成本 ${l3['cost_usd']:.6f}  延迟 {l3['latency_s']*1000:.0f}ms")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        _self_test()
    elif args.demo:
        _demo()
    else:
        _self_test()
        print("-" * 48)
        _demo()


if __name__ == "__main__":
    main()
