#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 客服四类翻车率批量评估：延迟转人工 / 幻觉 / 上下文污染 / 静默失败。

说明：同样是「机制模拟器」。它用 01_agent_loop 的 agent 跑 N 段多轮对话，统计四类失败率，
并和文章参考来源里的真实公开数字并列打印，方便读者对照「模拟复现」与「真实事故」。

真实公开数字（来源见文章）：
  - BestHub 客服 agent：23% 工具调用「静默失败」（报错被模型圆成正常结果）
  - Traversaal 调研：74% 企业回滚了 AI 客服 agent
  - Klarna：年省 $60M 但后续回滚（deflection 掩盖 resolution）

脚本默认参数是示意值（贴近上述事故量级），不是某家公司的真实配置。

运行：
    python3 02_failure_eval.py --self-test
    python3 02_failure_eval.py --n 2000
"""
import argparse
import importlib.util
import os
import sys

_spec = importlib.util.spec_from_file_location(
    "agent_loop_mod",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "01_agent_loop.py"))
_agent_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_agent_mod)
CustomerServiceAgent = _agent_mod.CustomerServiceAgent


# 对话模板：覆盖退款 / 订单 / 优惠券 / 多轮追问，制造长链路与长对话
TURN_BANK = [
    "我要退款", "我的订单到哪了", "那张券怎么用", "退款到哪一步了",
    "订单还没动静", "券能叠加吗", "退款单号给我", "物流查不到",
    "什么时候能退款", "订单超时了怎么办",
]


def eval_sessions(n=2000, seed=1234, handoff_threshold_ms=3000,
                  retrieval_ms=1500, tool_ms=1000, gen_ms=1200,
                  retrieval_error_rate=0.18, silent_fail_rate=0.23,
                  hard_fail_rate=0.05):
    agent = CustomerServiceAgent(
        retrieval_ms=retrieval_ms, tool_ms=tool_ms, gen_ms=gen_ms,
        retrieval_error_rate=retrieval_error_rate,
        silent_fail_rate=silent_fail_rate, hard_fail_rate=hard_fail_rate,
        seed=seed)
    rng = __import__("random").Random(seed + 1)

    total_turns = 0
    sum_ttft = 0.0
    handoff = 0          # TTFT 超阈值 → 用户转人工的代理指标
    hallucination = 0
    silent_fail = 0
    context_polluted = 0

    for _ in range(n):
        # 每段会话 3–10 轮，制造长对话以触发上下文污染
        n_turns = rng.randint(3, 10)
        for j in range(n_turns):
            text = TURN_BANK[rng.randrange(len(TURN_BANK))]
            r = agent.handle(text, history_turns=j)
            total_turns += 1
            sum_ttft += r["ttft_ms"]
            if r["ttft_ms"] >= handoff_threshold_ms:
                handoff += 1
            if r["hallucination"]:
                hallucination += 1
            if r["silent_fail"]:
                silent_fail += 1
            if r["context_polluted"]:
                context_polluted += 1

    return {
        "sessions": n,
        "total_turns": total_turns,
        "avg_ttft_ms": round(sum_ttft / total_turns, 1),
        "handoff_rate": round(100.0 * handoff / total_turns, 1),
        "hallucination_rate": round(100.0 * hallucination / total_turns, 1),
        "silent_fail_rate": round(100.0 * silent_fail / total_turns, 1),
        "context_pollution_rate": round(100.0 * context_polluted / total_turns, 1),
    }


def _report(stats, reported):
    print("=" * 70)
    print("模拟复现（本脚本，参数贴近事故量级）")
    print("-" * 70)
    print("会话数            : %d" % stats["sessions"])
    print("总对话轮次        : %d" % stats["total_turns"])
    print("平均 TTFT         : %.1f ms" % stats["avg_ttft_ms"])
    print("转人工率(代理)    : %.1f%%  (TTFT≥3000ms)" % stats["handoff_rate"])
    print("幻觉率            : %.1f%%" % stats["hallucination_rate"])
    print("静默失败率        : %.1f%%" % stats["silent_fail_rate"])
    print("上下文污染率      : %.1f%%  (第6轮起)" % stats["context_pollution_rate"])
    print("-" * 70)
    print("公开真实数字（来源见文章）")
    print("-" * 70)
    for k, v in reported.items():
        print("%-22s: %s" % (k, v))
    print("=" * 70)


def _self_test():
    s = eval_sessions(n=400, seed=99)
    # 高延迟配置下，转人工率应明显偏高
    assert s["handoff_rate"] > 50.0, "高延迟应导致高转人工率，实得 %.1f%%" % s["handoff_rate"]
    # 默认静默失败率配置 0.23 → 实测应在 15%~35% 区间
    assert 15.0 <= s["silent_fail_rate"] <= 35.0, "静默失败率异常 %.1f%%" % s["silent_fail_rate"]
    # 幻觉率应 > 0（检索有误差）
    assert s["hallucination_rate"] > 0.0, "幻觉率应大于 0"
    # 上下文污染率 > 0（含长会话）
    assert s["context_pollution_rate"] > 0.0, "上下文污染率应大于 0"
    # TTFT 应 > 3000ms（检索1500+工具1000+生成1200 量级，含 sleep 抖动）
    assert s["avg_ttft_ms"] > 3000.0, "平均 TTFT 应 > 3000ms，实得 %.1f" % s["avg_ttft_ms"]
    print("SELF-TEST PASS")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--n", type=int, default=2000)
    args = ap.parse_args()

    reported = {
        "BestHub 静默失败": "23%（工具报错被模型圆成正常结果）",
        "Traversaal 回滚": "74% 企业回滚了 AI 客服 agent",
        "BestHub 投入": "$70K / 7 天即下线",
        "Klarna": "年省 $60M 但后续回滚（deflection 掩盖 resolution）",
    }

    if args.self_test:
        _self_test()
    else:
        stats = eval_sessions(n=args.n)
        _report(stats, reported)
