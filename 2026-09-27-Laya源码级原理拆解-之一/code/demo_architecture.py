"""Laya 包组织与 lazy import 源码级复现（纯 Python，无需 torch、无需 numpy、无需 HuggingFace token）。

演示 __init__.py 的两条核心事实：
  1. import laya 时不拉 torch / numpy（纯 Python 层在顶层直接导入，torch 层全部延迟）。
  2. 访问 laya.Agent 这类 torch 后端名时，才经 __getattr__ -> import_module 真正加载；
     在加载之前，'Agent' 只登记在 _LAZY_ATTRS 里，不在 globals()，但会被 dir(laya) 列出。
  3. lang.analyse 返回 dict（不是属性对象），路由层靠 script / is_english 决定走哪个 checkpoint。

运行：
    python demo_architecture.py            # 打印 lazy import 与语言检测样例
    python demo_architecture.py --self-test # 跑断言并核对预期输出
"""
import sys

sys.path.insert(0, "/tmp/laya-src")  # 本地 clone 的源码；装了 pip install laya 可删掉这行


def main():
    print("[1] import laya 之前与之后，torch / numpy 是否被加载？")
    print("  before import laya -> 'torch' in sys.modules:",
          "torch" in sys.modules, "| 'numpy' in sys.modules:", "numpy" in sys.modules)

    import laya
    print("  laya.__version__ =", laya.__version__)
    print("  after  import laya -> 'torch' in sys.modules:",
          "torch" in sys.modules, "| 'numpy' in sys.modules:", "numpy" in sys.modules)

    print("\n[2] 纯 Python 层在顶层直接导入，无需 torch / numpy")
    from laya.router import Router, normalise_name   # 顶层导入，立即可用
    from laya.hooks import HookRegistry
    print("  Router / normalise_name / HookRegistry 已可直接引用")

    print("\n[3] torch 后端名只登记在 _LAZY_ATTRS，尚未真正加载")
    print("  'Agent' in laya._LAZY_ATTRS:", "Agent" in laya._LAZY_ATTRS)
    print("  'Agent' in laya.__dict__ (已解析的全局名):", "Agent" in laya.__dict__)
    print("  'laya.agent' in sys.modules (真正 import_module 过?):", "laya.agent" in sys.modules)
    print("  'Agent' listed by dir(laya):", "Agent" in dir(laya))
    print("  -> 只有访问 laya.Agent 时才会 import_module('laya.agent')，届时才需要 numpy/torch")

    print("\n[4] lang.analyse 返回 dict，靠 script / is_english 决定路由")
    from laya.lang import analyse
    for s in ("I want to cancel my subscription",
              "Quero cancelar minha conta",
              "你好，我要退款"):
        r = analyse(s)
        print("  %-40r -> script=%s is_english=%s language=%s"
              % (s[:40], r["script"], r["is_english"], r.get("language")))


def self_test():
    import laya
    assert laya.__version__ == "0.3.20"
    assert "torch" not in sys.modules and "numpy" not in sys.modules, \
        "import laya must not pull torch/numpy"
    # 纯 Python 层可在无 torch / numpy 下直接导入
    from laya.router import Router, normalise_name
    from laya.hooks import HookRegistry
    # torch 后端名延迟：登记在 _LAZY_ATTRS，但还没 import_module
    assert "Agent" in laya._LAZY_ATTRS
    assert "Agent" not in laya.__dict__
    assert "laya.agent" not in sys.modules
    assert "Agent" in dir(laya)
    # lang.analyse 真实行为
    from laya.lang import analyse
    r = analyse("I want to cancel my subscription")
    assert r["script"] == "latin" and r["is_english"] is True
    r2 = analyse("你好，我要退款")
    assert r2["script"] != "latin" and r2["is_english"] is False
    assert normalise_name("ml") == "multilingual"
    print("self-test PASS: 纯 Python 层 torch/numpy-free、Agent 延迟登记、lang.analyse 返回 dict 均符合预期")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        main()
