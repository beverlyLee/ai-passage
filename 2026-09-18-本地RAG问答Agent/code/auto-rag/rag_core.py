#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地 RAG 问答 Agent 的纯标准库内核（无外部模型依赖）。

提供：
  - Embedder：基于哈希技巧的确定性「假 embedding」，version 不同 => 向量空间不同（模拟版本漂移）。
  - chunk_document：两种切分策略（fixed 硬切 / sentence 语义切）。
  - VectorStore：JSON 持久化 + 损坏自动重建（模拟向量库持久化损坏）。
  - build_index / search：建索引与余弦检索。

设计目标：让三层脚本（准备 / 检索 / 生成）都能独立 self-test，
切到真实业务时只需把 Embedder 换成真模型、把 VectorStore 换成真向量库。
"""
import json
import math
import os
import re
import hashlib


def tokenize(text: str):
    """分词：英文/数字按词，中文按单字（unigram）。

    中文没有天然空格边界，按「短语整串」成 token 会让稍长的查询与文档无法重叠；
    按单字切能保证「七天无理由退款」这种核心词在查询与文档间逐字命中，
    也更符合真实中文 lexical 检索的行为。
    """
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    cjk = re.findall(r"[一-鿿]", text)
    return words + cjk


def _hash_full(token: str, salt: str) -> int:
    """完整 256-bit 哈希作为向量键。用完整哈希而非取模，避免不同 token 撞到同一维。"""
    return int(hashlib.sha256((salt + "|" + token).encode("utf-8")).hexdigest(), 16)


class Embedder:
    """确定性哈希 Embedder，输出「稀疏词袋向量」：{完整哈希键: 词频}，并做 L2 归一化。

    - version 改变 salt => 同一句话得到完全不同的键集（键集不交 => 余弦=0），
      用来演示 embedding 版本漂移导致向量对不上。
    - 真实项目里这里是 sentence-transformers / OpenAI embedding；本内核用哈希技巧替代，
      保证 self-test 不依赖网络与模型权重，且零碰撞。
    """

    def __init__(self, version: str = "v1"):
        self.version = version
        self.salt = "rag-embed-" + version

    def embed(self, text: str):
        vec = {}
        for tok in tokenize(text):
            k = _hash_full(tok, self.salt)
            vec[k] = vec.get(k, 0.0) + 1.0
        norm = math.sqrt(sum(v * v for v in vec.values()))
        if norm > 0:
            for k in vec:
                vec[k] /= norm
        return vec


def cosine(a, b) -> float:
    """稀疏向量的余弦相似度，只在交集键上求和（零重叠 => 0）。"""
    if not a or not b:
        return 0.0
    inter = set(a) & set(b)
    s = sum(a[k] * b[k] for k in inter)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return s / (na * nb)


def chunk_document(text: str, strategy: str = "sentence", size: int = 120):
    """把文档切成 chunk。

    fixed：按字符硬切，size 个字符一段——最容易切断语义（坑①）。
    sentence：按句号/问号/感叹号切句，再贪心打包到 size 上限——保留语义边界。
    """
    if strategy == "fixed":
        return [text[i:i + size] for i in range(0, len(text), size)]

    # sentence-aware：先切句，再贪心合并到 size 上限
    raw = re.split(r"(?<=[。！？!?])\s*", text)
    sentences = [s.strip() for s in raw if s.strip()]
    chunks, cur = [], ""
    for s in sentences:
        if cur and len(cur) + len(s) > size:
            chunks.append(cur)
            cur = s
        else:
            cur = (cur + " " + s).strip() if cur else s
    if cur:
        chunks.append(cur)
    return chunks


class VectorStore:
    """极简向量库：JSON 落盘。损坏时 load 抛错，load_or_rebuild 自动用 builder 重建。"""

    @staticmethod
    def save(path: str, records) -> None:
        payload = {
            "records": [
                {"doc_id": d, "chunk_id": c, "text": t, "vector": v}
                for (d, c, t, v) in records
            ]
        }
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)  # 原子写，避免写到一半被读到

    @staticmethod
    def load(path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [
            (r["doc_id"], r["chunk_id"], r["text"], r["vector"])
            for r in data["records"]
        ]

    @staticmethod
    def load_or_rebuild(path: str, builder):
        try:
            return VectorStore.load(path)
        except (json.JSONDecodeError, KeyError, FileNotFoundError, OSError):
            records = builder()
            VectorStore.save(path, records)
            return records


def build_index(docs, embedder: Embedder, strategy: str = "sentence", size: int = 120):
    """对 doc 列表做切分 + embedding，返回 records：[(doc_id, chunk_id, text, vector), ...]"""
    records = []
    for doc_id, text in enumerate(docs):
        for chunk_id, ch in enumerate(chunk_document(text, strategy, size)):
            records.append((doc_id, chunk_id, ch, embedder.embed(ch)))
    return records


def search(records, query_vec, topk: int = 3):
    """余弦检索，返回按相似度降序的前 topk：(score, doc_id, chunk_id, text)"""
    scored = [
        (cosine(query_vec, vec), doc_id, chunk_id, text)
        for (doc_id, chunk_id, text, vec) in records
    ]
    scored.sort(reverse=True)
    return scored[:topk]
