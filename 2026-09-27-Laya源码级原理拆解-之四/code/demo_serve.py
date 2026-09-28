#!/usr/bin/env python3
"""第33篇之四配套脚本：laya/serve.py 的两个纯逻辑函数的最小复刻（无 FastAPI 依赖）。

laya-serve 把 Jev 的 /v1/systemone 协议暴露成 HTTP 服务。这里复刻其中两处不依赖框架的
纯逻辑，让你看清「客户端 model 字段如何映射到 checkpoint」和「请求限额守卫」：

  _resolve_model  : Jev 模型 id（如 jev-1）应当被忽略、让路由自动选；只有 Laya checkpoint
                    名或已发布 Hugging Face id 才被识别。
  _check_request_limits : 在 tokenize 之前拒绝缺 state / 超额 questions / 超额选项 / state 过大。

真实实现里这两个函数会从 fastapi 抛 HTTPException；这里用一个本地 mock 顶替，断言用状态码比对。

运行：
    python3 demo_serve.py --self-test     # 断言全过打印 self-test PASS
    python3 demo_serve.py                 # 打印一组演示

源码对照：laya/serve.py 的 _KNOWN_MODELS(54)、_PUBLISHED_MODEL_IDS(74-77)、
MAX_QUESTIONS(59)、MAX_STATE_CHARS(60)、MAX_CHOICE_OPTIONS(63)、MAX_SCORE_LEVELS(64)、
MAX_TOTAL_OPTIONS(65)、_resolve_model(87-103)、_check_request_limits(130-182)。
"""

import sys

# --- serve.py 里的常量（逐字对应） -------------------------------------------------

_KNOWN_MODELS = {"english", "multilingual", "typed-decisions"}
MAX_QUESTIONS = 64
MAX_STATE_CHARS = 50000
MAX_CHOICE_OPTIONS = 100
MAX_SCORE_LEVELS = 32
MAX_TOTAL_OPTIONS = 512

# serve.py:74-77 —— 已发布的 Hugging Face id，允许客户端直接点名 checkpoint。
_PUBLISHED_MODEL_IDS = {
    "convaiinnovations/laya-multilingual": "multilingual",
    "convaiinnovations/laya-typed-decisions": "typed-decisions",
}


