"""Laya 路由层源码级复现（纯 Python，无需 torch、无需 HuggingFace token）。

演示 router.py 的两条核心事实：
  1. Router 在 import 阶段不拉 torch，route() 也不拉 torch（只跑 lang.analyse 做文字/语言检测）。
  2. 路由优先级链与 typed-decisions 工作流的精确 id 集合匹配。

运行：
    python demo_router.py            # 打印路由样例
    python demo_router.py --self-test # 跑断言并核对预期输出
"""
import sys

sys.path.insert(0, "/tmp/laya-src")  # 本地 clone 的源码；装了 pip install laya 可删掉这行

from laya.router import Router, normalise_name, match_typed_decisions_workflow


def case(state, questions=None, model=None, lang=None, auto_task_detection=False):
    r = Router(default="english", auto_task_detection=auto_task_detection)
    d = r.route(state, questions=questions, model=model, lang=lang)
    print("  state=%r" % (state[:48] if isinstance(state, str) else state))
    if questions:
        print("  questions-ids=%s" % sorted(questions))
    print("  -> model=%s  reason=%s" % (d["model"], d["reason"]))
    return d


def main():
    print("[1] 英文拉丁文本 -> english（默认路由目标）")
    case("I want to cancel my subscription please")

    print("\n[2] 葡萄牙语拉丁文本 -> multilingual（is_english=False）")
    case("Quero cancelar minha conta agora")

    print("\n[3] 显式 model 别名 multi -> multilingual（优先级高于检测）")
    case("anything at all", model="multi")

    print("\n[4] 显式 lang=pt -> multilingual；lang=en -> english")
    case("x", lang="pt")
    case("x", lang="en")

    print("\n[5] typed-decisions：问题 id 精确匹配四工作流之一 -> typed-decisions")
    wf = {"action": "a", "needs_review": "n", "outcome": "o", "risk": "r", "urgency": "u"}
    case("trace payload", questions=wf, auto_task_detection=True)

    print("\n[6] 近邻 schema（多一个无关键）-> 不匹配，落回默认 english")
    near = dict(wf)
    near["extra"] = "z"  # 破坏精确 id 集合
    case("trace payload", questions=near, auto_task_detection=True)

    print("\n[7] 别名解析 normalise_name")
    for a in ("en", "ml", "typed", "default"):
        print("  %r -> %r" % (a, normalise_name(a)))


def self_test():
    r = Router(default="english")
    assert r.route("I want to cancel my subscription")["model"] == "english"
    assert r.route("Quero cancelar minha conta")["model"] == "multilingual"
    assert r.route("x", model="multi")["model"] == "multilingual"
    assert r.route("x", lang="pt")["model"] == "multilingual"
    assert r.route("x", lang="en")["model"] == "english"
    wf = {"action": "a", "needs_review": "n", "outcome": "o", "risk": "r", "urgency": "u"}
    rt = Router(default="english", auto_task_detection=True)
    assert rt.route("trace", questions=wf)["model"] == "typed-decisions"
    near = dict(wf); near["extra"] = "z"
    assert rt.route("trace", questions=near)["model"] == "english"  # 精确匹配失败
    assert match_typed_decisions_workflow(wf) == "agent_trace_observability"
    assert normalise_name("ml") == "multilingual"
    print("self-test PASS: 路由优先级链与 typed-decisions 精确匹配均符合预期")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        main()
