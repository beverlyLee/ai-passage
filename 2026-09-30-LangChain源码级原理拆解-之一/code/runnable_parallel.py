#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
迷你 LCEL 核心（二）：RunnableParallel 扇入扇出 + RunnablePassthrough 透传 + 流式退化坑

一手源码参照（langchain-core 1.6.6, commit a9780cd3dd73135d21d7130b08711685f2700d51）：
  - class RunnableParallel(RunnableSerializable[Input, dict])   base.py:3864
  - RunnableParallel.invoke 线程池并发 + dict 汇总             base.py:4139, 4181
  - class RunnablePassthrough(RunnableSerializable)            passthrough.py:74
  - RunnablePassthrough.invoke 核心是 identity                  passthrough.py:226, 233
  - RunnableLambda 默认只有 invoke，无 transform/astream        base.py:4703 一带

运行：python3 runnable_parallel.py --self-test
"""

import sys
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor


class Runnable(ABC):
    @abstractmethod
    def invoke(self, input, config=None, **kwargs):
        raise NotImplementedError

    def transform(self, input, config=None, **kwargs):
        # 默认 transform 退化为一次性 invoke
        yield self.invoke(input, config, **kwargs)


def coerce_to_runnable(thing):
    if isinstance(thing, Runnable):
        return thing
    if callable(thing):
        return RunnableLambda(thing)
    if isinstance(thing, dict):
        return RunnableParallel(thing)
    raise TypeError(f"不支持的类型: {type(thing)}")


class RunnableLambda(Runnable):
    def __init__(self, func):
        self.func = func

    def invoke(self, input, config=None, **kwargs):
        return self.func(input)


class RunnableParallel(Runnable):
    def __init__(self, steps):
        self.steps = dict(steps)

    def invoke(self, input, config=None, **kwargs):
        # base.py:4181 同一 input 并发提交给每个分支，最后按 key 汇总
        out = {}
        with ThreadPoolExecutor(max_workers=len(self.steps)) as ex:
            futures = {
                k: ex.submit(self.steps[k].invoke, input, config)
                for k in self.steps
            }
            for k, f in futures.items():
                out[k] = f.result()
        return out


class RunnablePassthrough(Runnable):
    """passthrough.py:74 近乎恒等函数。这里演示它原样透传。"""
    def invoke(self, input, config=None, **kwargs):
        return input                     # passthrough.py:233 identity


# ---------- 自检 ----------

def _slow_branch(name, seconds):
    def _run(x):
        time.sleep(seconds)
        return f"{name}:{x}"
    return RunnableLambda(_run)


def _self_test():
    print("== runnable_parallel self-test ==")

    # 1) RunnableParallel 同输入扇出，并发执行（总耗时≈最慢分支，而非累加）
    para = RunnableParallel({"fast": _slow_branch("A", 0.2), "slow": _slow_branch("B", 0.2)})
    t0 = time.time()
    out = para.invoke("x")
    cost = time.time() - t0
    assert set(out) == {"fast", "slow"}, out
    assert 0.15 < cost < 0.35, f"应近似并发而非串行, cost={cost}"
    print("1) 并发扇出耗时(秒):", round(cost, 3), "结果:", out)

    # 2) RunnablePassthrough 透传恒等
    pt = RunnablePassthrough()
    assert pt.invoke({"q": "地球为什么是圆的"}) == {"q": "地球为什么是圆的"}
    print("2) RunnablePassthrough 透传:", pt.invoke("任意值"))

    # 3) 流式退化坑：只有 invoke 的 RunnableLambda 经 transform 一次性吐出，无分块
    lam = RunnableLambda(lambda s: s * 3)
    chunks = list(lam.transform("hi"))
    assert len(chunks) == 1 and chunks[0] == "hihihi", chunks
    print("3) 裸 lambda 的 transform 退化为单块:", chunks)

    # 4) 字典语法 {key: runnable} 被 coerce 成 RunnableParallel
    built = coerce_to_runnable({"a": _slow_branch("A", 0.05), "b": RunnablePassthrough()})
    assert isinstance(built, RunnableParallel), type(built)
    bout = built.invoke("z")
    assert bout == {"a": "A:z", "b": "z"}, bout
    print("4) 字典 coerce 成并行后结果:", bout)

    print("self-test PASS")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        _self_test()
    else:
        para = RunnableParallel({"a": RunnableLambda(lambda s: s.upper()), "b": RunnablePassthrough()})
        print("演示:", para.invoke("hello"))
