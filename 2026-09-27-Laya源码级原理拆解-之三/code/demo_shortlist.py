#!/usr/bin/env python3
"""demo_shortlist.py — 复刻 laya/shortlist.py 的「粗到细 shortlist」算法。

纯标准库，不依赖 torch / numpy。核心：_rank 用余弦相似度对高基数 choice 选项裁到 top-k，
_embeddings / _cosine / cached_embed_fn(LRU) 全部用纯 Python 重写，语义对齐源码。
运行 `python demo_shortlist.py --self-test` 自检全绿，标准输出即正文引用的「预期输出」。

一手来源：/tmp/laya-src/laya/shortlist.py（MIT，NandhaKishorM/laya）。
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Sequence

DEFAULT_SHORTLIST_K = 20

# BANKING77 风格的高基数选项：一封退款邮件应当被路由到 refund / billing 附近
DEPARTMENTS = {
    "refund_requests": "refund money back",
    "billing_invoices": "invoices payments refund",
    "payment_issue": "payment failed credit card",
    "account_security": "password login hacked",
    "technical_bugs": "bug crash error outage",
    "api_docs": "api integration sdk webhook",
    "feature_request": "feature idea suggestion",
    "data_export": "export download csv report",
    "subscription": "plan upgrade downgrade renew",
    "order_status": "order shipped tracking delivery",
    "shipping": "ship address courier post",
    "login_help": "cannot sign in otp code",
    "product_feedback": "love hate review experience",
    "partnership": "partner reseller affiliate",
    "careers": "job hire intern apply",
    "press": "media journalist interview",
    "legal": "contract terms law compliance",
    "complaint": "angry upset terrible service",
    "thanks": "thank you great appreciate",
    "general_question": "how does this work explain",
    "other": "none of the above",
    "spam_promo": "win prize discount buy now",
    "survey": "poll questionnaire rate us",
    "event_invite": "webinar conference meetup talk",
    "community": "forum group discord channel",
}

STOP = {
    "the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "on", "for", "and",
    "or", "but", "this", "that", "it", "my", "we", "you", "i", "please", "with", "as",
    "at", "by", "from", "be", "been", "have", "has", "had", "not", "no", "so", "if",
}


def _embed_one(text: str, dim: int = 16) -> List[float]:
    """确定性 bag-of-words 嵌入：把文本按词哈希进 dim 维再 L2 归一，纯 Python 复刻 mean-pool 的「语义近 = 向量近」。"""
    vec = [0.0] * dim
    for tok in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if tok in STOP:
            continue
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16) % dim
        vec[h] += 1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0.0:
        vec = [x / norm for x in vec]
    return vec


def make_embed_fn(dim: int = 512) -> Callable[[Sequence[str]], List[List[float]]]:
    """把单文本嵌入包成「文本列表 -> 行向量列表」的 embed_fn，契合 shortlist 的调用约定。"""
    def batch(texts: Sequence[str]) -> List[List[float]]:
        return [_embed_one(t, dim) for t in texts]
    return batch


def _render_choice_options(criteria: Any) -> List[str]:
    if isinstance(criteria, dict):
        return [str(k) if v is None or v == "" else "%s: %s" % (k, v) for k, v in criteria.items()]
    return [str(c) for c in criteria]


def serialize_state(state: Any) -> str:
    if isinstance(state, str):
        return state
    return json.dumps(state, ensure_ascii=False)


def _query_text(state: Any, instructions: Any) -> str:
    body = serialize_state(state)
    if instructions is None or instructions == "":
        return body
    if not isinstance(instructions, str):
        instructions = json.dumps(instructions, ensure_ascii=False)
    return "%s\n%s" % (instructions, body)


def _cosine(query: List[float], docs: List[List[float]]) -> List[float]:
    qn = math.sqrt(sum(x * x for x in query))
    if qn == 0.0 or len(docs) == 0:
        return [0.0] * len(docs)
    out = []
    for d in docs:
        dn = math.sqrt(sum(x * x for x in d))
        if dn == 0.0 or qn == 0.0:
            out.append(0.0)
            continue
        dot = sum(a * b for a, b in zip(query, d))
        sim = dot / (dn * qn)
        out.append(max(-1.0, min(1.0, sim)))
    return out


def _embeddings(embed_fn: Callable, texts: Sequence[str]) -> List[List[float]]:
    raw = embed_fn(list(texts))
    rows: List[List[float]] = []
    for r in raw:
        rows.append([float(x) for x in r])
    if len(rows) != len(texts) or (rows and len(rows[0]) < 1):
        raise ValueError("embed_fn must return one row per text")
    return rows


def _rank(state, criteria, embed_fn, k, instructions):
    items = list(criteria.items()) if isinstance(criteria, dict) else [(c, None) for c in criteria]
    n = len(items)
    keys = [key for key, _ in items]
    if k >= n:
        return list(keys), None, True, n
    query = _query_text(state, instructions)
    matrix = _embeddings(embed_fn, [query] + _render_choice_options(criteria))
    sims = _cosine(matrix[0], matrix[1:])
    order = sorted(range(n), key=lambda i: (-sims[i], i))[:k]
    labels = [keys[i] for i in order]
    scores = [round(sims[i], 4) for i in order]
    return labels, scores, False, n


def shortlist_choice(state, criteria, embed_fn, k: int = DEFAULT_SHORTLIST_K, *, instructions=None):
    labels, _s, _p, _n = _rank(state, criteria, embed_fn, k, instructions)
    return labels


def cached_embed_fn(embed_fn: Callable, maxsize: int = 4096):
    """纯 Python 版 LRU 缓存：与源码语义一致（锁只护缓存读写；命中按字符串精确匹配）。"""
    rows_by_text: "OrderedDict[str, List[float]]" = OrderedDict()
    lock = threading.Lock()
    counts = {"hits": 0, "misses": 0}

    def cached(texts: Sequence[str]):
        keys = ["" if t is None else str(t) for t in texts]
        if not keys:
            return []
        with lock:
            found: Dict[str, List[float]] = {}
            for key in keys:
                row = rows_by_text.get(key)
                if row is not None:
                    rows_by_text.move_to_end(key)
                    found[key] = row
                    counts["hits"] += 1
                else:
                    counts["misses"] += 1
            missing = [k for k in dict.fromkeys(keys) if k not in found]
        if missing:
            fresh = _embeddings(embed_fn, missing)
            with lock:
                for key, row in zip(missing, fresh):
                    rows_by_text[key] = row
                    rows_by_text.move_to_end(key)
                    while len(rows_by_text) > maxsize:
                        rows_by_text.popitem(last=False)
                    found[key] = row
        return [found[k] for k in keys]

    def cache_info():
        with lock:
            return {"size": len(rows_by_text), "maxsize": maxsize,
                    "hits": counts["hits"], "misses": counts["misses"]}

    cached.cache_info = cache_info
    return cached


def _demo():
    instructions = "Which team should handle the email in `body`?"
    state = ("Subject: Refund not received\n"
             "I paid last week but the refund never came back, please refund my card.")
    embed = make_embed_fn()  # 确定性嵌入

    print("=== 粗到细 shortlist（25 个部门，k=10）===")
    labels = shortlist_choice(state, DEPARTMENTS, embed, k=10, instructions=instructions)
    print("  输入选项数 n = %d，取 top-k = 10" % len(DEPARTMENTS))
    for i, lab in enumerate(labels, 1):
        print("  #%-2d %s" % (i, lab))

    print()
    print("=== k >= n 时原序透传，不调用 embed_fn ===")
    small = {"a": "x", "b": "y", "c": "z"}
    calls = {"n": 0}

    def counting_embed(texts):
        calls["n"] += 1
        return [_embed(t) for t in texts]

    out = shortlist_choice(state, small, counting_embed, k=20, instructions=instructions)
    print("  返回顺序: %s  embed_fn 调用次数: %d" % (out, calls["n"]))

    print()
    print("=== LRU 缓存：重复 shortlist 只重嵌新 query ===")
    cached = cached_embed_fn(embed)
    shortlist_choice(state, DEPARTMENTS, cached, k=10, instructions=instructions)
    info1 = cached.cache_info()
    shortlist_choice(state, DEPARTMENTS, cached, k=10, instructions=instructions)
    info2 = cached.cache_info()
    print("  第一次: %s" % info1)
    print("  第二次: %s  (hits 增长 = 选项行被复用)" % info2)


def _self_test():
    embed = make_embed_fn()
    instructions = "Which team should handle the email in `body`?"
    state = "Subject: Refund not received\nI paid last week but the refund never came back, please refund my card."

    # 1) top-1 必须是 refund_requests（与 query 共享 refund 词）
    top = shortlist_choice(state, DEPARTMENTS, embed, k=10, instructions=instructions)
    assert top[0] == "refund_requests", top

    # 2) k >= n 透传且 embed_fn 不被调用
    small = {"a": "x", "b": "y", "c": "z"}
    calls = {"n": 0}

    def ce(texts):
        calls["n"] += 1
        return [_embed(t) for t in texts]

    out = shortlist_choice(state, small, ce, k=20, instructions=instructions)
    assert out == ["a", "b", "c"] and calls["n"] == 0, (out, calls)

    # 3) 余弦：零向量 -> 0；完全同向 -> 1
    assert _cosine([0.0, 0.0], [[1.0, 0.0]]) == [0.0]
    assert abs(_cosine([1.0, 1.0], [[1.0, 1.0]])[0] - 1.0) < 1e-9

    # 4) LRU：第二次调用应产生命中
    cached = cached_embed_fn(embed)
    shortlist_choice(state, DEPARTMENTS, cached, k=10, instructions=instructions)
    first = cached.cache_info()["hits"]
    shortlist_choice(state, DEPARTMENTS, cached, k=10, instructions=instructions)
    second = cached.cache_info()["hits"]
    assert second > first, (first, second)

    print("self-test PASS: 排序/透传/余弦/缓存 全部符合预期")


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        _self_test()
    else:
        _demo()
