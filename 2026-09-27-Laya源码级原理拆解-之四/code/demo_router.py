#!/usr/bin/env python3
"""第33篇之四配套脚本：Laya 路由优先级的最小可复现实现（纯标准库，无需 torch）。

本文件从 laya/router.py 抽取了「纯路由决策」这一层，把真正加载模型、跑推理的部分
替换成可注入的 mock，让你不下载 1.16B 参数、不装 torch 也能看清 _route 的优先级链：
    explicit model > explicit task > detected workflow(需 auto_task_detection)
    > explicit lang > lang_guess > detected script/language > default

运行：
    python3 demo_router.py --self-test     # 跑断言，全部通过打印 self-test PASS
    python3 demo_router.py                 # 打印一组演示路由结果

源码对照：laya/router.py 的 _english_from_code(156-174)、_ALIASES(75-80)、
normalise_name(110-116)、match_typed_decisions_workflow(119-129)、_route(457-548)。
"""

import sys

# --- 直接从源码抄来的常量与别名，保证与仓库一致 ---------------------------------------

# router.py:45-51
_DEFAULT_MODELS = {
    "english": ("convaiinnovations/laya", None),
    "multilingual": ("convaiinnovations/laya", "multilingual"),
    "typed-decisions": ("convaiinnovations/laya", "typed-decisions"),
}

# router.py:142-153 —— 路由只需要一个比特：这是英文拉丁文本，还是英文 checkpoint 读不了的东西。
_ENGLISH_SUBTAGS = ("en", "eng", "english")
# C / POSIX / und / zxx / mul 这些 $LANG 值不命名任何语言，应当弃权（交给检测），而不是把英文钉死。
_LANGUAGE_AGNOSTIC_CODES = ("c", "posix", "und", "zxx", "mul")

# router.py:75-80 —— 人们可能随手敲的别名。
_ALIASES = {
    "en": "english", "laya": "english", "default": "english",
    "multi": "multilingual", "ml": "multilingual", "laya-multilingual": "multilingual",
    "typed": "typed-decisions", "typed_decisions": "typed-decisions",
    "laya-typed-decisions": "typed-decisions", "decisions": "typed-decisions",
}

# router.py:84-89 —— 四个 typed-decisions 工作流的精确 question-id 签名（只在 auto_task_detection 时用到）。
_TYPED_DECISION_WORKFLOWS = {
    "agent_trace_observability": {"action", "needs_review", "outcome", "risk", "urgency"},
    "customer_service": {"action", "category", "churn_risk", "needs_human", "urgency"},
    "invoice_processing": {"discrepancy_severity", "disposition", "duplicate", "matches_order", "urgency"},
    "security_incidents": {"credential_compromise", "disposition", "severity", "true_positive", "urgency"},
}


def _english_from_code(value):
    """router.py:156-174 的原样复刻：把语言代码归约到 True/False/None。

    None 表示「这条线索没用」，让语言识别模型可以弃权，也正好让 LANG=C 之类
    不命名语言的代码穿过检测而不是把每个请求都钉到某一个 checkpoint。
    """
    if value is None:
        return None
    code = str(value).strip().lower()
    if not code:
        return None
    code = code.split(".", 1)[0]                       # en_US.UTF-8 -> en_US
    primary = code.replace("_", "-").split("-", 1)[0]  # en_US -> en
    if not primary or primary in _LANGUAGE_AGNOSTIC_CODES:
        return None
    return primary in _ENGLISH_SUBTAGS


class RouteDecision(dict):
    """router.py:92-107 的复刻：路由结果，同时是 dict（可直接序列化进 API 响应）。"""

    @property
    def model(self):
        return self["model"]

    @property
    def reason(self):
        return self["reason"]


def normalise_name(name):
    """router.py:110-116 的复刻：别名归一化 + 未知模型报错。"""
    key = str(name).strip().lower()
    key = _ALIASES.get(key, key)
    if key not in _DEFAULT_MODELS:
        raise ValueError("unknown model %r; choose one of %s" % (name, sorted(_DEFAULT_MODELS)))
    return key


def match_typed_decisions_workflow(questions):
    """router.py:119-129 的复刻：精确 id-set 匹配，多一个或少一个都不算。"""
    ids = set(questions or {})
    for wf, sig in _TYPED_DECISION_WORKFLOWS.items():
        if ids == sig:
            return wf
    return None


def _repo_str(models, key):
    """router.py:61-64 的复刻：给出 checkpoint 的可读 id。"""
    repo, sub = models[key]
    return "%s/%s" % (repo, sub) if sub else repo


