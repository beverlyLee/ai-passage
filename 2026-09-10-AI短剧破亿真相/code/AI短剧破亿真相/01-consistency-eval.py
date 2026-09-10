#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 短剧跨帧一致性评测（生产级门禁逻辑，纯标准库，无需 torch/clip）。

用法:
    python3 01-consistency-eval.py --frames examples/frames.jsonl --ref examples/ref.json
    python3 01-consistency-eval.py --self-test

原理（对应正文 问题 2 / 坑 1）:
    把「参考身份特征向量」与「每一帧的特征向量」做余弦相似度，
    低于阈值 threshold 的帧判为「一致性崩」，触发门禁告警。
    真实产线里特征由 CLIP / ArcFace / ConsisID 提取；本脚本用模拟向量演示口径。

已知边界:
    - 特征是模拟的（examples/ 里是手工构造的浮点列表），仅用于演示评估逻辑。
    - 真实场景请替换为 IP-Adapter / ConsisID 输出的 identity embedding。
    - 阈值 0.85 是经验起点，按角色宽容度调。
"""
import argparse
import json
import math
import os
import sys

DEFAULT_THRESHOLD = 0.85


def cosine(a, b):
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def evaluate(frames, ref_feat, threshold):
    results = []
    for fr in frames:
        sim = cosine(fr.get("feat", []), ref_feat)
        passed = sim >= threshold
        results.append({
            "frame": fr.get("frame"),
            "sim": round(sim, 4),
            "passed": passed,
            "note": fr.get("note", ""),
        })
    return results


def report(results, threshold):
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    print(f"{'frame':<12}{'cosine':<10}{'一致性':<8}note")
    print("-" * 60)
    for r in results:
        flag = "PASS" if r["passed"] else "FAIL"
        print(f"{str(r['frame']):<12}{r['sim']:<10}{flag:<8}{r['note']}")
    print("-" * 60)
    rate = (passed / total * 100) if total else 0.0
    print(f"合格帧率: {passed}/{total} = {rate:.1f}%  (阈值 {threshold})")
    if rate < 90.0:
        print("⚠️  可用率 < 90%：行业经验线之下，量产大概率翻车（坑 7）。")
    else:
        print("✅ 一致性达标，可进剪辑。")
    return rate


def self_test():
    here = os.path.dirname(os.path.abspath(__file__))
    frames = load_jsonl(os.path.join(here, "examples", "frames.jsonl"))
    ref = json.load(open(os.path.join(here, "examples", "ref.json"), encoding="utf-8"))
    results = evaluate(frames, ref["feat"], DEFAULT_THRESHOLD)
    report(results, DEFAULT_THRESHOLD)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--frames", help="帧特征 jsonl，字段 frame/feat/note")
    p.add_argument("--ref", help="参考身份特征 json，字段 feat")
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    p.add_argument("--self-test", action="store_true", help="跑内置示例数据")
    args = p.parse_args()

    if args.self_test or not args.frames:
        return self_test()

    ref = json.load(open(args.ref, encoding="utf-8"))
    frames = load_jsonl(args.frames)
    results = evaluate(frames, ref["feat"], args.threshold)
    report(results, args.threshold)


if __name__ == "__main__":
    main()
