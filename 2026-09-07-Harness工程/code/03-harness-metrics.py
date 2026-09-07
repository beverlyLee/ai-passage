#!/usr/bin/env python3
"""03-harness-metrics.py — harness 度量面板
对应文章问题 5：五个必须测的量 + 裸模型基线对照。没有基线，所有改进都是感觉。

用法:
  python3 03-harness-metrics.py <run.jsonl> [--baseline.json base.json]

run.jsonl 每行一个 JSON（每轮一条）:
  {"turn": 1, "actions": 12, "recovered": true, "tokens_in": 48000,
   "tokens_out": 3100, "wall_sec": 214, "cost_usd": 0.42}
  recovered = 本轮是否从上一轮的失败中爬回并推进（恢复事件）

baseline.json（裸模型基线，同任务跑一遍的汇总）:
  {"actions": 40, "success_rate": 0.30, "cost_usd": 0.85, "wall_sec": 600}
"""
import json
import sys
import argparse


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--baseline")
    args = ap.parse_args()

    rows = load(args.run)
    if not rows:
        sys.exit("no rows")

    turns = len(rows)
    actions = sum(r.get("actions", 0) for r in rows)
    recov = sum(1 for r in rows if r.get("recovered"))
    tok = sum(r.get("tokens_in", 0) + r.get("tokens_out", 0) for r in rows)
    cost = sum(r.get("cost_usd", 0.0) for r in rows)
    wall = sum(r.get("wall_sec", 0) for r in rows)
    done = rows[-1].get("done", False)
    success_rate = 1.0 if done else 0.0

    print(f"═══ harness 运行报告（{turns} 轮）═══")
    print(f"成功率(终态)   : {success_rate:.0%}          {'✅ 目标达成' if done else '❌ 未达成（停在迭代/预算上限）'}")
    print(f"动作数         : {actions}")
    print(f"恢复频率       : {recov}/{turns} = {recov / turns:.0%}   ← harness 的核心产出")
    print(f"每轮 token     : {tok // max(turns, 1):,}   总量 {tok:,}")
    print(f"总成本         : ${cost:.2f}")
    print(f"wall-clock     : {wall // 60}m{(wall % 60):02d}s")

    if args.baseline:
        b = load(args.baseline)
        b = b[0] if isinstance(b, list) else b
        print(f"\n═══ 与裸模型基线对照 ═══")
        print(f"{'':14}{'harness':>12}{'裸模型':>12}{'差值':>12}")
        print(f"{'动作数':14}{actions:>12}{b.get('actions', '-')!s:>12}{actions - b.get('actions', 0):>12}")
        print(f"{'成功率':14}{success_rate:>11.0%}{b.get('success_rate', 0):>11.0%}"
              f"{success_rate - b.get('success_rate', 0):>+11.0%}")
        print(f"{'成本':14}{('$%.2f' % cost):>12}{('$%.2f' % b.get('cost_usd', 0)):>12}"
              f"{('$%+.2f' % (cost - b.get('cost_usd', 0))):>12}")
        print(f"{'wall-clock':14}{wall:>11}s{b.get('wall_sec', 0):>11}s{wall - b.get('wall_sec', 0):>+11}s")
        if success_rate > b.get("success_rate", 0) and cost > b.get("cost_usd", 0):
            print("\n判读：成功率上去了，但成本也上去了 —— 回到文章问题 5：动作少不一定快，supervisor 很重的话可能又慢又贵。")
        if success_rate > b.get("success_rate", 0) and actions < b.get("actions", 10**9):
            print("\n判读：同模型横向对比里动作数更少，这是可归因的架构收益（AVO 6,624 vs VISTA 7,542 的判断方式）。")
    else:
        print("\n（未提供 --baseline：先拿同一个模型裸跑一遍同任务，否则所有改进都是自我感觉）")


if __name__ == "__main__":
    main()
