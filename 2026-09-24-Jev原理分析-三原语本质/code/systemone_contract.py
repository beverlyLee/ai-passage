#!/usr/bin/env python3
# 源码级协议契约模拟器：本地复现 TypeSafe / Jev 的 System One API 契约（设备告警分诊场景版）。
#
# 重要边界（与正文一致）：
#   Jev 模型本身未开源，这里不是 typesafe-sdk 的源码，也不是 Jev 内部实现。
#   这是一份严格按官方公开文档（docs.typesafe.ai/api）字段约束写的本地重实现，
#   用来把"协议契约"这一层源码级事实跑起来、可验证，且不需要 API key。
#
#   本文件是「Jev 原理分析」系列第二篇（三原语的本质）的复现模块，承接第一篇
#   「架构总览」已建立的 System1/System2 分工，把三原语落到一条设备告警上：
#     - alert_category : Choice -> 告警归类（网络抖动 / 硬件故障 / 容量压力 / 正常）
#     - severity       : Score  -> 严重度 0~2，可落在档间（如 1.326）
#     - is_incident    : Noul   -> 确信真实故障 0~1，响应只有 noul，没有 confidence
#
#   关键设计（与正文一致）：Jev 只输出"判断"，不输出"动作"。最终升级/转人工/自动恢复
#   是开发者用 if/elif 按"错误成本"写的确定性路由（见 route_action），不是 Jev 给的。
#   这正体现三原语的本质：输出空间预先枚举、schema-safe，路由逻辑完全在你手里。
#
# 覆盖的官方契约要点：
#   - 请求顶层三字段：state / model / questions（均必填）
#   - Noul：响应只有 noul(0~1)，没有 confidence
#   - Choice：criteria 上限 255 选项；响应 probabilities 之和必须为 1，附 confidence
#   - Score：criteria 必须是 2~10 档的数组；响应 score 可落在档间（如 1.326）
#   - 错误码：422（非法请求）。真实 SDK 还会返 401/429/529，本脚本只演示 422。
#
# 用法：
#   python3 systemone_contract.py --self-test
#   python3 systemone_contract.py --demo
import argparse
import random


class ContractError(Exception):
    """对应官方错误码，这里只用 422。"""

    def __init__(self, code, message):
        super().__init__(f"[{code}] {message}")
        self.code = code


# 三个原语的请求规范（与官方 API 的 Question 对象字段对齐）。
class Noul:
    type = "noul"

    def __init__(self, instructions, criteria=None):
        self.instructions = instructions
        self.criteria = criteria or {"true": "是", "false": "否"}


class Choice:
    type = "choice"

    def __init__(self, instructions, criteria):
        self.instructions = instructions
        self.criteria = criteria  # 必填，dict，键=选项，值=描述


class Score:
    type = "score"

    def __init__(self, instructions, criteria):
        self.instructions = instructions
        self.criteria = criteria  # 必填，list，2~10 档


def _validate_request(state, model, questions):
    """逐字段校验请求契约，不合法抛 422（与官方一致）。"""
    if state is None or not isinstance(state, (str, dict, list)):
        raise ContractError(422, "state 必填，且必须是 string/object/array")
    if not isinstance(model, str) or not model:
        raise ContractError(422, "model 必填，且必须是字符串（如 jev-latest）")
    if not isinstance(questions, dict) or not questions:
        raise ContractError(422, "questions 必填，且必须是 map<string,Question>")
    for key, q in questions.items():
        if not isinstance(key, str) or not key:
            raise ContractError(422, "questions 的键必须是非空字符串")
        if q.type == "noul":
            if not isinstance(q.instructions, (str, dict, list)):
                raise ContractError(422, f"[{key}] noul 的 instructions 必填")
        elif q.type == "choice":
            if not isinstance(q.criteria, dict) or len(q.criteria) < 1:
                raise ContractError(422, f"[{key}] choice 的 criteria 必填且非空")
            if len(q.criteria) > 255:
                raise ContractError(422, f"[{key}] choice 的 criteria 最多 255 选项")
            if not isinstance(q.instructions, (str, dict, list)):
                raise ContractError(422, f"[{key}] choice 的 instructions 必填")
        elif q.type == "score":
            if not isinstance(q.criteria, list) or not (2 <= len(q.criteria) <= 10):
                raise ContractError(422, f"[{key}] score 的 criteria 必须是 2~10 档数组")
            if not isinstance(q.instructions, (str, dict, list)):
                raise ContractError(422, f"[{key}] score 的 instructions 必填")
        else:
            raise ContractError(422, f"[{key}] 未知原语类型：{q.type}")


