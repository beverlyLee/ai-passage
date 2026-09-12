#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02-cognitive-load-detector.py
AI 文本认知负载检测器：用两个纯标准库可算的风格指标，判断一段文本"更像人写还是 AI 写"。

指标（风格计量学常用代理，无需语言模型）：
  - 突发度 burstiness = 句长序列的 标准差 / 均值（0=每句等长，越大越"像人"）
  - 词汇多样性 type-token ratio (TTR) = 去重词数 / 总词数（越大越"像人"）

为什么这关认知负载：AI 文本突发度低、TTR 低（平滑、均匀、套路化），
人拿去用之前必须自己补"结构、立场、判断"——这一步就是正文机制③说的
extraneous load（外在认知负载）。本脚本帮你快速标记"这段需要我亲自整合/判断"。

对应正文机制③（认知负载激增）与图4。

用法：
  python3 02-cognitive-load-detector.py --self-test
  python3 02-cognitive-load-detector.py --text "你的文本..."
  cat a.txt | python3 02-cognitive-load-detector.py --stdin

纯标准库，无第三方依赖。
"""
import argparse
import math
import re
import sys


def sentences(text):
    # 以中英文句号/换行切句，过滤空句
    parts = re.split(r"[。！？!?\n]+", text)
    return [p.strip() for p in parts if p.strip()]


def words(text):
    # 中文按字、英文按词，统一成 token 序列（粗略但足够风格对比）
    toks = re.findall(r"[A-Za-z]+|[一-鿿]", text)
    return toks


def burstiness(text):
    lens = [len(s) for s in sentences(text)]
    n = len(lens)
    if n < 2:
        return 0.0
    mean = sum(lens) / n
    if mean == 0:
        return 0.0
    var = sum((x - mean) ** 2 for x in lens) / n
    return math.sqrt(var) / mean


def ttr(text):
    ws = words(text)
    if not ws:
        return 0.0
    return len(set(ws)) / len(ws)


def classify(text):
    b = burstiness(text)
    t = ttr(text)
    # 主判据是突发度（中文 TTR 天然偏高，不宜单独作硬阈值）：
    #   突发度 < 0.35 偏向 AI 套路化（句长均匀、平行结构）
    #   突发度 >= 0.35 偏向人写（句长有起伏）
    # TTR 仅作辅助：对含英文的文本更有区分度。
    ai_likely = b < 0.35
    label = "AI-like（句长均匀/平行结构，需你亲自整合判断）" if ai_likely else "human-like（句长有起伏）"
    return {
        "sentences": len(sentences(text)),
        "tokens": len(words(text)),
        "burstiness": b,
        "ttr": t,
        "ai_likely": ai_likely,
        "label": label,
    }


def fmt(d):
    return (
        f"  句数           : {d['sentences']}\n"
        f"  token 数       : {d['tokens']}\n"
        f"  突发度(主判据)  : {d['burstiness']:.3f}\n"
        f"  词汇多样性 TTR : {d['ttr']:.3f} (辅助)\n"
        f"  判断           : {d['label']}"
    )


HUMAN_SAMPLE = (
    "今天开会又拖了。\n"
    "累。\n"
    "我本来想下午写方案，结果被拉去对一整天的需求，里面有一半是拍脑袋想的，完全没有落地路径。\n"
    "晚上回家只想躺着，方案只开了个头。\n"
    "明天得早起，不然肯定交不上。"
)

AI_SAMPLE = (
    "在当今快速发展的数字化时代，人工智能技术正在深刻地改变着我们的工作方式。"
    "通过智能化的工具，企业能够显著提升运营效率并优化资源配置。"
    "与此同时，我们也需要关注技术在落地过程中可能带来的挑战与风险。"
    "只有在效率与责任之间取得平衡，才能实现可持续的发展目标。"
)


def self_test():
    print("== 自检 1: 人写样本（句长应有大起大落、高突发度）==")
    dh = classify(HUMAN_SAMPLE)
    print(fmt(dh))
    assert dh["burstiness"] > 0.35, f"人写样本突发度应>0.35, got {dh['burstiness']:.3f}"
    assert not dh["ai_likely"], "人写样本不应判为 AI-like"

    print("\n== 自检 2: AI 写样本（句长应均匀、低突发度）==")
    da = classify(AI_SAMPLE)
    print(fmt(da))
    assert da["burstiness"] < 0.35, f"AI 样本突发度应<0.35, got {da['burstiness']:.3f}"
    assert da["ai_likely"], "AI 样本应判为 AI-like"

    print("\n所有自检通过 ✅")
    print("注：突发度越低越'套路化'，越需要人亲自补结构/立场/判断（= 认知负载来源）。")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--text", type=str, default=None)
    p.add_argument("--stdin", action="store_true")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()

    if args.self_test or (args.text is None and not args.stdin):
        self_test()
        return

    if args.stdin:
        text = sys.stdin.read()
    else:
        text = args.text
    d = classify(text)
    print("== 文本认知负载检测 ==")
    print(fmt(d))


if __name__ == "__main__":
    main()
