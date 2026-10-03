# -*- coding: utf-8 -*-
"""
composite_primitives.py

LangChain 之二「组合原语深拆」的配套可运行复现脚本。

目的：用纯标准库（不依赖 langchain，免 API key）复刻 langchain-core 1.3.2 中
几个组合原语的核心行为，让读者在本机零成本跑通，并核对正文「复现模块」里的
精确预期输出。

对应一手源码（langchain-core == 1.3.2，本地安装路径见正文复现模块）：
  - runnables/base.py:2861  class RunnableSequence
  - runnables/base.py:3609  class RunnableParallel
  - runnables/base.py:6257  def coerce_to_runnable（dict -> RunnableParallel）
  - runnables/passthrough.py:74   class RunnablePassthrough
  - runnables/passthrough.py:207  RunnablePassthrough.assign
  - runnables/branch.py:42       class RunnableBranch
  - runnables/fallbacks.py:36    class RunnableWithFallbacks

运行：
  python composite_primitives.py --self-test

本脚本只复刻「逻辑形状」，不做异步、不接 callback、不接真实模型；并发分支用
ThreadPoolExecutor 模拟 langchain 的线程池扇出，输出按字典 key 顺序收敛，因此
结果是确定且可逐行核对的。
"""

from __future__ import annotations

import concurrent.futures
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 极简 Runnable 基类
# 真实 Runnable 在 base.py:128，这里只保留 invoke 这一条主线接口。
# ---------------------------------------------------------------------------
class Runnable:
    def invoke(self, inp: Any, **kwargs: Any) -> Any:  # pragma: no cover - 占位
        raise NotImplementedError

    def __or__(self, other: Any) -> "RunnableSequence":
        # 对应 base.py:622 __or__ -> RunnableSequence(self, coerce_to_runnable(other))
        return RunnableSequence(self, coerce_to_runnable(other))


def coerce_to_runnable(thing: Any) -> Runnable:
    # 对应 base.py:6257
    #   Runnable -> 原样；callable -> RunnableLambda；dict -> RunnableParallel
    if isinstance(thing, Runnable):
        return thing
    if callable(thing):
        return RunnableLambda(thing)
    if isinstance(thing, dict):
        return RunnableParallel(thing)
    raise TypeError(f"Expected Runnable/callable/dict, got {type(thing)}")


class RunnableLambda(Runnable):
    """对应 langchain 的 RunnableLambda：把普通函数包成 Runnable。"""

    def __init__(self, fn: Callable[[Any], Any]) -> None:
        self.fn = fn

    def invoke(self, inp: Any, **kwargs: Any) -> Any:
        return self.fn(inp)


class RunnableSequence(Runnable):
    """对应 base.py:2861。

    __init__ 会把嵌套的 RunnableSequence 展平（base.py:2975-2992），
    并保证至少 2 步，否则报错。
    """

    def __init__(self, *steps: Any) -> None:
        flat: List[Runnable] = []
        for step in steps:
            if isinstance(step, RunnableSequence):
                flat.extend(step.steps)  # 展平嵌套
            else:
                flat.append(coerce_to_runnable(step))
        if len(flat) < 2:
            raise ValueError("RunnableSequence needs at least two steps")
        self.steps: List[Runnable] = flat

    def invoke(self, inp: Any, **kwargs: Any) -> Any:
        # 对应 base.py:3175 invoke：逐 step 串喂，kwargs 只传给第一步
        value = inp
        for i, step in enumerate(self.steps):
            if i == 0:
                value = step.invoke(value, **kwargs)
            else:
                value = step.invoke(value)
        return value


class RunnableParallel(Runnable):
    """对应 base.py:3609。

    __init__ 把 dict 的每个值 coerce 成 Runnable（base.py:3695）；
    invoke 用线程池并发扇出（base.py:3878-3935），同输入、总耗时约等于最慢分支。
    """

    def __init__(self, steps: Dict[str, Any]) -> None:
        self.steps: Dict[str, Runnable] = {
            k: coerce_to_runnable(v) for k, v in steps.items()
        }

    def invoke(self, inp: Any, **kwargs: Any) -> Dict[str, Any]:
        # 模拟 langchain 的 get_executor_for_config + 并发提交
        results: Dict[str, Any] = {}
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(self.steps) or 1
        ) as ex:
            futures = {
                k: ex.submit(step.invoke, inp)
                for k, step in self.steps.items()
            }
            for k in self.steps:  # 按 key 顺序收敛，保证确定性
                results[k] = futures[k].result()
        return results