def _fake_answer(q, rng):
    """本地确定性后端：返回符合该原语响应形状的答案，不联网、不要 key。"""
    if q.type == "noul":
        # 关键源码级事实：Noul 响应只有 noul，没有 confidence 字段。
        return {"noul": round(rng.uniform(0.0, 1.0), 4)}
    if q.type == "choice":
        opts = list(q.criteria.keys())
        n = len(opts)
        raw = [rng.uniform(0.0, 1.0) for _ in range(n)]
        s = sum(raw)
        probs = {o: round(p / s, 4) for o, p in zip(opts, raw)}
        # 修正浮点尾差，保证显式之和为 1。
        probs[opts[0]] = round(1.0 - sum(probs[o] for o in opts[1:]), 4)
        best = max(opts, key=lambda o: probs[o])
        # confidence 由概率分布导出（最大概率）。
        return {"choice": best, "probabilities": probs, "confidence": probs[best]}
    if q.type == "score":
        n = len(q.criteria)
        raw = [rng.uniform(0.0, 1.0) for _ in range(n)]
        s = sum(raw)
        probs = {str(i): round(p / s, 4) for i, p in enumerate(raw)}
        probs[str(0)] = round(1.0 - sum(probs[str(i)] for i in range(1, n)), 4)
        # score 可落在档间（如 1.326），这正是 Score 与 Choice 的区别之一。
        score = sum(i * probs[str(i)] for i in range(n))
        confidence = max(probs.values())
        legend = {str(i): d for i, d in enumerate(q.criteria)}
        return {"score": round(score, 3), "legend": legend,
                "probabilities": probs, "confidence": round(confidence, 4)}


class FakeTypeSafeClient:
    """模仿 typesafe-sdk 的 client.system_one(...) 调用形状，但本地可跑。

    真实场景你换成对 api.typesafe.ai/v1/systemone 的 HTTP 调用即可，
    接口保持一致：state + questions -> {model, answers, usage}。
    """

    def __init__(self, model="jev-latest", seed=7, api_key=None):
        self.model = model
        self._rng = random.Random(seed)
        self._api_key = api_key  # 真实 SDK 需要 Bearer token；本模拟器留空也行

    def system_one(self, state, questions, model=None):
        m = model or self.model
        _validate_request(state, m, questions)
        answers = {}
        for key, q in questions.items():
            answers[key] = _fake_answer(q, self._rng)
        # 输出免费：usage 只计 input_tokens，output_tokens 记为 0。
        # 注意：这里曾写成 len(str(questions))，但 questions 里是对象，其默认 repr 带
        # 内存地址，跨进程会变，导致 input_tokens 不固定。改成只依赖 state 长度与问题数，
        # 保证读者重跑得到完全一致的 usage（演示近似，真实以你的账户返回为准）。
        n_input = len(str(state)) // 4 + len(questions) + 1
        return {
            "model": "jev-1.13.0",  # 实际模型版本号，对应官方响应顶层 model
            "answers": answers,
            "usage": {"input_tokens": n_input, "output_tokens": 0},
        }


# ---- 开发者侧的确定性路由：Jev 给判断，人写阈值，错误成本决定阈值高低 ----
# 这不是 Jev 的输出，是业务代码。正是三原语"输出空间预定、schema-safe"的好处：
# 你拿到的一定是这三个形状，路由逻辑因此可以写成不会崩的 if/elif。

# 策略 A（保守）：错放一次真实故障的代价 > 错拦一次误报告警（如机房宕机、SLA 违约、
# 半夜被叫醒后发现的却是假预警）。它的阈值是 incident 超过 0.9 升级、severity 超过 1.5 升级、
# severity 超过 1.0 转人工核验。
POLICY_CONSERVATIVE = {"escalate_if_incident_ge": 0.9, "escalate_if_severity_ge": 1.5,
                        "review_if_severity_ge": 1.0}

# 策略 B（宽松）：错拦会制造告警疲劳，真实故障反而被淹没（如值班被假预警叫醒太多次，
# 真出事时没人信了），宁可多转人工。它的阈值是 incident 超过 0.95 升级、severity 超过 2.0 升级、
# severity 超过 1.5 转人工核验。
POLICY_LOOSE = {"escalate_if_incident_ge": 0.95, "escalate_if_severity_ge": 2.0,
                "review_if_severity_ge": 1.5}


def route_action(answers, policy):
    """同一组 Jev 判断，按不同错误成本假设得到不同裁决。"""
    incident = answers["is_incident"]["noul"]
    severity = answers["severity"]["score"]
    if incident >= policy["escalate_if_incident_ge"]:
        return "escalate"  # 确信真实故障，直接升级/派单
    if severity >= policy["escalate_if_severity_ge"]:
        return "escalate"  # 高严重度，直接升级
    if severity >= policy["review_if_severity_ge"]:
        return "review"  # 中严重度，转人工核验
    return "auto"  # 低严重度，自动恢复/忽略