def route_decision(state, questions=None, model=None, task=None, lang=None,
                   lang_guess=None, models=None, default="english",
                   auto_task_detection=False, analyse_fn=None):
    """router.py:_route(457-548) 的复刻：只做路由决策，不加载、不推理。

    analyse_fn 是可注入的检测函数，默认返回英文拉丁文本的探测结果，便于不装 torch 也能跑。
    优先级链与源码逐字对齐：
        model > task > workflow(需开关) > lang > lang_guess > 检测 > default
    """
    models = models or _DEFAULT_MODELS
    analyse_fn = analyse_fn or (lambda s: {
        "script": "latin", "script_profile": {}, "language": "en", "is_english": True,
        "non_latin_fraction": 0.0, "mixed_segment": None, "diacritic_rate": 0.0,
        "language_undecided": False,
    })

    if model is not None:
        key = normalise_name(model)
        return RouteDecision(model=key, repo=_repo_str(models, key),
                             reason="explicit model=%r" % model, detection=None, workflow=None)

    if task is not None:
        key = normalise_name("typed-decisions" if str(task).lower().replace("-", "_") == "typed_decisions" else task)
        return RouteDecision(model=key, repo=_repo_str(models, key),
                             reason="explicit task=%r" % task, detection=None, workflow=None)

    workflow = match_typed_decisions_workflow(questions or {})
    if workflow and auto_task_detection:
        return RouteDecision(model="typed-decisions", repo=_repo_str(models, "typed-decisions"),
                             reason="question ids match the %r typed-decisions workflow" % workflow,
                             detection=None, workflow=workflow)

    if lang is not None:
        resolved = _english_from_code(lang)
        if resolved is not None:
            key = "english" if resolved else "multilingual"
            return RouteDecision(model=key, repo=_repo_str(models, key),
                                 reason="explicit lang=%r" % lang, detection=None, workflow=workflow)

    # lang_guess：per-call 优先，其次 Router 级；只有真正回答了的线索才路由，其余穿过检测。
    for source, hint in (("lang_guess", lang_guess),):
        resolved = hint if isinstance(hint, bool) else _english_from_code(hint)
        if resolved is not None:
            key = "english" if resolved else "multilingual"
            return RouteDecision(
                model=key, repo=_repo_str(models, key),
                reason="%s: caller identified this as %s text" % (
                    source, "English" if resolved else "non-English"),
                detection=None, workflow=workflow)

    det = analyse_fn(state)
    if det["script"] == "unknown":
        key = default
        reason = "no letters detected in state; using default (%s)" % key
    elif det["script"] != "latin":
        key = "multilingual"
        reason = "non-Latin script (%s, %.0f%% of letters); English checkpoint cannot read it" % (
            det["script"], 100 * float(det["non_latin_fraction"]))
    elif not det["is_english"]:
        key = "multilingual"
        if det.get("mixed_segment"):
            reason = "Latin but a segment reads as %r; English checkpoint cannot read it" % det["language"]
        elif det["language"]:
            reason = "Latin script but language looks like %r, not English" % det["language"]
        else:
            reason = "Latin, language not identified but %.0f%% non-English letters" % (
                100 * float(det["diacritic_rate"]))
    elif det.get("language_undecided"):
        key = default
        reason = "Latin, language not identified; using default (%s)" % key
    else:
        key = "english"
        reason = "English Latin text"
    return RouteDecision(model=key, repo=_repo_str(models, key), reason=reason,
                         detection=det, workflow=workflow)


# --- 演示：一组能看清优先级链的路由 -----------------------------------------------

def _demo():
    customer_service_qs = {"action": None, "category": None, "churn_risk": None,
                           "needs_human": None, "urgency": None}
    print("== 路由优先级演示（analyse 默认返回英文拉丁文本）==")
    cases = [
        ("显式 model=ml", dict(model="ml")),
        ("显式 task=typed_decisions", dict(task="typed_decisions")),
        ("显式 questions=customer_service + auto=True",
         dict(questions=customer_service_qs, auto_task_detection=True)),
        ("同上但 auto=False（关掉后穿过到检测）",
         dict(questions=customer_service_qs, auto_task_detection=False)),
        ("显式 lang=de", dict(lang="de")),
        ("显式 lang=en", dict(lang="en")),
        ("lang_guess=fr", dict(lang_guess="fr")),
        ("无任何线索 -> default(english)", dict()),
    ]
    for label, kw in cases:
        d = route_decision("some state text", **kw)
        print("  %-46s -> %-16s %s" % (label, d.model, d.reason))

    print("\n== 检测分支：注入不同的探测结果 ==")
    injected = {
        "non-latin": lambda s: {"script": "han", "is_english": False,
                                "non_latin_fraction": 1.0, "language": None,
                                "mixed_segment": None, "diacritic_rate": 0.0,
                                "language_undecided": True},
        "german": lambda s: {"script": "latin", "is_english": False,
                             "non_latin_fraction": 0.0, "language": "de",
                             "mixed_segment": None, "diacritic_rate": 0.0,
                             "language_undecided": False},
        "english": lambda s: {"script": "latin", "is_english": True,
                              "non_latin_fraction": 0.0, "language": "en",
                              "mixed_segment": None, "diacritic_rate": 0.0,
                              "language_undecided": False},
    }
    for label, fn in injected.items():
        d = route_decision("x", analyse_fn=fn)
        print("  detect=%-10s -> %-16s %s" % (label, d.model, d.reason))


