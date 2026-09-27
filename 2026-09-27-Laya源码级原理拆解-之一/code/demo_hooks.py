"""Laya 钩子框架源码级复现（纯 Python，无需 torch、无需 HuggingFace token）。

演示 hooks.py 的三条核心事实：
  1. HookRegistry 是 Agent / Router 都继承的 mixin，add_hook 在调用时读快照，不干扰在途调用。
  2. on_predict_start 里调用 ctx.skip([...]) 可以短路推理，用缓存结果代替真正 forward。
  3. dispatch 的 hooks_timeout 用一个后台线程 join 来给每个钩子设上限，超时抛 TimeoutError。

运行：
    python demo_hooks.py            # 打印钩子样例
    python demo_hooks.py --self-test # 跑断言并核对预期输出
"""
import sys
import time

sys.path.insert(0, "/tmp/laya-src")

from laya.hooks import HookRegistry, BaseHook, PredictContext, dispatch, validate_timeout


class MiniRuntime(HookRegistry):
    """用 HookRegistry 最小复刻 Agent/Router 的钩子驱动，便于无 torch 复现。"""

    def __init__(self):
        self.hooks = ()
        self._hooks_mutex = None

    def run(self, state, questions, hooks_timeout=None):
        ctx = PredictContext(states=[state], questions=questions or {})
        dispatch(self.hooks, "on_predict_start", ctx, timeout=hooks_timeout)
        if ctx.results is None:  # 没有被 start 钩子 skip 掉
            ctx.results = [{"answer": "simulated", "usage": {"input_tokens": 12, "output_tokens": 0}}]
        dispatch(self.hooks, "on_predict_end", ctx, timeout=hooks_timeout)
        return ctx


class Tracer(BaseHook):
    def on_predict_start(self, ctx):
        print("  [hook] on_predict_start fired, states=%d" % len(ctx.states))

    def on_predict_end(self, ctx):
        print("  [hook] on_predict_end fired, results=%s" % (ctx.results,))


class CacheShortcut(BaseHook):
    """start 钩子直接 skip，推理被短路。"""

    def on_predict_start(self, ctx):
        print("  [hook] on_predict_start: skip with cached result")
        ctx.skip([{"answer": "cached", "usage": {"input_tokens": 0, "output_tokens": 0}}])


class SlowHook(BaseHook):
    def on_predict_start(self, ctx):
        time.sleep(2.0)  # 故意超过 timeout


def main():
    print("[1] 普通钩子：观察 start / end 两个事件")
    rt = MiniRuntime()
    rt.add_hook(Tracer())
    out = rt.run("hello", {"q": "a"})
    print("  -> result answer=%s (真实推理未被短路)" % out.results[0]["answer"])

    print("\n[2] skip 短路：start 钩子设置缓存结果，不再跑推理")
    rt2 = MiniRuntime()
    rt2.add_hook(CacheShortcut())
    out2 = rt2.run("hello", {"q": "a"})
    print("  -> result answer=%s input_tokens=%s (推理被跳过)"
          % (out2.results[0]["answer"], out2.results[0]["usage"]["input_tokens"]))

    print("\n[3] 超时保护：钩子 sleep 超过 hooks_timeout -> TimeoutError")
    rt3 = MiniRuntime()
    rt3.add_hook(SlowHook())
    try:
        rt3.run("hello", {"q": "a"}, hooks_timeout=0.2)
        print("  -> 没有抛错（意外）")
    except TimeoutError as e:
        print("  -> 捕获到超时：%s" % e)


def self_test():
    rt = MiniRuntime()
    rt.add_hook(Tracer())
    out = rt.run("hello", {"q": "a"})
    assert out.results[0]["answer"] == "simulated"

    rt2 = MiniRuntime()
    rt2.add_hook(CacheShortcut())
    out2 = rt2.run("hello", {"q": "a"})
    assert out2.results[0]["answer"] == "cached"
    assert out2.results[0]["usage"]["input_tokens"] == 0

    rt3 = MiniRuntime()
    rt3.add_hook(SlowHook())
    raised = False
    try:
        rt3.run("hello", {"q": "a"}, hooks_timeout=0.2)
    except TimeoutError:
        raised = True
    assert raised, "expected TimeoutError from overrunning hook"
    assert validate_timeout(None) is None
    print("self-test PASS: 钩子框架的 add/dispatch/skip/timeout 均符合预期")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        main()
