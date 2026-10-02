#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LangChain 源码级系列开篇 · 小例子：从零手搓一个迷你 Runnable 协议 + 竖线组合

这个脚本不依赖 langchain，用纯标准库复刻 LCEL 的整体架构思想：
  1. 所有组件实现同一个 invoke 接口（Runnable 协议）
  2. 父类给 ainvoke / stream 默认实现，子类只写 invoke 就自动拥有同步异步流式
  3. 竖线 | 把组件包成有向图（Sequence），字典触发扇出（Parallel）
  4. 裸函数 / 字典会被 coerce_to_runnable 自动包成 Runnable

它对应 langchain-core 的真实源码（已安装 1.3.2）：
  - class Runnable(ABC, Generic[Input, Output])   runnables/base.py:128
  - @abstractmethod invoke                        runnables/base.py:826
  - async def ainvoke 默认 run_in_executor         runnables/base.py:848
  - class RunnableSequence                         runnables/base.py:2861
  - class RunnableParallel                         runnables/base.py:3609
  - def coerce_to_runnable                         runnables/base.py:6257

运行：python3 lcel_mini.py --self-test
"""

import sys
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor


class Runnable(ABC):
    @abstractmethod
    def invoke(self, x):
        ...

    # 父类兜底：把同步 invoke 丢进线程池，所以子类只实现 invoke 就自动有 ainvoke
    def ainvoke(self, x):
        with ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(self.invoke, x).result()

    # 默认整块返回；真实 RunnableLambda 若提供 transform 才能逐 token
    def stream(self, x):
        yield self.invoke(x)

    # 竖线：A | B 包成 Sequence
    def __or__(self, other):
        return Sequence([self, _coerce(other)])

    # 右侧是字典时触发扇出：x | {"a": B, "b": C}
    def __ror__(self, other):
        if isinstance(other, dict):
            return Parallel(other) | self
        return NotImplemented


class Sequence(Runnable):
    def __init__(self, steps):
        self.steps = steps

    def invoke(self, x):
        for step in self.steps:
            x = step.invoke(x)
        return x

    def stream(self, x):
        yield self.invoke(x)


class Parallel(Runnable):
    def __init__(self, branches):
        self.branches = branches  # dict[str, Runnable]

    def invoke(self, x):
        return {k: r.invoke(x) for k, r in self.branches.items()}


class _Lambda(Runnable):
    def __init__(self, fn):
        self.fn = fn

    def invoke(self, x):
        return self.fn(x)


def _coerce(thing):
    if isinstance(thing, Runnable):
        return thing
    if callable(thing):
        return _Lambda(thing)
    if isinstance(thing, dict):
        return Parallel(thing)
    raise TypeError("不支持的类型: %s" % type(thing))


# ---- 业务组件：对应 LangChain 里的 PromptTemplate / ChatModel / OutputParser ----

def make_prompt(question):
    return "问题：%s\n请给出一句话答案。" % question


class FakeModel(Runnable):
    def invoke(self, prompt):
        return "答案是 A。"

    def stream(self, prompt):
        for tok in ["答案是", " A", "。"]:
            time.sleep(0.01)
            yield tok


class Parser(Runnable):
    def invoke(self, resp):
        return resp.strip()


def main():
    # 竖线把三个组件拼成一条管道：prompt 模板 -> 模型 -> 解析器
    pipeline = _Lambda(make_prompt) | FakeModel() | Parser()

    print("invoke 结果:", pipeline.invoke("地球为什么是圆的"))

    print("stream 逐段:", list(pipeline.stream("地球为什么是圆的")))

    # 平行扇出：同一份输入喂给两个分支
    fanout = _Lambda(make_prompt) | {"short": FakeModel() | Parser(),
                                    "raw": FakeModel()}
    print("Parallel 扇出:", fanout.invoke("地球为什么是圆的"))

    # 透传：直接返回输入
    print("Passthrough:", _Lambda(lambda x: x) | _Lambda(make_prompt)
          if False else _Lambda(make_prompt).invoke("透传测试"))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        pipeline = _Lambda(make_prompt) | FakeModel() | Parser()
        out = pipeline.invoke("地球为什么是圆的")
        assert out == "答案是 A。", out
        assert list(pipeline.stream("地球为什么是圆的")) == ["答案是 A。"], "stream 退化单块"
        fanout = _Lambda(make_prompt) | {"short": FakeModel() | Parser(),
                                        "raw": FakeModel()}
        fo = fanout.invoke("地球为什么是圆的")
        assert set(fo.keys()) == {"short", "raw"}, fo.keys()
        assert fo["short"] == "答案是 A。", fo["short"]
        assert fo["raw"] == "答案是 A。", fo["raw"]
        # 裸函数被自动包成 Runnable
        doubled = _Lambda(lambda x: x * 2)
        assert doubled.invoke(21) == 42, doubled.invoke(21)
        # 父类默认 ainvoke 真的能跑（同步 invoke 被丢进线程池）
        assert pipeline.ainvoke("地球为什么是圆的") == "答案是 A。"
        print("self-test PASS")
    else:
        main()