class RunnablePassthrough(Runnable):
    """对应 passthrough.py:74。invoke 恒等透传（passthrough.py:226 identity）。"""

    def invoke(self, inp: Any, **kwargs: Any) -> Any:
        return inp

    @classmethod
    def assign(cls, **kwargs: Any) -> "RunnableAssign":
        # 对应 passthrough.py:207：等于 RunnableAssign(RunnableParallel(kwargs))
        return RunnableAssign(RunnableParallel(dict(kwargs)))


class RunnableAssign(Runnable):
    """对应 passthrough.py:352。把并行结果回写进原字典。"""

    def __init__(self, parallel: RunnableParallel) -> None:
        self.parallel = parallel

    def invoke(self, inp: Any, **kwargs: Any) -> Any:
        extra = self.parallel.invoke(inp)
        # 真实实现把 extra（dict）合并回原 input dict
        if isinstance(inp, dict) and isinstance(extra, dict):
            return {**inp, **extra}
        return extra


class RunnableBranch(Runnable):
    """对应 branch.py:42。

    invoke（branch.py:189）顺序扫描 (condition, runnable)，第一个 condition 为真即
    命中并 break；全不命中走 default（顺序即优先级）。
    """

    def __init__(
        self,
        *branches: Tuple[Callable[[Any], Any], Runnable],
        default: Optional[Runnable] = None,
    ) -> None:
        self.branches: List[Tuple[Callable[[Any], Any], Runnable]] = list(branches)
        self.default = default

    def invoke(self, inp: Any, **kwargs: Any) -> Any:
        for condition, runnable in self.branches:
            if condition(inp):
                return runnable.invoke(inp, **kwargs)
        if self.default is not None:
            return self.default.invoke(inp, **kwargs)
        raise ValueError("no branch matched and no default")


class RunnableWithFallbacks(Runnable):
    """对应 fallbacks.py:36。

    invoke（fallbacks.py:166）顺序尝试，捕获 exceptions_to_handle（默认 Exception），
    全失败抛 first_error（fallbacks.py:199-213）。
    """

    def __init__(
        self,
        *runnables: Runnable,
        exceptions_to_handle: Tuple[type, ...] = (Exception,),
    ) -> None:
        self.runnables: List[Runnable] = list(runnables)
        self.exceptions_to_handle = exceptions_to_handle

    def invoke(self, inp: Any, **kwargs: Any) -> Any:
        first_error: Optional[BaseException] = None
        for runnable in self.runnables:
            try:
                return runnable.invoke(inp, **kwargs)
            except self.exceptions_to_handle as e:  # noqa: B902
                if first_error is None:
                    first_error = e
        if first_error is not None:
            raise first_error
        raise ValueError("no runnables provided")


# ---------------------------------------------------------------------------
# 案例函数：工单预处理（与正文贯穿案例一致）
# ---------------------------------------------------------------------------
def classify(ticket: Dict[str, Any]) -> Dict[str, Any]:
    text = ticket["text"]
    if "退款" in text:
        intent = "refund"
    elif "催单" in text:
        intent = "urge"
    else:
        intent = "general"
    return {**ticket, "intent": intent}


def extract(ticket: Dict[str, Any]) -> Dict[str, Any]:
    return {**ticket, "entities": ["订单号12345"]}


def summarize(ticket: Dict[str, Any]) -> Dict[str, Any]:
    return {**ticket, "summary": ticket["text"][:12] + "..."}


def refund_reply(ticket: Dict[str, Any]) -> Dict[str, Any]:
    return {**ticket, "reply": "已为您发起退款，预计原路退回"}