class _HTTPException(Exception):
    """mock fastapi.HTTPException，只保留 status_code / detail 以便断言。"""

    def __init__(self, status_code, detail=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _resolve_model(model):
    """serve.py:_resolve_model(87-103) 的复刻。"""
    if not model:
        return None
    published = _PUBLISHED_MODEL_IDS.get(str(model).strip().lower())
    if published is not None:
        return published

    # 真实实现里这里 from .router import normalise_name，并包在 try/except 中：
    # Jev 客户端的 model 字段（如 "jev-1"）预期会 miss，当作「无显式 checkpoint」返回 None。
    try:
        key = normalise_name_local(model)
    except Exception:
        return None
    return key if key in _KNOWN_MODELS else None


def normalise_name_local(name):
    _ALIASES = {
        "en": "english", "laya": "english", "default": "english",
        "multi": "multilingual", "ml": "multilingual", "laya-multilingual": "multilingual",
        "typed": "typed-decisions", "typed_decisions": "typed-decisions",
        "laya-typed-decisions": "typed-decisions", "decisions": "typed-decisions",
    }
    key = str(name).strip().lower()
    key = _ALIASES.get(key, key)
    _DEFAULT = {"english", "multilingual", "typed-decisions"}
    if key not in _DEFAULT:
        raise ValueError("unknown model %r" % name)
    return key


def _check_request_limits(state, questions):
    """serve.py:_check_request_limits(130-182) 的复刻，抛本地 _HTTPException。"""
    if state is None:
        raise _HTTPException(status_code=400, detail="'state' is required")
    if not isinstance(questions, dict):
        raise _HTTPException(status_code=400, detail="'questions' must be an object")
    if len(questions) > MAX_QUESTIONS:
        raise _HTTPException(status_code=413,
                             detail="too many questions (%d > %d)" % (len(questions), MAX_QUESTIONS))

    total_options = 0
    for qid, question in questions.items():
        if not isinstance(question, dict):
            continue
        crit = question.get("criteria")
        qtype = question.get("type")
        if qtype == "choice" and isinstance(crit, (dict, list)):
            count = len(crit)
            total_options += count
            if count > MAX_CHOICE_OPTIONS:
                raise _HTTPException(
                    status_code=413,
                    detail="too many choice options for %r (%d > %d)" % (qid, count, MAX_CHOICE_OPTIONS),
                )
        elif qtype == "score" and isinstance(crit, list):
            count = len(crit)
            total_options += count
            if count > MAX_SCORE_LEVELS:
                raise _HTTPException(
                    status_code=413,
                    detail="too many score levels for %r (%d > %d)" % (qid, count, MAX_SCORE_LEVELS),
                )
    if total_options > MAX_TOTAL_OPTIONS:
        raise _HTTPException(
            status_code=413,
            detail="too many answer options across questions (%d > %d)" % (total_options, MAX_TOTAL_OPTIONS),
        )

    try:
        state_len = len(state) if isinstance(state, str) else len(str(state))
    except Exception:
        state_len = MAX_STATE_CHARS + 1
    if state_len > MAX_STATE_CHARS:
        raise _HTTPException(status_code=413,
                             detail="state too large (%d > %d chars)" % (state_len, MAX_STATE_CHARS))


# --- 演示 -----------------------------------------------------------------------

def _demo():
    print("== _resolve_model：Jev id 应被忽略，Laya checkpoint 名应被识别 ==")
    for m in ["jev-1", "gpt-4o", "", "english", "ml", "convaiinnovations/laya-multilingual",
              "convaiinnovations/laya"]:
        print("  %-38r -> %s" % (m, _resolve_model(m)))

    print("\n== _check_request_limits：超限应被拒 ==")
    ok_questions = {"category": {"type": "choice", "criteria": ["billing", "bug", "other"]}}
    try:
        _check_request_limits("I was charged twice", ok_questions)
        print("  正常请求(state+3选项) -> 通过")
    except _HTTPException as e:
        print("  正常请求竟被拒: %s" % e.detail)

    try:
        _check_request_limits(None, ok_questions)
        print("  缺 state 竟通过（应为 400）")
    except _HTTPException as e:
        print("  缺 state -> 400 %s" % e.detail)

    big = {"q%d" % i: {"type": "choice", "criteria": ["a%d" % j for j in range(10)]}
           for i in range(20)}  # 20*10 = 200 选项，超过 MAX_TOTAL_OPTIONS? 不超；改超单题
    try:
        _check_request_limits("x", {"big": {"type": "choice", "criteria": list(range(200))}})
        print("  单题 200 选项竟通过（应为 413）")
    except _HTTPException as e:
        print("  单题超 100 选项 -> 413 %s" % e.detail)


def _self_test():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    # 1) _resolve_model
    check(_resolve_model("jev-1") is None, "Jev id 应被忽略 -> None")
    check(_resolve_model("gpt-4o") is None, "非 Laya 的 Jev 模型 id 应被忽略 -> None")
    check(_resolve_model("") is None, "空 model 应 -> None")
    check(_resolve_model("english") == "english", "english 别名应识别")
    check(_resolve_model("ml") == "multilingual", "ml 别名应识别")
    check(_resolve_model("convaiinnovations/laya-multilingual") == "multilingual",
          "已发布 HF id 应映射 multilingual")
    check(_resolve_model("convaiinnovations/laya") is None,
          "根 bundle id 意为「让路由选」，不应钉 english -> None")

    # 2) _check_request_limits
    ok = {"category": {"type": "choice", "criteria": ["billing", "bug"]}}
    try:
        _check_request_limits("I was charged twice", ok)
    except _HTTPException as e:
        fails.append("正常请求不应被拒，却收到 %d %s" % (e.status_code, e.detail))
    # 缺 state
    try:
        _check_request_limits(None, ok)
        fails.append("缺 state 应通过限额检查")
    except _HTTPException as e:
        check(e.status_code == 400, "缺 state 应为 400，实际 %d" % e.status_code)
    # 单题 choice 超 100
    try:
        _check_request_limits("x", {"big": {"type": "choice", "criteria": list(range(200))}})
        fails.append("单题 200 选项应通过限额检查")
    except _HTTPException as e:
        check(e.status_code == 413, "单题超选项应为 413，实际 %d" % e.status_code)
    # questions 非 dict
    try:
        _check_request_limits("x", ["not", "a", "dict"])
        fails.append("questions 非 dict 应通过")
    except _HTTPException as e:
        check(e.status_code == 400, "questions 非 dict 应为 400，实际 %d" % e.status_code)
    # state 过大
    try:
        _check_request_limits("x" * (MAX_STATE_CHARS + 1), ok)
        fails.append("超大 state 应通过")
    except _HTTPException as e:
        check(e.status_code == 413, "超大 state 应为 413，实际 %d" % e.status_code)

    if fails:
        print("self-test FAIL")
        for f in fails:
            print("  - " + f)
        return 1
    print("self-test PASS")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    _demo()
