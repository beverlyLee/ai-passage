#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分层召回评测：按 LongMemEval 五类分别打分。

为什么必须分开测：一个总分会掩盖最值钱的信息。很多系统「单会话召回」接近满分，
把总分拉上去，而「知识更新」和「时序推理」是灾难 —— 那两类恰恰是记忆系统存在的理由。

用法：
    python 01-memory-recall-eval.py --cases cases.jsonl --memory memory.jsonl --k 5

输入格式：
    memory.jsonl  每行 {"id": str, "text": str, "valid_from": "YYYY-MM-DD"?,
                        "valid_to": "YYYY-MM-DD"?, "source": str?}
    cases.jsonl   每行 {"id": str, "category": str, "question": str,
                        "must_hit": ["mem_id_1", ...]}

category 建议取值（对应 LongMemEval 五类）：
    single_session  单会话召回
    preference      偏好追踪
    multi_session   多会话推理
    knowledge_update 知识更新
    temporal        时序推理

输出：每个类别的 recall@k、样本数，以及全局最差类别提示。
退出码：0 = 跑完；2 = 参数/文件错误。

依赖：仅标准库。默认检索器是字符 2-gram TF-IDF + 余弦，
换成真实检索器见文件底部 CUSTOM RETRIEVER 说明。
"""

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict

CATEGORIES = [
    "single_session",
    "preference",
    "multi_session",
    "knowledge_update",
    "temporal",
]

CAT_LABEL = {
    "single_session": "单会话召回",
    "preference": "偏好追踪",
    "multi_session": "多会话推理",
    "knowledge_update": "知识更新",
    "temporal": "时序推理",
}


def tokenize(text):
    """中文 + 英文混合的廉价切分：英文按词，中文按 2-gram。"""
    text = text.lower()
    grams = []
    for word in re.findall(r"[a-z0-9_]+", text):
        grams.append(word)
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(run) == 1:
            grams.append(run)
        for i in range(len(run) - 1):
            grams.append(run[i:i + 2])
    return grams or ["<empty>"]


class TfidfRetriever:
    """基线检索器：字符/词 n-gram TF-IDF + 余弦。零依赖，用来当对照组。"""

    def __init__(self, docs):
        self.ids = [d["id"] for d in docs]
        self.docs = [tokenize(d["text"]) for d in docs]
        self.df = Counter()
        for toks in self.docs:
            self.df.update(set(toks))
        self.n = len(self.docs)
        self.vecs = [self._vec(toks) for toks in self.docs]

    def _tf(self, toks):
        c = Counter(toks)
        total = len(toks)
        return {t: cnt / total for t, cnt in c.items()}

    def _vec(self, toks):
        tf = self._tf(toks)
        vec = {}
        for t, v in tf.items():
            idf = math.log((self.n + 1) / (self.df.get(t, 0) + 1)) + 1.0
            vec[t] = v * idf
        norm = math.sqrt(sum(x * x for x in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def search(self, query, k=5):
        q = self._vec(tokenize(query))
        scores = []
        for idx, v in enumerate(self.vecs):
            s = sum(val * q.get(t, 0.0) for t, val in v.items())
            scores.append((s, self.ids[idx]))
        scores.sort(key=lambda x: (-x[0], x[1]))
        return [i for _, i in scores[:k]]


def load_jsonl(path, required):
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
            missing = [k for k in required if k not in obj]
            if missing:
                sys.exit(f"[错误] {path}:{ln} 缺少字段 {missing}")
            rows.append(obj)
    return rows


def main():
    ap = argparse.ArgumentParser(description="分层召回评测")
    ap.add_argument("--cases", required=True, help="测试集 jsonl")
    ap.add_argument("--memory", required=True, help="记忆库 jsonl")
    ap.add_argument("--k", type=int, default=5, help="recall@k 的 k，默认 5")
    ap.add_argument(
        "--retriever",
        default=None,
        help="自定义检索器，格式 module.py:FactoryName，Factory(docs) -> obj.search(q, k)",
    )
    ap.add_argument("--fail-under", type=float, default=None,
                    help="任一类 recall@k 低于该值则退出码为 1（用于 CI 门禁）")
    args = ap.parse_args()

    docs = load_jsonl(args.memory, required=["id", "text"])
    cases = load_jsonl(args.cases, required=["id", "category", "question", "must_hit"])

    if args.retriever:
        mod_path, _, factory = args.retriever.partition(":")
        if not mod_path or not factory:
            sys.exit("[错误] --retriever 格式应为 module.py:FactoryName")
        import importlib.util
        spec = importlib.util.spec_from_file_location("custom_retriever", mod_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        retriever = getattr(mod, factory)(docs)
    else:
        retriever = TfidfRetriever(docs)

    known_ids = {d["id"] for d in docs}
    per_cat = defaultdict(lambda: {"hit": 0.0, "total": 0.0, "cases": 0})
    worst_examples = []

    for c in cases:
        cat = c["category"]
        if cat not in CATEGORIES:
            cat = cat  # 允许自定义类别，只是没有中文标签
        must = list(c["must_hit"])
        if not must:
            continue
        bad = [m for m in must if m not in known_ids]
        if bad:
            print(f"[警告] 用例 {c['id']} 的 must_hit 在记忆库中不存在: {bad}", file=sys.stderr)

        got = set(retriever.search(c["question"], args.k))
        hit = sum(1 for m in must if m in got)
        rec = hit / len(must)

        bucket = per_cat[cat]
        bucket["hit"] += rec
        bucket["total"] += 1
        bucket["cases"] += 1
        if rec < 1.0:
            worst_examples.append((rec, c["id"], cat, c["question"],
                                   [m for m in must if m not in got]))

    print("=" * 68)
    print(f"分层召回评测  (k={args.k}, 记忆 {len(docs)} 条, 用例 {len(cases)} 条)")
    print("=" * 68)
    print(f"{'类别':<26}{'recall@k':>10}{'用例数':>8}")
    print("-" * 68)

    ordered = CATEGORIES + [k for k in per_cat if k not in CATEGORIES]
    scores = {}
    for cat in ordered:
        if cat not in per_cat:
            continue
        b = per_cat[cat]
        r = b["hit"] / b["total"] if b["total"] else 0.0
        scores[cat] = r
        label = f"{cat} / {CAT_LABEL.get(cat, '自定义')}"
        print(f"{label:<26}{r:>9.1%}{int(b['total']):>8}")
    print("-" * 68)

    if scores:
        overall = sum(scores.values()) / len(scores)
        worst_cat = min(scores, key=scores.get)
        print(f"{'五类均值（非总分）':<26}{overall:>9.1%}")
        print()
        print(f"最弱类别：{worst_cat} / {CAT_LABEL.get(worst_cat, '自定义')} "
              f"({scores[worst_cat]:.1%})")
        if worst_cat in ("knowledge_update", "temporal"):
            print("  ⚠ 这两类正是记忆系统的立身之本。"
                  "低分通常意味着没有失效机制，而不是 embedding 不够好。")

    if worst_examples:
        worst_examples.sort(key=lambda x: x[0])
        print()
        print("未完全命中的用例（按召回率升序，最多 8 条）：")
        for rec, cid, cat, q, miss in worst_examples[:8]:
            print(f"  [{rec:.0%}] {cid} ({cat}) {q[:34]}")
            print(f"         未召回: {miss}")

    rc = 0
    if args.fail_under is not None and scores:
        bad = [c for c, r in scores.items() if r < args.fail_under]
        if bad:
            print(f"\n[门禁失败] 低于 {args.fail_under:.0%} 的类别: {bad}")
            rc = 1
    return rc


# ---------------------------------------------------------------------------
# CUSTOM RETRIEVER
# ---------------------------------------------------------------------------
# 接入真实检索器：写一个模块，暴露 Factory(docs) -> obj，obj.search(query, k) -> [id]
#   然后：python 01-memory-recall-eval.py --cases c.jsonl --memory m.jsonl \
#           --retriever my_retriever.py:MyRetriever
# 这样基线（TF-IDF）和你线上的检索器可以同场对比。
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(main())