def urge_reply(ticket: Dict[str, Any]) -> Dict[str, Any]:
    return {**ticket, "reply": "已加急催促仓库，请稍候"}


def general_reply(ticket: Dict[str, Any]) -> Dict[str, Any]:
    return {**ticket, "reply": "已收到您的留言，客服稍后联系"}


def build_pipeline() -> RunnableSequence:
    """正文里那条竖线流水线：分类 -> 并行抽取+摘要 -> 按意图路由。"""
    router = RunnableBranch(
        (lambda x: x["intent"] == "refund", RunnableLambda(refund_reply)),
        (lambda x: x["intent"] == "urge", RunnableLambda(urge_reply)),
        default=RunnableLambda(general_reply),
    )
    # 注意：这里的 assign 用 dict 直接喂给 RunnableParallel 也会被 coerce
    return RunnableSequence(
        RunnableLambda(classify),
        RunnablePassthrough.assign(extract=extract, summary=summarize),
        router,
    )


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------
def _self_test() -> int:
    failures: List[str] = []

    # 1) Sequence 展平 + 逐 step 喂值
    seq = RunnableLambda(classify) | RunnablePassthrough.assign(
        extract=extract, summary=summarize
    )
    nested = seq | RunnableLambda(refund_reply)
    # nested 应被展平为 3 步，而非 2 步
    if len(nested.steps) != 3:
        failures.append(f"Sequence 未展平：期望 3 步，实际 {len(nested.steps)} 步")

    # 2) 整条流水线端到端
    pipe = build_pipeline()
    out = pipe.invoke({"text": "我要退款订单号12345"})
    expected_keys = {"text", "intent", "extract", "summary", "reply"}
    if set(out.keys()) != expected_keys:
        failures.append(f"流水线输出字段不符：{sorted(out.keys())}")
    if out["intent"] != "refund":
        failures.append(f"intent 分类错误：{out['intent']}")
    if out["reply"] != "已为您发起退款，预计原路退回":
        failures.append(f"路由回复错误：{out['reply']}")

    # 3) Parallel 并发形状：输出按 key 收敛
    par = RunnableParallel({"a": RunnableLambda(extract), "b": RunnableLambda(summarize)})
    pout = par.invoke({"text": "x"})
    if set(pout.keys()) != {"a", "b"}:
        failures.append(f"Parallel 输出 key 不符：{sorted(pout.keys())}")

    # 4) Branch 顺序即优先级 + default
    br = RunnableBranch(
        (lambda x: x > 10, RunnableLambda(lambda x: "big")),
        (lambda x: x > 5, RunnableLambda(lambda x: "mid")),
        default=RunnableLambda(lambda x: "small"),
    )
    if br.invoke(20) != "big" or br.invoke(7) != "mid" or br.invoke(1) != "small":
        failures.append("RunnableBranch 路由/默认分支错误")

    # 5) WithFallbacks 容错：主路抛错走 fallback
    def boom(_: Any) -> Any:
        raise RuntimeError("主路挂了")

    fb = RunnableWithFallbacks(
        RunnableLambda(boom),
        RunnableLambda(lambda x: "兜底成功"),
        exceptions_to_handle=(RuntimeError,),
    )
    if fb.invoke(None) != "兜底成功":
        failures.append("WithFallbacks 未兜底")
    # 全部失败应抛出 first_error
    fb2 = RunnableWithFallbacks(
        RunnableLambda(boom), RunnableLambda(boom), exceptions_to_handle=(RuntimeError,)
    )
    try:
        fb2.invoke(None)
        failures.append("WithFallbacks 全失败时未抛错")
    except RuntimeError:
        pass

    if failures:
        print("self-test FAIL")
        for f in failures:
            print("  - " + f)
        return 1

    print("self-test PASS")
    print("--- pipeline 端到端输出（与正文复现模块一致）---")
    final = build_pipeline().invoke({"text": "我要退款订单号12345"})
    for k in sorted(final.keys()):
        print(f"{k} = {final[k]}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        sys.exit(_self_test())
    print("用法：python composite_primitives.py --self-test")
