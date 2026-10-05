"""LangChain 之六：记忆与历史 可复现脚本（无需 API key）。

对应正文：对话历史与长期记忆在 LangChain 里怎么被建模成可增删改查的对象，
以及 RunnableWithMessageHistory 怎么在每次调用前后自动读写历史、把多轮对话串起来。

核心对象：
  - BaseChatMessageHistory（chat_history.py:22）：历史存储的抽象基类
  - InMemoryChatMessageHistory（chat_history.py:202）：内存版实现
  - RunnableWithMessageHistory（runnables/history.py:38）：把历史读写包进竖线
  - MessagesPlaceholder（prompts/chat.py:53）：在提示词里给历史留一个可变插槽

全部用内存存储与确定性假链，不调任何大模型、不发网络请求。

运行：
    python memory_and_history.py            # 跑演示
    python memory_and_history.py --self-test  # 跑断言，全绿退出 0
"""

import asyncio

from langchain_core.chat_history import (
    BaseChatMessageHistory,
    InMemoryChatMessageHistory,
)
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda, RunnableWithMessageHistory


# --------------------------------------------------------------------------
# 1. 假「模型」：收一个带 history 与 input 的字典，吐一个 output 字典
#    history_messages_key 设了之后，RunnableWithMessageHistory 会把历史消息
#    作为独立字段喂进来（runnables/history.py:326 的 messages_key 逻辑）。
# --------------------------------------------------------------------------
def fake_chat(inputs: dict) -> dict:
    human = inputs["input"]
    history = inputs["history"]  # 本轮之前累积的历史消息列表
    # 把当前看到的上下文窗口大小记录下来，供 self-test 校验
    fake_chat.seen_history_len = len(history)
    return {"output": f"回应[{len(history)}]:{human}"}


# --------------------------------------------------------------------------
# 2. session 工厂：不同 session_id 对应不同的历史存储
#    get_session_history 的签名由 RunnableWithMessageHistory 反射得到
#    （runnables/history.py:619 的 _get_parameter_names 用 inspect.signature）。
# --------------------------------------------------------------------------
STORE: dict[str, InMemoryChatMessageHistory] = {}


def get_session_history(session_id: str) -> InMemoryChatMessageHistory:
    if session_id not in STORE:
        STORE[session_id] = InMemoryChatMessageHistory()
    return STORE[session_id]


def build_chain() -> RunnableWithMessageHistory:
    return RunnableWithMessageHistory(
        RunnableLambda(fake_chat),
        get_session_history,
        input_messages_key="input",
        history_messages_key="history",
        output_messages_key="output",
    )


def demo() -> None:
    hist = InMemoryChatMessageHistory()
    hist.add_user_message("你好")  # 便捷方法，等价 add_message(HumanMessage(...))
    hist.add_ai_message("你好，我是助手")
    print("当前历史条数：", len(hist.messages))
    for m in hist.messages:
        print(f"  {type(m).__name__}: {m.content}")

    chain = build_chain()
    print("\n三轮对话（同一 session）：")
    for q in ["q1", "q2", "q3"]:
        out = chain.invoke(
            {"input": q}, config={"configurable": {"session_id": "demo"}}
        )
        print(f"  输入 {q} -> {out['output']}")
    print("最终历史条数：", len(STORE["demo"].messages))


def self_test() -> None:
    # 断言1：InMemoryChatMessageHistory 是 BaseChatMessageHistory，
    # add_message 追加、clear 清空（chat_history.py:202 / 224 / 240）。
    assert issubclass(InMemoryChatMessageHistory, BaseChatMessageHistory)
    hist = InMemoryChatMessageHistory()
    assert len(hist.messages) == 0
    hist.add_message(HumanMessage(content="a"))
    hist.add_message(AIMessage(content="b"))
    assert len(hist.messages) == 2
    assert isinstance(hist.messages[0], HumanMessage)
    hist.clear()
    assert len(hist.messages) == 0
    print("self-test PASS [1] InMemoryChatMessageHistory 继承基类，增改查清空正确")

    # 断言2：异步 aadd_messages 也能追加消息（chat_history.py:232）。
    hist2 = InMemoryChatMessageHistory()

    async def _arun() -> None:
        await hist2.aadd_messages([HumanMessage(content="x"), AIMessage(content="y")])

    asyncio.run(_arun())
    assert len(hist2.messages) == 2
    print("self-test PASS [2] aadd_messages 异步追加，历史条数正确")

    # 断言3：RunnableWithMessageHistory 跨多轮把历史累积进存储。
    # 每轮写入 1 条 Human + 1 条 AI，三轮后应为 6 条，且顺序正确；
    # 第 2、3 轮进入假模型时，看到的 history 长度应分别为 2、4（之前累积的）。
    STORE.clear()
    chain = build_chain()
    cfg = {"configurable": {"session_id": "s1"}}
    chain.invoke({"input": "t1"}, config=cfg)
    assert fake_chat.seen_history_len == 0, fake_chat.seen_history_len
    chain.invoke({"input": "t2"}, config=cfg)
    assert fake_chat.seen_history_len == 2, fake_chat.seen_history_len
    chain.invoke({"input": "t3"}, config=cfg)
    assert fake_chat.seen_history_len == 4, fake_chat.seen_history_len

    final = STORE["s1"].messages
    assert len(final) == 6, len(final)
    assert isinstance(final[0], HumanMessage) and final[0].content == "t1"
    assert isinstance(final[1], AIMessage) and final[1].content == "回应[0]:t1"
    assert isinstance(final[2], HumanMessage) and final[2].content == "t2"
    assert isinstance(final[3], AIMessage) and final[3].content == "回应[2]:t2"
    assert isinstance(final[4], HumanMessage) and final[4].content == "t3"
    assert isinstance(final[5], AIMessage) and final[5].content == "回应[4]:t3"
    print("self-test PASS [3] RunnableWithMessageHistory 三轮累积 6 条且顺序正确")

    # 断言4：MessagesPlaceholder 在提示词里插入可变长度的历史消息
    # （prompts/chat.py:53）。
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "你是客服助手"),
            MessagesPlaceholder("history"),
            ("human", "{input}"),
        ]
    )
    history_msgs = [
        HumanMessage(content="上一条问题"),
        AIMessage(content="上一条回答"),
        HumanMessage(content="又一条问题"),
    ]
    rendered = prompt.format_messages(history=history_msgs, input="现在的问题")
    # system(1) + history(3) + human(1) = 5 条
    assert len(rendered) == 5, len(rendered)
    assert rendered[1].content == "上一条问题"
    assert rendered[2].content == "上一条回答"
    assert rendered[3].content == "又一条问题"
    assert rendered[4].content == "现在的问题"
    print("self-test PASS [4] MessagesPlaceholder 把可变长度历史插进提示词")


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        self_test()
        print("ALL self-test PASS")
    else:
        demo()
