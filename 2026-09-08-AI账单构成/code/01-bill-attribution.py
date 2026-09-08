#!/usr/bin/env python3
"""01-bill-attribution.py — 把 usage 记录按计费类别分段归因。

对应文章「问题 1（立总根）」：账单 ≠ input + output，
还有 reasoning token、缓存写溢价、非生产流量三项。

输入：一份 JSONL / CSV 格式的 usage 记录，每行至少包含：
  timestamp, environment (prod/staging/ci/...),
  input_tokens, cached_input_tokens, cache_write_tokens,
  output_tokens, reasoning_tokens, model

用法：
  python3 01-bill-attribution.py usage.jsonl --pricing pricing.csv

pricing.csv 格式（每百万 token 单价，美元）：
  model,input,cached_input,cache_write,output
  claude-sonnet-4-6,3.00,0.30,3.75,15.00

不带 --pricing 时用内置的示例价目（Claude Sonnet 4.6 口径），
只用于演示，真实核算请换成你当期的价目表。
"""
import argparse
import csv
import json
import sys
from collections import defaultdict

# 示例价目：Claude Sonnet 4.6（$/MTok）。仅供演示。
DEFAULT_PRICING = {
    "*": {"input": 3.00, "cached_input": 0.30, "cache_write": 3.75, "output": 15.00},
}


def load_pricing(path):
    pricing = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pricing[row["model"]] = {
                "input": float(row["input"]),
                "cached_input": float(row["cached_input"]),
                "cache_write": float(row["cache_write"]),
                "output": float(row["output"]),
            }
    return pricing


def iter_records(path):
    """支持 .jsonl（每行一个 JSON 对象）与 .csv（带表头）。"""
    if path.endswith(".csv"):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                yield {k: (int(v) if k.endswith("tokens") else v)
                       for k, v in row.items() if v}
    else:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("usage", help="usage 记录文件（.jsonl 或 .csv）")
    ap.add_argument("--pricing", help="价目表 CSV；缺省用内置示例价目")
    args = ap.parse_args()

    pricing = load_pricing(args.pricing) if args.pricing else DEFAULT_PRICING

    # 按 (类别) 与 (环境) 两个维度累加成本
    cost_by_kind = defaultdict(float)
    cost_by_env = defaultdict(float)
    n = 0
    unparsed_models = set()

    for rec in iter_records(args.usage):
        model = rec.get("model", "*")
        rates = pricing.get(model)
        if rates is None:
            if "*" in pricing:
                rates = pricing["*"]
            else:
                unparsed_models.add(model)
                continue
        env = rec.get("environment", "unknown")

        cached = rec.get("cached_input_tokens", 0)
        cache_w = rec.get("cache_write_tokens", 0)
        fresh_in = rec.get("input_tokens", 0) - cached  # 若你的日志 input 已含 cached，请按各自口径调整
        out_v = rec.get("output_tokens", 0)
        out_r = rec.get("reasoning_tokens", 0)

        cost = (fresh_in * rates["input"]
                + cached * rates["cached_input"]
                + cache_w * rates["cache_write"]
                + (out_v + out_r) * rates["output"]) / 1_000_000

        kind = "reasoning(hidden)" if out_r else "visible"
        cost_by_kind[f"input:fresh"] += fresh_in * rates["input"] / 1_000_000
        cost_by_kind[f"input:cached"] += cached * rates["cached_input"] / 1_000_000
        cost_by_kind[f"input:cache-write"] += cache_w * rates["cache_write"] / 1_000_000
        cost_by_kind[f"output:visible"] += out_v * rates["output"] / 1_000_000
        cost_by_kind[f"output:reasoning"] += out_r * rates["output"] / 1_000_000
        cost_by_env[env] += cost
        n += 1

    total = sum(cost_by_kind.values())
    if total == 0:
        print("没有可归因的记录。检查字段名与文件格式。")
        sys.exit(1)

    print(f"记录数: {n}    总成本: ${total:,.2f}\n")
    print("== 按计费类别 ==")
    for kind, c in sorted(cost_by_kind.items(), key=lambda kv: -kv[1]):
        bar = "#" * max(1, int(c / total * 40))
        print(f"  {kind:<20} ${c:>10,.2f}  {c / total * 100:5.1f}%  {bar}")

    print("\n== 按环境 ==")
    for env, c in sorted(cost_by_env.items(), key=lambda kv: -kv[1]):
        print(f"  {env:<12} ${c:>10,.2f}  {c / total * 100:5.1f}%")

    nonprod = sum(c for e, c in cost_by_env.items() if e not in ("prod", "production"))
    if nonprod / total > 0.1:
        print(f"\n[!] 非生产流量占 {nonprod / total * 100:.1f}%。"
              f"企业口径下 CI/staging 占 30%-50% 很常见，给每个请求打上 environment 标签。")
    if cost_by_kind["output:reasoning"] / total > 0.4:
        print("[!] reasoning token 占比过高：检查是否所有任务都开着高 effort。")


if __name__ == "__main__":
    main()