def _self_test():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    # 1) _english_from_code
    for code, expect in [("en", True), ("EN", True), ("en-US", True), ("en_US", True),
                         ("en_US.UTF-8", True), ("de", False), ("de-DE", False),
                         ("zh", False), ("C", None), ("und", None), ("", None),
                         (None, None)]:
        got = _english_from_code(code)
        check(got == expect, "_english_from_code(%r) = %r, expect %r" % (code, got, expect))

    # 2) normalise_name
    for alias, expect in [("en", "english"), ("ml", "multilingual"),
                          ("typed", "typed-decisions"), ("laya", "english"),
                          ("english", "english")]:
        check(normalise_name(alias) == expect, "normalise_name(%r) != %r" % (alias, expect))
    try:
        normalise_name("not-a-model")
        check(False, "normalise_name('not-a-model') 应当抛 ValueError")
    except ValueError:
        pass

    # 3) match_typed_decisions_workflow
    cs = {"action", "category", "churn_risk", "needs_human", "urgency"}
    check(match_typed_decisions_workflow(cs) == "customer_service",
          "customer_service 精确签名未匹配")
    check(match_typed_decisions_workflow({"action", "urgency"}) is None,
          "子集不应匹配")
    check(match_typed_decisions_workflow({"urgency", "foo", "bar"}) is None,
          "无关 schema 含 urgency 不应被捕获")

    # 4) 路由优先级
    cs_qs = {k: None for k in cs}
    # model 最高优先级
    d = route_decision("x", model="ml", task="typed_decisions", lang="de",
                       questions=cs_qs, auto_task_detection=True)
    check(d.model == "multilingual" and "explicit model" in d.reason,
          "model 应压过 task/lang/workflow")
    # task 压过 workflow
    d = route_decision("x", task="typed_decisions", questions=cs_qs,
                       auto_task_detection=True)
    check(d.model == "typed-decisions" and "explicit task" in d.reason,
          "explicit task 应压过 workflow")
    # workflow 需要 auto_task_detection
    d = route_decision("x", questions=cs_qs, auto_task_detection=True)
    check(d.model == "typed-decisions", "auto=True 时应命中 workflow")
    d = route_decision("x", questions=cs_qs, auto_task_detection=False)
    check("explicit" not in d.reason, "auto=False 时应穿过 workflow")
    # explicit lang=de -> multilingual
    d = route_decision("x", lang="de")
    check(d.model == "multilingual" and "explicit lang" in d.reason, "lang=de 应路由 multilingual")
    # explicit lang=en -> english
    d = route_decision("x", lang="en")
    check(d.model == "english", "lang=en 应路由 english")
    # lang_guess=fr 在 lang=None 后生效
    d = route_decision("x", lang_guess="fr")
    check(d.model == "multilingual" and "lang_guess" in d.reason, "lang_guess=fr 应路由 multilingual")
    # 默认英文拉丁文本
    d = route_decision("x")
    check(d.model == "english", "默认应为 english")
    # 检测分支：non-latin
    nonlatin = lambda s: {"script": "han", "is_english": False, "non_latin_fraction": 1.0,
                          "language": None, "mixed_segment": None, "diacritic_rate": 0.0,
                          "language_undecided": True}
    d = route_decision("x", analyse_fn=nonlatin)
    check(d.model == "multilingual" and "non-Latin" in d.reason, "non-latin 应路由 multilingual")
    # 检测分支：german（拉丁但非英文）
    german = lambda s: {"script": "latin", "is_english": False, "non_latin_fraction": 0.0,
                        "language": "de", "mixed_segment": None, "diacritic_rate": 0.0,
                        "language_undecided": False}
    d = route_decision("x", analyse_fn=german)
    check(d.model == "multilingual", "德语应路由 multilingual")
    # 检测分支：english
    english = lambda s: {"script": "latin", "is_english": True, "non_latin_fraction": 0.0,
                         "language": "en", "mixed_segment": None, "diacritic_rate": 0.0,
                         "language_undecided": False}
    d = route_decision("x", analyse_fn=english)
    check(d.model == "english", "英文应路由 english")

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