def _self_test():
    client = FakeTypeSafeClient(seed=7)

    # 1) 合法请求：Choice + Score + Noul 一次并行，响应形状必须合规。
    resp = client.system_one(
        state="告警：node-07 在 03:14 CPU 97%、磁盘 IO 等待飙升、三探针同时报红，QPS 未降",
        questions={
            "alert_category": Choice(
                instructions="这条告警最像哪类问题",
                criteria={"net": "网络抖动", "hardware": "硬件故障",
                          "capacity": "容量压力", "normal": "正常波动"},
            ),
            "severity": Score(
                instructions="严重度分", criteria=["低", "中", "高"]
            ),
            "is_incident": Noul(instructions="这是否为一次真实故障"),
        },
    )
    ans = resp["answers"]
    assert "noul" in ans["is_incident"] and "confidence" not in ans["is_incident"], \
        "Noul 响应必须只有 noul，不能带 confidence"
    assert abs(sum(ans["alert_category"]["probabilities"].values()) - 1.0) < 1e-6, \
        "Choice 的 probabilities 之和必须为 1"
    assert 0 <= ans["severity"]["score"] <= 2, "Score 的 score 必须在刻度范围内"
    assert resp["usage"]["output_tokens"] == 0, "输出必须免费（output_tokens=0）"

    # 2) 路由逻辑：同一组判断，保守策略比宽松策略更激进（错放更贵）。
    sample = {"is_incident": {"noul": 0.18}, "severity": {"score": 1.08}}
    assert route_action(sample, POLICY_CONSERVATIVE) == "review", "1.08 在保守策略下转人工"
    assert route_action(sample, POLICY_LOOSE) == "auto", "1.08 在宽松策略下自动恢复"
    high = {"is_incident": {"noul": 0.97}, "severity": {"score": 1.9}}
    assert route_action(high, POLICY_CONSERVATIVE) == "escalate"
    assert route_action(high, POLICY_LOOSE) == "escalate", "确信真实故障在两种策略下都升级"

    # 3) 非法请求触发 422：Choice 选项超过 255。
    too_many = {f"o{i}": f"opt{i}" for i in range(256)}
    try:
        client.system_one(state="x", questions={"c": Choice("i", too_many)})
        raise AssertionError("超过 255 选项应当触发 422")
    except ContractError as e:
        assert e.code == 422, "应当返回 422"

    # 4) Score 档数越界触发 422：只有 1 档（要求 2~10）。
    try:
        client.system_one(state="x", questions={"s": Score("i", ["只有一档"])})
        raise AssertionError("Score 只有 1 档应当触发 422")
    except ContractError as e:
        assert e.code == 422, "应当返回 422"

    print("self-test PASS: 协议契约的形状、错误码、路由与阈值逻辑均成立")


def _demo():
    # 一条"看着吓人、但说不清是不是真故障"的告警：这是告警分诊最难受的区间。
    client = FakeTypeSafeClient(seed=21)
    state = ("告警：node-07 在 03:14 触发，CPU 持续 97%、磁盘 IO 等待飙升、"
             "同一时刻三个探针同时报红，但业务 QPS 未见明显下滑、错误率平稳")
    resp = client.system_one(
        state=state,
        questions={
            "alert_category": Choice(
                instructions="这条告警最像哪类问题",
                criteria={"net": "网络抖动", "hardware": "硬件故障",
                          "capacity": "容量压力", "normal": "正常波动"},
            ),
            "severity": Score(
                instructions="严重度（0=低，2=高，可落档间）",
                criteria=["低", "中", "高"],
            ),
            "is_incident": Noul(instructions="这是否为一次真实故障"),
        },
    )
    print(f"model={resp['model']}  usage={resp['usage']}")
    a = resp["answers"]
    print(f"alert_category.choice = {a['alert_category']['choice']}")
    print(f"alert_category.probs  = {a['alert_category']['probabilities']}")
    print(f"severity.score        = {a['severity']['score']}  legend={a['severity']['legend']}")
    print(f"is_incident.noul      = {a['is_incident']['noul']}  (无 confidence)")
    print("-" * 48)
    print("同一组判断，两种错误成本假设下的裁决：")
    print(f"  保守策略(错放更贵) -> {route_action(a, POLICY_CONSERVATIVE)}")
    print(f"  宽松策略(错拦更贵) -> {route_action(a, POLICY_LOOSE)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        _self_test()
    elif args.demo:
        _demo()
    else:
        _self_test()
        print("-" * 48)
        _demo()


if __name__ == "__main__":
    main()
