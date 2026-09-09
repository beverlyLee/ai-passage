#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆库体检：找出过期、冲突、无出处、没人读的条目。

记忆系统最典型的腐烂方式不是「存错了」，是「存对了但再也没管过」：
旧事实不失效、同一件事存了三个互相打架的版本、来源不明却一直被当作可信输入。

用法：
    python 02-stale-fact-scan.py --memory memory.jsonl [--now 2026-09-09] [--stale-days 90]

输入（每行一条）：
    {"id": str, "text": str,
     "subject": str?, "predicate": str?, "object": str?,   # 有这三个字段才能做冲突检测
     "valid_from": "YYYY-MM-DD"?, "valid_to": "YYYY-MM-DD"?,  # null / 缺省 = 仍然有效
     "source": str?,          # user_stated | agent_inferred | external_content
     "ingested_at": "YYYY-MM-DD"?, "last_read_at": "YYYY-MM-DD"?}

检查项：
    A 无出处       缺 source 或 ingested_at —— 出事后无法溯源
    B 已过期未关   valid_to 早于今天，但没有被标记为作废
    C 事实冲突     同一 (subject, predicate) 有多条仍然有效、且 object 不同
    D 长期未读     last_read_at 距今超过 --stale-days（90 天默认）
    E 外部来源      source=external_content 却仍然有效 —— 投毒的高风险位

退出码：0 = 无 A/B/C 级问题；1 = 存在 A/B/C 级问题（可用于 CI 门禁）；2 = 参数错误。
D/E 只告警，不影响退出码。
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime

TRUST_ORDER = {"user_stated": 0, "agent_inferred": 1, "external_content": 2}


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                sys.exit(f"[错误] {path}:{ln} JSON 解析失败: {e}")
            if "id" not in obj or "text" not in obj:
                sys.exit(f"[错误] {path}:{ln} 必须含 id 与 text")
            rows.append(obj)
    return rows


def scan(rows, today, stale_days):
    problems = defaultdict(list)

    # A 无出处
    for r in rows:
        if not r.get("source") or not r.get("ingested_at"):
            problems["A"].append((r["id"], "缺 source 或 ingested_at", r["text"][:60]))

    # B 已过期未关
    for r in rows:
        vt = parse_date(r.get("valid_to"))
        if vt and vt < today and r.get("valid_to") and r.get("status") != "invalidated":
            problems["B"].append((r["id"], f"valid_to={r['valid_to']} 已过期",
                                  r["text"][:60]))

    # C 事实冲突
    groups = defaultdict(list)
    for r in rows:
        s, p, o = r.get("subject"), r.get("predicate"), r.get("object")
        if s and p and o and not r.get("valid_to") and r.get("status") != "invalidated":
            groups[(s, p)].append(r)
    for (s, p), items in groups.items():
        objs = {i["object"] for i in items}
        if len(objs) > 1:
            ids = [i["id"] for i in items]
            problems["C"].append((ids[0],
                                  f"「{s} · {p}」有 {len(objs)} 个互相冲突的当前值",
                                  " / ".join(sorted(objs))[:60]))

    # D 长期未读
    for r in rows:
        lr = parse_date(r.get("last_read_at"))
        if r.get("last_read_at") and lr and (today - lr).days > stale_days:
            problems["D"].append((r["id"],
                                  f"{(today - lr).days} 天没被读过", r["text"][:60]))

    # E 外部来源仍有效
    for r in rows:
        if r.get("source") == "external_content" and not r.get("valid_to"):
            problems["E"].append((r["id"], "外部来源却仍然有效", r["text"][:60]))

    return problems


def main():
    ap = argparse.ArgumentParser(description="记忆库体检")
    ap.add_argument("--memory", required=True)
    ap.add_argument("--now", default=None, help="当作今天的日期 YYYY-MM-DD，默认取系统日期")
    ap.add_argument("--stale-days", type=int, default=90)
    args = ap.parse_args()

    today = parse_date(args.now) or date.today()
    rows = load(args.memory)
    problems = scan(rows, today, args.stale_days)

    titles = {
        "A": "A · 无出处（出事后无法溯源）",
        "B": "B · 已过期但未关闭有效期",
        "C": "C · 事实冲突（同一件事多个当前值）",
        "D": "D · 长期未读（只告警）",
        "E": "E · 外部来源却仍然有效（投毒高风险位，只告警）",
    }

    print("=" * 68)
    print(f"记忆库体检  ({len(rows)} 条 · 今天 {today} · 未读阈值 {args.stale_days} 天)")
    print("=" * 68)

    blocking = 0
    for key in ["A", "B", "C", "D", "E"]:
        items = problems.get(key, [])
        print(f"\n{titles[key]}：{len(items)} 条")
        if not items:
            print("  ✓ 无")
            continue
        if key in ("A", "B", "C"):
            blocking += len(items)
        for mid, why, snippet in items[:10]:
            print(f"  - {mid}: {why}")
            print(f"      {snippet}")
        if len(items) > 10:
            print(f"  ... 另有 {len(items) - 10} 条")

    print()
    print("=" * 68)
    if blocking:
        print(f"结论：{blocking} 条 A/B/C 级问题。记忆的价值不在存多少，在废得准。")
        print("优先修 C（冲突），它会直接导致回答自相矛盾；再修 B（过期），再补 A（出处）。")
        return 1
    print("结论：无 A/B/C 级问题。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
