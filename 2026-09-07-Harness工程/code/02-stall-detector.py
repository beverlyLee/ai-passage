#!/usr/bin/env python3
"""02-stall-detector.py — 停滞检测
对应文章问题 4：盯轨迹，不是单步。四类停滞信号，超阈值报警并给重定向建议。

用法:
  python3 02-stall-detector.py <metrics.jsonl> [--window 8] [--file-churn 5]

metrics.jsonl 每行一个 JSON:
  {"turn": 1, "score": 0.42, "files_changed": ["a.py"], "candidates": ["v1 text..."], "error": null}
  score        本轮评估分数（验证器产出，不是 agent 自评）
  files_changed 本轮实际修改的文件列表
  candidates    本轮产生的候选描述（用于相似度估算）
  error         本轮失败原因（字符串或 null）
"""
import json
import sys
import argparse
from collections import Counter


def load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    rows.sort(key=lambda r: r.get("turn", 0))
    return rows


def ngram(s, n=3):
    s = "".join(s.split())
    return {s[i:i + n] for i in range(max(1, len(s) - n + 1))}


def similarity(a, b):
    A, B = ngram(a), ngram(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def detect(rows, window, file_churn):
    alerts = []
    recent = rows[-window:]

    # 信号 1：连续 N 轮评估分无提升（平台）
    if len(recent) >= window:
        best_before = max((r["score"] for r in rows[:-window]), default=-1)
        if max(r["score"] for r in recent) <= best_before + 1e-9:
            alerts.append(f"平台：最近 {window} 轮无任何提升（前段最佳 {best_before:.3f}）")

    # 信号 2：同一文件被反复修改
    churn = Counter(f for r in recent for f in r.get("files_changed", []))
    for f, c in churn.most_common(1):
        if c >= file_churn:
            alerts.append(f"原地打转：{f} 在 {window} 轮内被改了 {c} 次")

    # 信号 3：候选项之间相似度越来越高
    cands = [r for r in recent if r.get("candidates")]
    if len(cands) >= 3:
        sims = []
        for i in range(1, len(cands)):
            a = " ".join(cands[i - 1]["candidates"])
            b = " ".join(cands[i]["candidates"])
            sims.append(similarity(a, b))
        if len(sims) >= 2 and min(sims) > 0.8:
            alerts.append(f"候选趋同：相邻轮候选相似度 {min(sims):.2f} > 0.8，在同一个想法里打转")

    # 信号 4：失败原因在重复
    errs = Counter(r["error"] for r in recent if r.get("error"))
    if errs and errs.most_common(1)[0][1] >= max(3, window // 2):
        alerts.append(f"失败重复：『{errs.most_common(1)[0][0][:60]}』出现 {errs.most_common(1)[0][1]} 次")

    return alerts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("metrics")
    ap.add_argument("--window", type=int, default=8)
    ap.add_argument("--file-churn", type=int, default=5)
    args = ap.parse_args()

    rows = load(args.metrics)
    if not rows:
        sys.exit("no rows")
    alerts = detect(rows, args.window, args.file_churn)

    if not alerts:
        print(f"OK · {len(rows)} 轮，最近 {args.window} 轮无停滞信号")
        return

    print(f"⚠️ 检测到 {len(alerts)} 类停滞信号（supervisor 应介入重定向）：")
    for a in alerts:
        print(f"  - {a}")
    print("\n重定向建议：换一个正交策略（换数据结构 / 换依赖路径 / 回滚到上一 committed 版本再分叉），")
    print("而不是在当前方向上继续加力 —— 500 个方向里能留下 40 个的前提是敢换方向。")
    sys.exit(1)


if __name__ == "__main__":
    main()
