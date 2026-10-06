"""之九 实战：一个能检索又会调工具的流式问答助手（免 key 可复现）。

运行：/tmp/lc132/bin/python langchain_rag_agent_demo.py --self-test

覆盖（串联 之一 到 之八）：
1. 组合原语（之一 / 之二）：RunnableParallel / RunnablePassthrough.assign / RunnableLambda 串管道
2. 模型与消息（之三）：BaseChatModel 子类 + AIMessageChunk + ToolMessage
3. 检索与文档（之四）：Document + 离线检索器
4. 智能体与工具（之五）：工具调用消息流 + 确定性路由（离线模拟）
5. 记忆与历史（之六）：RunnableWithMessageHistory + InMemoryChatMessageHistory
6. 回调与可观测（之七）：自定义 CallbackHandler 数 token
7. 流式与透传（之八）：stream 逐 chunk + 过滤末尾空 token

所有组件都跑在标准库 + langchain-core 1.3.2 上，不需要任何 API key。
生产环境把 FakeModel / FakeRetriever 换成真实的 chat_models 与 vectorstore 即可，
组合方式完全一致（文中有对照）。
"""

import argparse

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.documents import Document
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    ToolMessage,
)
from langchain_core.output_parsers import StrOutputParser
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import (
    RunnableLambda,
    RunnableParallel,
    RunnablePassthrough,
    RunnableWithMessageHistory,
)


# ---------- 检索（之四） ----------
class FakeRetriever:
    """离线检索器：用关键字命中几条写死的 Document，模拟向量检索。"""

    def __init__(self):
        self._docs = {
            "退货": [
                Document(page_content="七天无理由退货：商品未拆封可发起。", metadata={"src": "faq-1"}),
                Document(page_content="退货时效：签收后 7 日内。", metadata={"src": "faq-2"}),
            ],
            "发票": [
                Document(page_content="电子发票在订单详情自助下载。", metadata={"src": "faq-3"}),
            ],
        }

    def invoke(self, query):
        for key, docs in self._docs.items():
            if key in query:
                return docs
        return [Document(page_content="没有命中知识库，转人工。", metadata={"src": "fallback"})]


def format_docs(docs):
    return "\n".join(d.page_content for d in docs)


# ---------- 模型（之三 + 之八 流式） ----------
class FakeModel(BaseChatModel):
    """最小可流式 chat model：覆写 _stream 逐 token 产出（含一个末尾空 token）。"""

    @property
    def _llm_type(self):
        return "fake"

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        for ch in ["请", "问", "的", "是", "：", "已", "记录"]:
            yield ChatGenerationChunk(message=AIMessageChunk(content=ch))
        # 末尾补一个空 token（与系列前文回调 / 解析层联动，会被过滤）
        yield ChatGenerationChunk(message=AIMessageChunk(content=""))

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        chunks = list(self._stream(messages, stop, run_manager))
        text = "".join(c.message.content for c in chunks if c.message.content)
        return ChatResult(
            generations=[ChatGenerationChunk(message=AIMessageChunk(content=text))]
        )


# ---------- 可观测（之七） ----------
class TokenTracer(BaseCallbackHandler):
    """自定义回调：数流式 token，顺手把末尾空 token 过滤掉。"""

    def __init__(self):
        self.tokens = 0

    def on_llm_new_token(self, token, **kwargs):
        if token:
            self.tokens += 1


# ---------- 工具（之五，离线模拟） ----------
class FakeToolModel(BaseChatModel):
    """会下达工具调用的假模型：第一次返回 tool_call，工具结果回来后自然语言收尾。"""

    @property
    def _llm_type(self):
        return "fake-tool"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        # 上一条若是工具结果，说明已经查过，直接自然语言收尾
        if any(isinstance(m, ToolMessage) for m in messages):
            return ChatResult(
                generations=[ChatGenerationChunk(message=AIMessageChunk(content="已为你查到物流。"))]
            )
        return ChatResult(
            generations=[
                ChatGenerationChunk(
                    message=AIMessageChunk(
                        content="",
                        tool_call_chunks=[
                            {
                                "name": "query_logistics",
                                "args": '{"order_id": "123"}',
                                "id": "call_1",
                            }
                        ],
                    )
                )
            ]
        )

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        for g in self._generate(messages, stop, run_manager).generations:
            yield g


def run_tool_call(name, args_json):
    """确定性工具路由：按名字执行工具，返回 ToolMessage。"""
    if name == "query_logistics":
        return ToolMessage(content="物流状态：运输中。", tool_call_id="call_1")
    raise ValueError(f"未知工具: {name}")


# ---------- 组装主链（之一 / 之二 / 之四 / 之六 / 之八） ----------
def build_chain(get_session_history):
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "你是客服助手。知识库：\n{context}"),
            ("placeholder", "{history}"),
            ("human", "{question}"),
        ]
    )
    retriever = FakeRetriever()
    base = (
        RunnablePassthrough.assign(
            context=lambda d: format_docs(retriever.invoke(d["question"]))
        )
        | prompt
        | FakeModel()
        | StrOutputParser()
    )
    return RunnableWithMessageHistory(
        base,
        get_session_history,
        input_messages_key="question",
        history_messages_key="history",
    )


def self_test() -> None:
    # 1. 检索（之四）
    retriever = FakeRetriever()
    docs = retriever.invoke("我要退货")
    assert len(docs) >= 1, "检索应返回文档"
    assert "退货" in docs[0].page_content

    # 2. 并行扇出（之一 / 之二）
    parallel = RunnableParallel(
        question=RunnablePassthrough(),
        context=RunnableLambda(lambda q: format_docs(retriever.invoke(q))),
    )
    out = parallel.invoke("我要退货")
    assert out["question"] == "我要退货"
    assert "退货" in out["context"]

    # 3. 记忆（之六）
    store: dict = {}

    def get_session_history(session_id):
        if session_id not in store:
            store[session_id] = InMemoryChatMessageHistory()
        return store[session_id]

    chain = build_chain(get_session_history)
    cfg = lambda sid: {"configurable": {"session_id": sid}}
    chain.invoke({"question": "我要退货"}, config=cfg("s1"))
    chain.invoke({"question": "那发票呢"}, config=cfg("s1"))
    hist = get_session_history("s1").messages
    assert sum(isinstance(m, HumanMessage) for m in hist) == 2, "应有 2 条 human"
    assert sum(isinstance(m, AIMessage) for m in hist) == 2, "应有 2 条 ai"

    # 4. 流式 + 回调（之八 + 之七）
    tracer = TokenTracer()
    chunks = []
    for c in chain.stream(
        {"question": "我要退货"},
        config={"configurable": {"session_id": "s2"}, "callbacks": [tracer]},
    ):
        if c:  # 过滤末尾空 token
            chunks.append(c)
    assert len(chunks) > 1, "流式应吐出多个 chunk"
    assert tracer.tokens >= 1, "回调应数到 token"

    # 5. 工具调用（之五）
    tool_model = FakeToolModel()
    msgs = [HumanMessage(content="查物流 123")]
    first = tool_model.invoke(msgs)
    assert first.tool_calls, "模型应下达 tool_call"
    tc = first.tool_calls[0]
    tool_msg = run_tool_call(tc["name"], tc["args"])
    assert isinstance(tool_msg, ToolMessage)
    assert "运输中" in tool_msg.content
    # 把工具结果喂回，模型收尾
    second = tool_model.invoke(msgs + [tool_msg])
    assert "物流" in second.content

    print("ALL self-test PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        print("传入 --self-test 运行免 key 复现")
