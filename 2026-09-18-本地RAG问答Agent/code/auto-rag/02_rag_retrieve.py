#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""#26 本地 RAG 问答 Agent —— 检索层（对「问题↔知识对齐」建模错）可复现脚本。

复现两个真实坑：
  ④ 查询词与文档词不匹配：用户问「怎么开发票」，知识库只讲退款/物流，检索空窗=>无上下文。
  ⑤ 上下文窗口溢出截断：拼了太多 chunk，预算只够 2 段，把排名第 3 的关键 chunk 挤掉了。

运行：python3 02_rag_retrieve.py --self-test
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rag_core import Embedder, build_index, search, cosine  # noqa: E402

# 知识库只覆盖「退款」和「物流」，没有「发票」
DOCS = [
    "用户在签收商品后七天无理由退款。生鲜类不支持退款。",
    "退款申请会在两个工作日内由客服处理。运费由买家承担。",
    "物流时效为下单后三到五天送达。偏远地区另计。",
    "包裹丢失可联系客服重寄。需要提供订单编号。",
]

def safe_retrieve(records, query, embedder, topk=3, floor=0.05):
    """带空窗保护的检索：最佳相似度低于 floor 视为检索空窗，返回 []。"""
    ranked = search(records, embedder.embed(query), topk=topk)
    best = ranked[0][0] if ranked else 0.0
    if best < floor:
        return []  # 检索空窗：宁可给模型「我不知道」，也不要拿无关文本硬答
    return ranked


def select_by_budget(ranked, budget_chunks: int):
    """模拟上下文窗口：只取前 budget_chunks 段，其余截断。"""
    return ranked[:budget_chunks]


def test_query_mismatch_blank():
    """坑④：问「发票」这种知识库没有的词，检索应返回空窗。"""
    e = Embedder("v1")
    recs = build_index(DOCS, e, strategy="sentence", size=120)
    out = safe_retrieve(recs, "如何开具增值税发票", e, topk=3)
    assert out == [], "知识库无发票内容，检索应判空窗"
    # 对照：问域内问题能正常命中
    hit = safe_retrieve(recs, "退款需要几天", e, topk=3)
    assert hit and hit[0][0] > 0.05, "域内问题应能命中"
    print("[1] 查询词不匹配：域外问「发票」命中空窗, 域内问「退款」正常 -> OK")


def test_context_overflow_drops_key_chunk():
    """坑⑤：检索其实命中了正确 chunk，但上下文预算只够前 2 段，把它截断丢失。

    这里用一次真实检索常见的排序形态建模：前两段与问题表面相关（退款/运费），
    但真正能回答「多久到」的是排第 3 的物流条款；预算过小就把来源挤掉了。
    """
    ranked = [
        (0.62, 0, 0, "七天无理由退款。生鲜类不支持退款。"),
        (0.55, 1, 0, "退款申请会在两个工作日内处理。运费由买家承担。"),
        (0.41, 2, 0, "物流时效为下单后三到五天送达。偏远地区另计。"),
        (0.20, 3, 0, "包裹丢失可联系客服重寄。需要提供订单编号。"),
    ]
    pos = 2  # 关键 chunk（物流时效）排第 3
    small = select_by_budget(ranked, budget_chunks=2)
    big = select_by_budget(ranked, budget_chunks=len(ranked))
    assert all(r[1] != 2 for r in small), "预算=2 时关键 chunk 被截断丢失"
    assert any(r[1] == 2 for r in big), "预算足够时关键 chunk 保留"
    print(f"[2] 上下文溢出：关键 chunk 排第{pos+1}位, 预算=2 被截断, 预算充足保留 -> OK")


def test_retrieval_recall_sane():
    """好路径：域内问题 top1 能命中正确文档。"""
    e = Embedder("v1")
    recs = build_index(DOCS, e, strategy="sentence", size=120)
    top = search(recs, e.embed("退款几天到账"), topk=1)[0]
    assert top[1] in (0, 1), "退款类问题应命中退款文档"
    print(f"[3] 正常召回：退款问题 top1=doc{top[1]} (score={top[0]:.2f}) -> OK")


def run_selftest():
    test_query_mismatch_blank()
    test_context_overflow_drops_key_chunk()
    test_retrieval_recall_sane()
    print("ALL_SELFTESTS_PASSED")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        run_selftest()
    else:
        print("usage: python3 02_rag_retrieve.py --self-test")
