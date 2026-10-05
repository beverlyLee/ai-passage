"""LangChain 之七：回调与可观测 可复现脚本（无需 API key）。

对应正文：回调是 LangChain 的可观测骨架。BaseCallbackHandler 定义了一组钩子，
框架在链、模型、工具、检索器运行的关键节点自动调用它们；BaseCallbackManager 负责
把事件分发给所有已注册的 handler；tracers 把同样的事件收敛成可回放的 Run 树。

本脚本全部用内存对象与确定性假组件，不调任何大模型、不发网络请求。

覆盖：
  - 同步 handler 捕获 chain / tool 事件（callbacks/base.py:493）
  - 异步 handler（AsyncCallbackHandler:545）捕获异步链事件
  - 流式 token 钩子 on_llm_new_token（callbacks/base.py:65）经假聊天模型的 _stream 触发
  - StdOutCallbackHandler（callbacks/stdout.py:16）是内置的现成 handler

运行：
    python callbacks_and_observability.py            # 跑演示
    python callbacks_and_observability.py --self-test  # 跑断言，全绿退出 0
"""

from langchain_core.callbacks.base import (
    AsyncCallbackHandler,
    BaseCallbackHandler,
    BaseCallbackManager,
    Callbacks,
)
from langchain_core.callbacks.stdout import StdOutCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import BaseTool


# --------------------------------------------------------------------------
# 1. 一个同步计数 handler：把关键事件按发生顺序记进列表
#    BaseCallbackHandler 是一组 Mixin 的合集（callbacks/base.py:493），
#    on_chain_start / on_chain_end / on_tool_start / on_tool_end /
#    on_llm_new_token 都是它提供的钩子接口。
# --------------------------------------------------------------------------
class TallyHandler(BaseCallbackHandler):
    def __init__(self) -> None:
        self.events: list[tuple] = []

    def on_chain_start(self, serialized, inputs, *, run_id=None, parent_run_id=None,
                       tags=None, metadata=None, **kwargs):
        name = None
        if isinstance(serialized, dict):
            name = serialized.get("name")
        self.events.append(("chain_start", name, str(run_id)))

    def on_chain_end(self, outputs, *, run_id=None, parent_run_id=None, **kwargs):
        self.events.append(("chain_end", None, str(run_id)))

    def on_tool_start(self, serialized, input_str, *, run_id=None, parent_run_id=None,
                      inputs=None, **kwargs):
        self.events.append(("tool_start", input_str, str(run_id)))

    def on_tool_end(self, output, *, run_id=None, parent_run_id=None, **kwargs):
        self.events.append(("tool_end", output, str(run_id)))

    def on_llm_new_token(self, token, *, chunk=None, run_id=None, parent_run_id=None,
                         **kwargs):
        self.events.append(("llm_token", token, str(run_id)))


# --------------------------------------------------------------------------
# 2. 一个确定性假聊天模型：实现 _generate（必填）与 _stream（流式）。
#    BaseChatModel（language_models/chat_models.py）的 stream() 会在每个 chunk
#    上自动调用 run_manager.on_llm_new_token（chat_models.py:790/810）。
#    _llm_type 是抽象方法，必须实现（chat_models.py:2205）。
# --------------------------------------------------------------------------
class EchoChatModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:  # noqa: D401
        return "echo"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        text = messages[-1].content
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        text = messages[-1].content
        for ch in text:
            yield ChatGenerationChunk(message=AIMessageChunk(content=ch))


# --------------------------------------------------------------------------
# 3. 一个最小工具，用来演示 tool 事件
# --------------------------------------------------------------------------
class EchoTool(BaseTool):
    name: str = "echo"
    description: str = "原样返回输入"

    def _run(self, text: str) -> str:
        return f"echo: {text}"

    async def _arun(self, text: str) -> str:
        return self._run(text)


# --------------------------------------------------------------------------
# 4. 异步 handler：演示 AsyncCallbackHandler 这一支（callbacks/base.py:545）
# --------------------------------------------------------------------------
class AsyncTallyHandler(AsyncCallbackHandler):
    def __init__(self) -> None:
        self.events: list[tuple] = []

    async def on_chain_start(self, serialized, inputs, *, run_id=None,
                             parent_run_id=None, tags=None, metadata=None, **kwargs):
        self.events.append(("chain_start", None, str(run_id)))

    async def on_chain_end(self, outputs, *, run_id=None, parent_run_id=None, **kwargs):
        self.events.append(("chain_end", None, str(run_id)))


