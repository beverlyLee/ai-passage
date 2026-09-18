#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""#26 本地 RAG 问答 Agent —— 准备层（对「知识」建模错）可复现脚本。

复现三个真实坑：
  ① 切分策略错位：按字符硬切把一句话的核心概念切成两半，检索时两边都答不准。
  ② embedding 版本漂移：索引用 v1、查询用 v2，同一句话向量对不上，top1 直接答错。
  ③ 向量库持久化损坏：落盘文件被截断，重启后检索全崩；load_or_rebuild 自动重建。

运行：python3 01_rag_prep.py --self-test
切真实业务：把 Embedder 换成真模型、VectorStore 换成真向量库即可，其余逻辑不变。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rag_core import (  # noqa: E402
    Embedder, chunk_document, build_index, search, VectorStore, cosine,
)

# 一篇「退款政策」文档：核心句「七天无理由退款」必须完整落在一个 chunk 里才查得准。
DOC = (
    "我们的退款政策如下。用户在签收商品后七天无理由退款。"
    "生鲜类商品不支持退款。运费由买家承担。客服会在两个工作日内处理退款申请。"
)

QUERY = "七天无理由退款怎么操作"


def test_chunk_strategy():
    """坑①：fixed 硬切会切断「七天无理由退款」这句话。"""
    fixed = chunk_document(DOC, strategy="fixed", size=20)
    sentence = chunk_document(DOC, strategy="sentence", size=120)
    # fixed 把整篇切成每段 20 字，核心句必然散落在相邻两段
    joined_fixed = "".join(fixed)
    split_core = not any("七天无理由退款" in c for c in fixed)
    # sentence 切分把核心句完整保留在某一段
    kept_core = any("七天无理由退款" in c for c in sentence)
    assert split_core, "fixed 切分反而没切断核心句，测试前提失效"
    assert kept_core, "sentence 切分没保留核心句完整"
    print("[1] 切分错位：fixed 切断核心句, sentence 保留 -> OK")
    return fixed, sentence


def test_embedding_drift():
    """坑②：version 漂移让同一句话向量失配。"""
    e1 = Embedder("v1")
    same_v = cosine(e1.embed(QUERY), e1.embed(QUERY))
    e2 = Embedder("v2")
    drift = cosine(e1.embed(QUERY), e2.embed(QUERY))
    assert same_v > 0.999, "同版本余弦应≈1"
    assert drift < 0.3, "跨版本余弦应明显偏低（向量对不上）"
    print(f"[2] embedding 漂移：同版={same_v:.3f} 跨版={drift:.3f} -> OK")
    return e1, e2


def test_store_corruption():
    """坑③：向量库文件损坏后，load_or_rebuild 从源文档重建。"""
    e1 = Embedder("v1")
    records = build_index([DOC], e1, strategy="sentence", size=120)
    path = os.path.join(tempfile.gettempdir(), "rag_store_demo.json")
    VectorStore.save(path, records)
    # 模拟损坏：截断文件
    with open(path, "r+", encoding="utf-8") as f:
        data = f.read()
        f.seek(0)
        f.write(data[: len(data) // 2])  # 写回一半 => JSON 损坏
        f.truncate()
    recovered = VectorStore.load_or_rebuild(path, lambda: records)
    assert len(recovered) == len(records), "重建后 chunk 数应一致"
    assert recovered[0][2] == records[0][2], "重建后文本应一致"
    print(f"[3] 向量库损坏：截断后自动重建 {len(recovered)} 个 chunk -> OK")
    return e1, records, path


def test_index_query_consistency():
    """整合：索引/查询同版本 -> top1 正确；跨版本 -> top1 答错。"""
    e1 = Embedder("v1")
    e2 = Embedder("v2")
    recs_v1 = build_index([DOC], e1, strategy="sentence", size=120)
    q_v1 = search(recs_v1, e1.embed(QUERY), topk=1)
    recs_v2 = build_index([DOC], e2, strategy="sentence", size=120)
    q_v2 = search(recs_v2, e1.embed(QUERY), topk=1)  # 索引是 v2，查询用 v1
    assert "七天无理由退款" in q_v1[0][3], "同版本应检索到含核心句的 chunk"
    assert q_v1[0][0] > 0.35, "同版本 top1 应有较高相似度"
    assert q_v2[0][0] < 0.3, "跨版本 top1 相似度应很低（向量失配）"
    print(f"[4] 索引/查询一致性：同版命中(score={q_v1[0][0]:.2f}), 跨版漂移(score={q_v2[0][0]:.2f}) -> OK")


def run_selftest():
    test_chunk_strategy()
    test_embedding_drift()
    test_store_corruption()
    test_index_query_consistency()
    print("ALL_SELFTESTS_PASSED")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        run_selftest()
    else:
        print("usage: python3 01_rag_prep.py --self-test")
