#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""《后西游记》表演级情绪连续性门禁（对应正文 问题 2 / 坑 7 / 三层治理·一致性层）。

用法:
    python3 01-consistency-eval.py --self-test
    python3 01-consistency-eval.py --scene examples/frames.jsonl --max-jump 0.35
    python3 01-consistency-eval.py --scene examples/frames.jsonl --arc examples/ref.json

为什么需要这个脚本:
    AIGC 长剧的底层逻辑是「定帧」——每 15 秒左右的定帧之间，情绪衔接交给模型。
    武戏可以「一步一景」堆奇观，文戏却要求相邻定帧的情绪连贯、微表情不僵。
    总导演李东珅的原话是「被一根尾巴卡住十天」，难的不是画面，是情绪表达；
    观众也吐槽《后西游记》「部分素材表情僵硬、节奏偏慢」。

    本脚本把「表演级情绪」表示成向量（6 维：[喜悦, 悲伤, 愤怒, 恐惧, 惊讶, 平静]，0~1），
    对相邻定帧计算情绪跳变（欧氏距离），跳变过大 = 微表情僵硬 / 情绪断层，触发门禁。
    另支持 --arc 把实际情绪弧线与「剧本期望弧线」对比，定位偏离最大的僵硬帧。

门禁逻辑:
    相邻定帧情绪跳变 = 向量欧氏距离；> max_jump(默认 0.35) 判为「断裂」。
    一段文戏「断裂间隙占比」> max_broken_rate(默认 10%) → 文戏不合格、不许进剪辑。

已知边界:
    - emotion 是手工构造的模拟向量，仅演示评估口径；真实产线由表情/表演分析模型输出。
    - 阈值 0.35 / 10% 为经验起点，按文戏宽容度调。
"""
import argparse
import json
import math
import os


DEFAULT_MAX_JUMP = 0.35
DEFAULT_MAX_BROKEN_RATE = 0.10


def euclid(a, b):
    if len(a) != len(b):
        return float("inf")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def load_scene(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def evaluate_adjacency(scene, max_jump):
    """逐间隙检测相邻定帧的情绪跳变。"""
    results = []
    for i in range(len(scene) - 1):
        a, b = scene[i], scene[i + 1]
        dist = euclid(a.get("emotion", []), b.get("emotion", []))
        passed = dist <= max_jump
        results.append({
            "gap": f"{a.get('frame')}→{b.get('frame')}",
            "dist": round(dist, 4),
            "passed": passed,
            "note": b.get("note", ""),
        })
    return results


def evaluate_arc(scene, arc):
    """实际情绪弧线 vs 剧本期望弧线，逐帧偏差。"""
    results = []
    for fr, expected in zip(scene, arc):
        dist = euclid(fr.get("emotion", []), expected)
        results.append({
            "frame": fr.get("frame"),
            "deviation": round(dist, 4),
            "note": fr.get("note", ""),
        })
    return results


def report_adjacency(results, max_jump, max_broken_rate):
    total = len(results)
    broken = sum(1 for r in results if not r["passed"])
    print(f"{'gap':<10}{'jump':<10}{'判定':<8}note")
    print("-" * 64)
    for r in results:
        flag = "PASS" if r["passed"] else "FAIL"
        print(f"{r['gap']:<10}{r['dist']:<10}{flag:<8}{r['note']}")
    print("-" * 64)
    rate = (broken / total * 100) if total else 0.0
    print(f"断裂间隙占比: {broken}/{total} = {rate:.1f}%  (门禁 {max_broken_rate*100:.0f}%)")
    if rate > max_broken_rate * 100:
        print("⚠️  文戏不合格：情绪断层超阈值，微表情僵硬，不许进剪辑（坑 7）。")
        print("    → 开启嘴型匹配/骨骼控制/超分修复 + 重抽僵硬帧，再复测。")
    else:
        print("✅ 情绪连续达标，可进剪辑。")
    return rate


def report_arc(results):
    worst = max(results, key=lambda r: r["deviation"])
    print(f"{'frame':<8}{'deviation':<12}note")
    print("-" * 60)
    for r in results:
        print(f"{str(r['frame']):<8}{r['deviation']:<12}{r['note']}")
    print("-" * 60)
    print(f"最大偏离在 frame {worst['frame']}（{worst['deviation']}）：{worst['note']}")
    print("→ 该帧与剧本期望情绪弧线脱节，是微表情僵硬/不连贯的高危点（坑 7）。")


def self_test():
    here = os.path.dirname(os.path.abspath(__file__))
    scene = load_scene(os.path.join(here, "examples", "frames.jsonl"))
    print("=== 模式 A：相邻定帧情绪跳变门禁（演示一处僵硬帧拖垮整段文戏）===")
    adj = evaluate_adjacency(scene, DEFAULT_MAX_JUMP)
    report_adjacency(adj, DEFAULT_MAX_JUMP, DEFAULT_MAX_BROKEN_RATE)
    print()
    print("=== 模式 B：实际情绪弧线 vs 剧本期望弧线 ===")
    arc = json.load(open(os.path.join(here, "examples", "ref.json"), encoding="utf-8"))
    arc_res = evaluate_arc(scene, arc["arc"])
    report_arc(arc_res)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scene", help="定帧情绪向量 jsonl，字段 frame/emotion/note")
    p.add_argument("--arc", help="剧本期望情绪弧线 json，字段 arc（与 scene 等长向量列表）")
    p.add_argument("--max-jump", type=float, default=DEFAULT_MAX_JUMP, help="相邻跳变门禁")
    p.add_argument("--max-broken-rate", type=float, default=DEFAULT_MAX_BROKEN_RATE, help="断裂间隙占比上限")
    p.add_argument("--self-test", action="store_true", help="跑内置示例数据")
    args = p.parse_args()

    if args.self_test or not args.scene:
        return self_test()

    scene = load_scene(args.scene)
    if args.arc:
        arc = json.load(open(args.arc, encoding="utf-8"))
        report_arc(evaluate_arc(scene, arc["arc"]))
    else:
        report_adjacency(evaluate_adjacency(scene, args.max_jump),
                         args.max_jump, args.max_broken_rate)


if __name__ == "__main__":
    main()
