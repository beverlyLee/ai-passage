#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
triage_batch.py — 批量分诊反馈信箱：读一批邮件，输出路由报告，演示确定性路由与成本。
复用 triage_router.py 里的 JevBackend / FakeJevBackend / route / triage_one。
纯标准库；默认走 FakeJevBackend（无需 API key），可用 --real 切到真实后端。

用法：
  python3 triage_batch.py --self-test     # 跑断言：队列分布 + 成本计算正确
  python3 triage_batch.py --demo          # 读 samples/ 里 7 封，打印完整路由报告
  python3 triage_batch.py --dir 某目录     # 读指定目录下的 .txt 邮件
  python3 triage_batch.py --real          # 走真实 API（需要 TYPESAFE_API_KEY）

为什么需要批量：单封分诊看不出价值，批量才看得出『确定性路由』把多少信自动派掉了、
多少转人工、成本摊到每封是多少。这正是 Jev 高吞吐便宜的甜区。
"""

import os
import sys
import glob

import triage_router as tr

SAMPLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")


def load_tickets(directory):
    """读目录下每个 .txt 作为一封邮件：第一行当 subject，其余当 body。"""
    tickets = []
    for path in sorted(glob.glob(os.path.join(directory, "*.txt"))):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        subject = lines[0] if lines else ""
        body = "\n".join(lines[1:]).strip()
        tickets.append({"subject": subject, "body": body, "from": os.path.basename(path)})
    return tickets


def run_batch(backend, tickets, auto_threshold=0.7):
    decisions = []
    for meta in tickets:
        d = tr.triage_one(backend, meta, auto_threshold)
        decisions.append((meta, d))
    return decisions


def summarize(decisions):
    counts = {"auto": 0, "human_review": 0, "human_priority": 0, "discard": 0}
    total_cost = 0.0
    total_tokens = 0
    for meta, d in decisions:
        counts[d["queue"]] = counts.get(d["queue"], 0) + 1
        total_cost += d["cost_usd"]
        total_tokens += d["input_tokens"]
    return counts, total_cost, total_tokens


def print_report(decisions, counts, total_cost, total_tokens):
    print("  反馈信箱批量分诊报告")
    print("  " + "-" * 78)
    for meta, d in decisions:
        print(tr.fmt_decision(meta, d))
    print("  " + "-" * 78)
    print("  队列分布：", counts)
    print("  合计：%d 封 | 输入 token %d | Jev 成本 $%.7f（输出免费）" % (
        len(decisions), total_tokens, total_cost))
    auto = counts.get("auto", 0)
    print("  自动派单 %d 封（占 %.0f%%），人工相关 %d 封，贵的真人只接模糊/高危的。" % (
        auto, 100.0 * auto / max(1, len(decisions)), len(decisions) - auto))


def self_test():
    be = tr.FakeJevBackend()
    tickets = load_tickets(SAMPLES_DIR)
    decisions = run_batch(be, tickets)
    counts, total_cost, total_tokens = summarize(decisions)

    ok = True
    # 断言 1：安全信进 human_priority、灌水进 discard、模糊信进 human_review
    by_from = {m["from"]: d["queue"] for m, d in decisions}
    checks = {
        "01_security.txt": "human_priority",
        "02_spam.txt": "discard",
        "06_vague.txt": "human_review",
    }
    for fn, exp in checks.items():
        got = by_from.get(fn)
        flag = "OK " if got == exp else "FAIL"
        if got != exp:
            ok = False
        print("  %s %s -> %s（期望 %s）" % (flag, fn, got, exp))

    # 断言 2：成本 = 总 token * 单价 / 1e6
    expected_cost = total_tokens * tr.PRICE_PER_MTOK_INPUT / 1_000_000.0
    if abs(total_cost - expected_cost) > 1e-9:
        ok = False
        print("  FAIL 成本计算：实得 %.9f 期望 %.9f" % (total_cost, expected_cost))
    else:
        print("  OK  成本计算：total_tokens=%d * %.5f / 1e6 = $%.7f" % (
            total_tokens, tr.PRICE_PER_MTOK_INPUT, expected_cost))

    # 断言 3：队列计数之和等于邮件总数
    if sum(counts.values()) != len(tickets):
        ok = False
        print("  FAIL 队列计数之和 != 邮件数")
    else:
        print("  OK  队列计数之和 == 邮件数（%d）" % len(tickets))

    print("\n  self-test: %s（%d 条断言）" % ("全部通过" if ok else "有失败", 5))
    return ok


def demo():
    be = tr.FakeJevBackend()
    tickets = load_tickets(SAMPLES_DIR)
    decisions = run_batch(be, tickets)
    counts, total_cost, total_tokens = summarize(decisions)
    print_report(decisions, counts, total_cost, total_tokens)
    print("\n  吞吐对比（定性，非夸大）：Jev 三问一次调用≈一次延迟（官方称 70–500ms，社区实测约 0.3s/封）；")
    print("  若改用聊天模型逐封『读信+判断+写回』，单封通常数秒且另计输出 token。量大时差异被放大。")


def main(argv):
    if "--self-test" in argv:
        return 0 if self_test() else 1
    if "--real" in argv:
        if "--dir" in argv:
            idx = argv.index("--dir")
            directory = argv[idx + 1]
        else:
            directory = SAMPLES_DIR
        tickets = load_tickets(directory)
        try:
            decisions = run_batch(tr.HttpJevBackend(), tickets)
        except Exception as e:
            print("真实后端调用失败：%s" % e)
            return 1
        counts, total_cost, total_tokens = summarize(decisions)
        print_report(decisions, counts, total_cost, total_tokens)
        return 0
    # 默认 demo
    demo()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
