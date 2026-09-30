#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迷你 LCEL 核心（三）：RunnableBranch 条件路由 + 顺序即优先级

一手源码参照（langchain-core 1.6.6, commit a9780cd3dd73135d21d7130b08711685f2700d51）：
  - class RunnableBranch(RunnableSerializable)            branch.py:43
  - RunnableBranch.__init__ 取 *branches，default=最后一项   branch.py:70, 101
  - RunnableBranch.invoke 首个为真条件命中，否则走 default    branch.py:185, 208, 229

运行：python3 runnable_branch.py --self-test
"""

import sys
from abc import ABC, abstractmethod


class Runnable(ABC):
    @abstractmethod
    def invoke(self, input, config=None, **kwargs):
        raise NotImplementedError


def coerce_to_runnable(thing):
    if isinstance(thing, Runnable):
        return thing
    if callable(thing):
        return RunnableLambda(thing)
    raise TypeError(f"不支持的类型: {type(thing)}")


class RunnableLambda(Runnable):
    def __init__(self, func):
        self.func = func

    def invoke(self, input, config=None, **kwargs):
        return self.func(input)


class RunnableBranch(Runnable):
    def __init__(self, *branches):
        # branch.py:70 取 *branches 元组；branch.py:101 default = 最后一项
        self.branches = list(branches[:-1])
        self.default = coerce_to_runnable(branches[-1])

    def invoke(self, input, config=None, **kwargs):
        # branch.py:208 for 循环按序扫分支；branch.py:219 首个为真即命中并 break
        for condition, runnable in self.branches:
            if condition.invoke(input, config):
                return runnable.invoke(input, config, **kwargs)
        # branch.py:229 全不命中走 default
        return self.default.invoke(input, config, **kwargs)


# ---------- 业务样例：根据问题类型路由不同处理 ----------

def is_code(x):
    return x.startswith("CODE:")

def is_math(x):
    return x.startswith("MATH:")

route = RunnableBranch(
    (RunnableLambda(is_code), RunnableLambda(lambda x: f"[代码模式] {x[5:]}")),
    (RunnableLambda(is_math), RunnableLambda(lambda x: f"[数学模式] {x[5:]}")),
    RunnableLambda(lambda x: f"[通用模式] {x}"),   # 兜底 default
)


# ---------- 自检 ----------

def _self_test():
    print("== runnable_branch self-test ==")

    # 1) 命中第一个为真条件（代码模式）
    assert route.invoke("CODE:print(1)") == "[代码模式] print(1)"
    print("1) 代码模式路由:", route.invoke("CODE:print(1)"))

    # 2) 命中第二个条件（数学模式）
    assert route.invoke("MATH:1+1") == "[数学模式] 1+1"
    print("2) 数学模式路由:", route.invoke("MATH:1+1"))

    # 3) 全不命中走 default
    assert route.invoke("hello world") == "[通用模式] hello world"
    print("3) 兜底路由:", route.invoke("hello world"))

    # 4) 顺序即优先级：把兜底条件(is_anything)放第一，会挡住后面所有分支
    broad = RunnableBranch(
        (RunnableLambda(lambda x: True), RunnableLambda(lambda x: "被宽条件吃掉")),
        (RunnableLambda(is_code), RunnableLambda(lambda x: "永远到不了")),
        RunnableLambda(lambda x: "也到不了"),
    )
    assert broad.invoke("CODE:x") == "被宽条件吃掉", broad.invoke("CODE:x")
    print("4) 宽条件前置挡住窄条件:", broad.invoke("CODE:x"))

    print("self-test PASS")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        _self_test()
    else:
        print("演示:", route.invoke("MATH:2*3"))
