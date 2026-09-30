#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迷你 LCEL 核心（一）：Runnable 协议 + 竖线运算符 + coerce_to_runnable + RunnableSequence

本脚本用纯标准库复刻 langchain-core 1.6.6 的 LCEL 第一块基石，不带任何第三方依赖，
目的是把源码级原理变成可运行、可断点的代码。

一手源码参照（langchain-ai/langchain, libs/core, commit a9780cd3dd73135d21d7130b08711685f2700d51）：
  - class Runnable(ABC, Generic[Input, Output])            base.py:133
  - def __or__(self, other) -> RunnableSequence(...)        base.py:648, 返回在 base.py:673
  - def coerce_to_runnable(thing)                           base.py:6623
        callable -> RunnableLambda                          base.py:6656
        dict     -> RunnableParallel                         base.py:6658
        Runnable  -> 原样返回                                base.py:6652
  - class RunnableSequence(RunnableSerializable)            base.py:3075
  - RunnableSequence.__init__ 扁平化嵌套序列                base.py:3169, 3193
  - RunnableSequence.invoke for 循环链式调用                base.py:3430, 3453

运行：python3 runnable_sequence.py --self-test
"""

import sys
import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor


# base.py:133  class Runnable(ABC, Generic[Input, Output])
class Runnable(ABC):
    """最小 Runnable 协议：只要求子类实现 invoke。"""

    # base.py:885  @abstractmethod def invoke(...)
    @abstractmethod
    def invoke(self, input, config=None, **kwargs):
        raise NotImplementedError

    # base.py:908  async def ainvoke 默认用 run_in_executor 兜底同步 invoke。
    # 这里用线程池模拟「父类白送异步能力」：子类只写 invoke，就自动拥有 ainvoke。
    def ainvoke(self, input, config=None, **kwargs):
        with ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(self.invoke, input, config, **kwargs).result()


# base.py:6623  def coerce_to_runnable(thing)
def coerce_to_runnable(thing):
    """把 RunnableLike 强制变成 Runnable。竖线能接函数/字典/生成器的根本原因。"""
    if isinstance(thing, Runnable):
        return thing                                   # base.py:6652 原样返回
    if callable(thing):
        return RunnableLambda(thing)                    # base.py:6656 callable -> Lambda
    if isinstance(thing, dict):
        return RunnableParallel(thing)                  # base.py:6658 dict -> Parallel
    raise TypeError(f"不支持的类型: {type(thing)}")     # base.py:6664


# base.py:4703  class RunnableLambda(Runnable[Input, Output])
class RunnableLambda(Runnable):
    """把普通函数包成 Runnable。"""

    def __init__(self, func):
        self.func = func

    def invoke(self, input, config=None, **kwargs):
        return self.func(input)


# base.py:3864  class RunnableParallel(RunnableSerializable[Input, dict])
class RunnableParallel(Runnable):
    """字典 -> 同一份输入扇出到多个分支，按 key 汇总成 dict。"""

    def __init__(self, steps):
        self.steps = dict(steps)

    def invoke(self, input, config=None, **kwargs):
        out = {}
        # base.py:4181 用线程池并发提交每个分支，同一 input 喂给全部
        with ThreadPoolExecutor(max_workers=len(self.steps)) as ex:
            futures = {
                k: ex.submit(self.steps[k].invoke, input, config)
                for k in self.steps
            }
            for k, f in futures.items():
                out[k] = f.result()
        return out


# base.py:3075  class RunnableSequence(RunnableSerializable[Input, Output])
class RunnableSequence(Runnable):
    def __init__(self, *steps):
        flat = []
        for step in steps:
            # base.py:3193 遇到嵌套 RunnableSequence 就拆平
            if isinstance(step, RunnableSequence):
                flat.extend(step.steps)
            else:
                flat.append(coerce_to_runnable(step))   # base.py:3196
        if len(flat) < 2:
            raise ValueError("RunnableSequence 至少需要 2 个 step")
        self.steps = flat

    def invoke(self, input, config=None, **kwargs):
        # base.py:3430 核心就是这段 for 循环：上一步输出作下一步输入
        value = input
        for i, step in enumerate(self.steps):
            if i == 0:
                value = step.invoke(value, config, **kwargs)
            else:
                value = step.invoke(value, config)
        return value

    # base.py:648  def __or__(self, other) -> RunnableSequence(self, coerce_to_runnable(other))
    def __or__(self, other):
        return RunnableSequence(self, coerce_to_runnable(other))   # base.py:673


# base.py:133 的 Runnable 也要有 __or__，否则裸 Runnable 不能竖线
def _runnable_or(self, other):
    return RunnableSequence(self, coerce_to_runnable(other))       # base.py:673
Runnable.__or__ = _runnable_or


# ---------- 业务样例：prompt | model | parser 风格 ----------

class Prompt(Runnable):
    """模拟提示模板：把问题格式化进一段文本。"""
    def invoke(self, input, config=None, **kwargs):
        return f"问题：{input} 请给出一句话答案。"


class Model(Runnable):
    """模拟模型：输入提示，返回原始文本。"""
    def invoke(self, input, config=None, **kwargs):
        return f"[模型原始输出]{input}答案在此。"


def _to_clean(text):
    """裸函数：把模型输出抽成纯答案。会被 coerce_to_runnable 包成 RunnableLambda。"""
    return text.replace("[模型原始输出]", "").replace("答案在此。", "答案是 A。")


# ---------- 自检 ----------

def _self_test():
    print("== runnable_sequence self-test ==")

    # 1) 竖线把三段编译成 RunnableSequence，invoke 时链式喂值
    chain = Prompt() | Model() | _to_clean          # 注意 _to_clean 是裸函数
    assert isinstance(chain, RunnableSequence), "竖线应产出 RunnableSequence"
    out = chain.invoke("地球为什么是圆的")
    assert out == "问题：地球为什么是圆的 请给出一句话答案。答案是 A。", out
    print("1) prompt | model | 裸函数 链式产出:", out)

    # 2) 裸函数被 coerce_to_runnable 包成 RunnableLambda，链条仍能 invoke
    assert isinstance(chain.steps[2], RunnableLambda), "裸函数应被包成 RunnableLambda"
    print("2) 第三步类型:", type(chain.steps[2]).__name__)

    # 3) RunnableParallel 同输入扇出，按 key 汇总
    para = RunnableParallel({"a": Prompt(), "b": Model()})
    pout = para.invoke("你好")
    assert isinstance(pout, dict) and set(pout) == {"a", "b"}, pout
    print("3) 并行扇出字典 keys:", sorted(pout))

    # 4) 嵌套序列构造时被扁平化，((x|y)|z) 与 x|y|z 同图
    nested = RunnableSequence(RunnableSequence(Prompt(), Model()), _to_clean)
    assert len(nested.steps) == 3, len(nested.steps)
    print("4) 嵌套序列展平后 step 数:", len(nested.steps))

    # 5) 少于 2 个 step 抛 ValueError
    try:
        RunnableSequence(Prompt())
        raise AssertionError("应抛 ValueError")
    except ValueError:
        print("5) 单 step 抛 ValueError: OK")

    print("self-test PASS")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        _self_test()
    else:
        # 直接运行演示
        chain = Prompt() | Model() | _to_clean
        print("演示:", chain.invoke("地球为什么是圆的"))
