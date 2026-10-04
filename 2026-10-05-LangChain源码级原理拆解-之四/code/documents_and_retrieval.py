"""LangChain 之四：检索与文档 — 可复现脚本（无需 API key）。

对应正文：把一块文本变成可检索的知识。
链路：Document -> RecursiveCharacterTextSplitter -> Embeddings -> VectorStore -> Retriever

所有向量用一个确定性的「假 Embeddings」生成（基于词哈希 + 随机投影），
不调用任何网络、不需要任何模型权重，目的只是让链路能端到端跑通并断言行为。

运行：
    python documents_and_retrieval.py            # 跑演示
    python documents_and_retrieval.py --self-test  # 跑断言，全绿退出 0
"""

import math
import re
from typing import List

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_core.retrievers import BaseRetriever
from langchain_text_splitters import RecursiveCharacterTextSplitter


# --------------------------------------------------------------------------
# 1. 假 Embeddings：确定性、纯标准库实现
#    真实场景这里会换成 OpenAIEmbeddings / HuggingFaceEmbeddings 等，
#    但 VectorStore 只认 Embeddings 抽象，不关心背后怎么算。
# --------------------------------------------------------------------------
class HashEmbeddings(Embeddings):
    """把文本投影到 dim 维向量：字粒度词频哈希 + 余弦归一化。

    关键：纯函数。同一段文本无论第几次调用、调用顺序如何，都得到同一向量
    （由文本自身哈希做随机种子，不依赖外部可变状态），便于断言复现。
    """

    def __init__(self, dim: int = 32) -> None:
        self.dim = dim

    def _tokenize(self, text: str) -> List[str]:
        # ASCII 词作为一个 token；CJK 逐字作为一个 token，保证中文也能对齐
        text = text.lower()
        toks: List[str] = []
        for m in re.finditer(r"[a-z0-9]+|[一-鿿]", text):
            toks.append(m.group(0))
        return toks

    def _proj(self, text: str) -> List[float]:
        # 由文本哈希派生固定种子，保证确定性
        seed = 0
        for ch in text:
            seed = (seed * 31 + ord(ch)) & 0x7FFFFFFF
        state = seed or 1

        def nxt() -> float:
            nonlocal state
            state = (1103515245 * state + 12345) & 0x7FFFFFFF
            return state / 0x7FFFFFFF

        vec = [0.0] * self.dim
        for w in self._tokenize(text):
            h = 0
            for ch in w:
                h = (h * 31 + ord(ch)) & 0xFFFFFFFF
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._proj(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._proj(text)


# --------------------------------------------------------------------------
# 2. 一个小知识库：一段运维手册
# --------------------------------------------------------------------------
KB = """
数据库主节点在凌晨两点发生OOM，连接池被打满，下游订单服务开始超时。
缓存层命中率从98%跌到40%，大量请求穿透到数据库，形成雪崩。
网关层返回502，健康检查连续失败三次后触发自动摘除。
消息队列积压超过五十万条，消费者线程全部阻塞在数据库写入。
日志显示慢查询集中在用户表，缺少复合索引导致全表扫描。
运维手册要求：先扩容连接池，再回滚最近的发布，最后补充缺失索引。
支付链路与订单链路共享同一个数据库实例，需要优先隔离。
告警分诊台把P0工单直接推送给值班工程师，P2工单进入工单池排队。
"""


def build_store() -> InMemoryVectorStore:
    """切块 -> 建库 的完整链路。"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=60,
        chunk_overlap=10,
        separators=["\n", "。", "，", " "],
    )
    docs = splitter.create_documents([KB])
    store = InMemoryVectorStore(HashEmbeddings())
    store.add_documents(docs)
    return store


# --------------------------------------------------------------------------
# 3. 自定义 Retriever：继承 BaseRetriever，复写 _get_relevant_documents
#    BaseRetriever 本身是 RunnableSerializable，所以能直接 .invoke()
# --------------------------------------------------------------------------
class TopKRetriever(BaseRetriever):
    store: InMemoryVectorStore
    k: int = 3

    def _get_relevant_documents(self, query: str, *, run_manager=None) -> List[Document]:
        return self.store.similarity_search(query, k=self.k)


def demo() -> None:
    store = build_store()
    docs = store.similarity_search("数据库OOM怎么处理", k=3)
    print(f"知识库切块数: {len(store.store)}")
    print("检索「数据库OOM怎么处理」top3:\n")
    for i, d in enumerate(docs, 1):
        print(f"[{i}] {d.page_content.strip()[:40]}...  meta={d.metadata}")

    retr = store.as_retriever(search_kwargs={"k": 2})
    print("\n通过 as_retriever 走 Runnable 接口:")
    for d in retr.invoke("消息队列积压怎么办"):
        print(" -", d.page_content.strip()[:40])

    custom = TopKRetriever(store=store, k=2)
    print("\n自定义 Retriever .invoke():")
    for d in custom.invoke("告警怎么分诊"):
        print(" -", d.page_content.strip()[:40])


def self_test() -> None:
    store = build_store()

    # 断言1：切块数量合理（原始文本按句切，应多于 3 块）
    n = len(store.store)
    assert n >= 3, f"切块数过少: {n}"
    print(f"self-test PASS [1] 切块数={n}")

    # 断言2：Document 字段契约——page_content 与 metadata 都在
    raw = store.store
    first = next(iter(raw.values()))
    assert "text" in first and "metadata" in first and "vector" in first
    print("self-test PASS [2] InMemoryVectorStore 内部记录含 text/metadata/vector")

    # 断言3：相似度检索返回 k 条且按相关度排序（top1 命中「数据库OOM」相关句）
    top = store.similarity_search("数据库OOM连接池打满", k=2)
    assert len(top) == 2
    assert "OOM" in top[0].page_content or "连接池" in top[0].page_content
    print("self-test PASS [3] top1 命中 OOM/连接池 相关句")

    # 断言4：as_retriever 产出的 VectorStoreRetriever 也是 Runnable，
    #        用统一 invoke 入口拿到文档
    retr = store.as_retriever(search_kwargs={"k": 1})
    out = retr.invoke("慢查询缺索引")
    assert len(out) == 1 and "索引" in out[0].page_content
    print("self-test PASS [4] as_retriever().invoke() 返回相关文档")

    # 断言5：自定义 BaseRetriever 子类 .invoke() 走 _get_relevant_documents
    custom = TopKRetriever(store=store, k=2)
    out2 = custom.invoke("消息队列积压")
    assert len(out2) == 2 and any("消息队列" in d.page_content for d in out2)
    print("self-test PASS [5] 自定义 Retriever 子类 invoke 生效")

    # 断言6：Embeddings 抽象行为——同文本同向量，不同文本距离可变
    emb = HashEmbeddings()
    v1 = emb.embed_query("数据库 OOM")
    v2 = emb.embed_query("数据库 OOM")
    v3 = emb.embed_query("今天天气晴")
    assert v1 == v2, "同文本应得同向量"
    assert v1 != v3, "不同文本通常不同向量"
    print("self-test PASS [6] Embeddings 确定性（同文同向量）")


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        self_test()
        print("ALL self-test PASS")
    else:
        demo()
