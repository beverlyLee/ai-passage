"""之八 流式与透传：免 key 可复现演示。

运行：/tmp/lc132/bin/python streaming_and_passthrough.py --self-test

覆盖：
1. 模型层流式（BaseChatModel.stream 覆写 _stream）+ 末尾空 token（与系列前文联动）
2. RunnablePassthrough.invoke 原样返回 + stream 整体一个 chunk
3. RunnablePassthrough.assign 要求 dict 输入 + 透传补字段
4. 链中 passthrough 透传上游 chunk 给下游
5. 基类 Runnable.stream 默认等于 yield invoke（不真流式）
"""

import argparse

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_core.runnables import RunnableLambda, RunnablePassthrough


class FakeModel(BaseChatModel):
    """最小可流式 chat model：覆写 _stream 逐 token 产出。"""

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        for ch in ["你", "好"]:
            yield ChatGenerationChunk(message=AIMessageChunk(content=ch))

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(
            generations=[ChatGenerationChunk(message=AIMessageChunk(content="你好"))]
        )


def self_test() -> None:
    # 断言 1：模型层流式 + 末尾空 token 过滤
    fm = FakeModel()
    chunks = list(fm.stream("hi"))
    text = "".join(c.content for c in chunks if c.content != "")
    assert text == "你好", text
    assert len(chunks) >= 3, f"非空 token + 末尾空 token, got {len(chunks)}"

    # 断言 2：RunnablePassthrough 原样返回 + stream 整体一个 chunk
    rp = RunnablePassthrough()
    assert rp.invoke("hi") == "hi"
    assert list(rp.stream("hi")) == ["hi"]

    # 断言 3：assign 要求 dict 输入 + 透传补字段
    rpa = RunnablePassthrough.assign(extra=lambda x: x["orig"] + "!")
    assert rpa.invoke({"orig": "hi"}) == {"orig": "hi", "extra": "hi!"}
    assert list(rpa.stream({"orig": "hi"})) == [{"orig": "hi"}, {"extra": "hi!"}]
    # assign 字符串输入应报 ValueError（源码要求 dict）
    try:
        rpa.invoke("hi")
        raise AssertionError("assign 应拒绝非 dict 输入")
    except ValueError:
        pass

    # 断言 4：链中 passthrough 透传上游 chunk 给下游
    chain = fm | RunnablePassthrough() | RunnableLambda(lambda x: x.content)
    out = list(chain.stream("hi"))
    assert out == ["你好"], out

    # 断言 5：基类 Runnable.stream 默认 = yield invoke（不真流式）
    rl = RunnableLambda(lambda x: x + "!")
    assert list(rl.stream("hi")) == ["hi!"]

    print("ALL self-test PASS")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
    else:
        print("run with --self-test")