def demo() -> None:
    handler = TallyHandler()
    chain = RunnableLambda(lambda x: f"得到 {x}")
    out = chain.invoke("你好", config={"callbacks": [handler]})
    print("链输出：", out)
    print("捕获到的事件：")
    for ev in handler.events:
        print("  ", ev)

    model = EchoChatModel()
    print("\n流式 token：")
    for chunk in model.stream("abc", config={"callbacks": [handler]}):
        print("  chunk:", chunk.content)


def self_test() -> None:
    # 断言1：同步 handler 在链运行前后捕获 chain_start 与 chain_end
    handler = TallyHandler()
    chain = RunnableLambda(lambda x: f"得到 {x}")
    assert chain.invoke("你好", config={"callbacks": [handler]}) == "得到 你好"
    kinds = [e[0] for e in handler.events]
    assert "chain_start" in kinds and "chain_end" in kinds
    assert kinds.index("chain_start") < kinds.index("chain_end")
    print("self-test PASS [1] 同步 handler 捕获 chain_start 与 chain_end（顺序正确）")

    # 断言2：工具调用同时触发 on_tool_start 与 on_tool_end
    handler2 = TallyHandler()
    tool = EchoTool()
    assert tool.invoke("hi", config={"callbacks": [handler2]}) == "echo: hi"
    kinds2 = [e[0] for e in handler2.events]
    assert "tool_start" in kinds2 and "tool_end" in kinds2
    # tool_start 记录的是传入的输入字符串
    tool_starts = [e for e in handler2.events if e[0] == "tool_start"]
    assert tool_starts[0][1] == "hi", tool_starts
    print("self-test PASS [2] 工具调用触发 on_tool_start / on_tool_end（输入正确）")

    # 断言3：流式 token 钩子 on_llm_new_token 逐字符触发，且能拼回原文
    handler3 = TallyHandler()
    model = EchoChatModel()
    pieces = [c.content for c in model.stream("abc", config={"callbacks": [handler3]})]
    assert "".join(pieces) == "abc", pieces
    # 框架在流末会补发一个空 token（chunk_position="last"，chat_models.py:810）
    # 用来给接收方打上“这是最后一片”的标记，过滤掉它再比对有效 token
    tokens = [e for e in handler3.events if e[0] == "llm_token" and e[1] != ""]
    assert [t[1] for t in tokens] == ["a", "b", "c"], tokens
    print("self-test PASS [3] on_llm_new_token 逐字符触发，流式拼回 abc")

    # 断言4：AsyncCallbackHandler 是 BaseCallbackHandler 的子类，且异步链能捕获事件
    assert issubclass(AsyncCallbackHandler, BaseCallbackHandler)
    handler4 = AsyncTallyHandler()
    achain = RunnableLambda(lambda x: f"async 得到 {x}")

    async def _arun():
        return await achain.ainvoke("hey", config={"callbacks": [handler4]})

    import asyncio
    assert asyncio.run(_arun()) == "async 得到 hey"
    kinds4 = [e[0] for e in handler4.events]
    assert "chain_start" in kinds4 and "chain_end" in kinds4
    print("self-test PASS [4] AsyncCallbackHandler 子类，异步链事件被捕获")

    # 断言5：StdOutCallbackHandler 是内置的现成 handler，同样是 BaseCallbackHandler 子类
    assert issubclass(StdOutCallbackHandler, BaseCallbackHandler)
    assert isinstance(BaseCallbackManager, type)
    # Callbacks 是类型别名：list[BaseCallbackHandler] | BaseCallbackManager | None
    assert Callbacks is not None
    print("self-test PASS [5] StdOutCallbackHandler 内置；BaseCallbackManager 与 Callbacks 类型存在")


if __name__ == "__main__":
    import sys

    if "--self-test" in sys.argv:
        self_test()
        print("ALL self-test PASS")
    else:
        demo()
