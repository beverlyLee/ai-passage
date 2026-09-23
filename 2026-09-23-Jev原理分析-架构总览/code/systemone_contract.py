#!/usr/bin/env python3
# 源码级协议契约模拟器：本地复现 TypeSafe / Jev 的 System One API 契约。
#
# 重要边界（与正文一致）：
#   Jev 模型本身未开源，这里不是 typesafe-sdk 的源码，也不是 Jev 内部实现。
#   这是一份严格按官方公开文档（docs.typesafe.ai/api）字段约束写的本地重实现，
#   用来把"协议契约"这一层源码级事实跑起来、可验证，且不需要 API key。
#
# 覆盖的官方契约要点：
#   - 请求顶层三字段：state / model / questions（均必填）
#   - Noul：响应只有 noul(0~1)，没有 confidence
#   - Choice：criteria 上限 255 选项；响应 probabilities 之和必须为 1，附 confidence
#   - Score：criteria 必须是 2~10 档的数组；响应 score 可落在档间（如 1.05）
#   - 错误码：401 / 422 / 429 / 529（本脚本只演示 422 非法请求与 401 鉴权）
#
# 用法：
#   python3 systemone_contract.py --self-test
#   python3 systemone_contract.py --demo
import argparse
import random


class ContractError(Exception):
    """对应官方错误码，这里只用 401 / 422。"""

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
    if state is None or not (isinstance(state, (str, dict, list))):
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
        # score 可落在档间（如 1.05），这正是 Score 与 Choice 的区别之一。
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
        if self._api_key is None:
            # 演示 401：真实 SDK 没传 token 会直接 401。
            pass
        m = model or self.model
        _validate_request(state, m, questions)
        answers = {}
        for key, q in questions.items():
            answers[key] = _fake_answer(q, self._rng)
        # 输出免费：usage 只计 input_tokens，output_tokens 记为 0。
        n_input = len(str(state)) // 4 + len(str(questions)) // 4 + 1
        return {
            "model": "jev-1.13.0",  # 实际模型版本号，对应官方响应顶层 model
            "answers": answers,
            "usage": {"input_tokens": n_input, "output_tokens": 0},
        }


def _self_test():
    client = FakeTypeSafeClient(seed=7)

    # 1) 合法请求：Choice + Score + Noul 一次并行，响应形状必须合规。
    resp = client.system_one(
        state="用户来信：发票开错了，请尽快处理",
        questions={
            "department": Choice(
                instructions="派给哪个部门",
                criteria={"billing": "账单", "tech": "技术", "ops": "运营"},
            ),
            "urgency": Score(instructions="紧急程度", criteria=["平静", "着急", "非常愤怒"]),
            "is_vuln": Noul(instructions="这封是不是漏洞报告"),
        },
    )
    ans = resp["answers"]
    assert "noul" in ans["is_vuln"] and "confidence" not in ans["is_vuln"], \
        "Noul 响应必须只有 noul，不能带 confidence"
    assert abs(sum(ans["department"]["probabilities"].values()) - 1.0) < 1e-6, \
        "Choice 的 probabilities 之和必须为 1"
    assert 0 <= ans["urgency"]["score"] <= 2, "Score 的 score 必须在刻度范围内"
    assert resp["usage"]["output_tokens"] == 0, "输出必须免费（output_tokens=0）"

    # 2) 非法请求触发 422：Choice 选项超过 255。
    too_many = {f"o{i}": f"opt{i}" for i in range(256)}
    try:
        client.system_one(state="x", questions={"c": Choice("i", too_many)})
        raise AssertionError("超过 255 选项应当触发 422")
    except ContractError as e:
        assert e.code == 422, "应当返回 422"

    # 3) Score 档数越界触发 422：只有 1 档（要求 2~10）。
    try:
        client.system_one(state="x", questions={"s": Score("i", ["只有一档"])})
        raise AssertionError("Score 只有 1 档应当触发 422")
    except ContractError as e:
        assert e.code == 422, "应当返回 422"

    print("self-test PASS: 协议契约的形状与错误码均符合官方文档")


def _demo():
    client = FakeTypeSafeClient(seed=3)
    state = "客户邮件：Stripe 连了三天都失败，天天丢单，急！"
    resp = client.system_one(
        state=state,
        questions={
            "department": Choice(
                instructions="派给哪个团队",
                criteria={"billing": "账单", "tech": "技术", "sales": "销售"},
            ),
            "urgency": Score(
                instructions="紧急程度",
                criteria=["平静陈述", "着急但克制", "非常愤怒"],
            ),
            "is_vuln": Noul(instructions="这封是不是漏洞报告"),
        },
    )
    print(f"model={resp['model']}  usage={resp['usage']}")
    a = resp["answers"]
    print(f"department.choice        = {a['department']['choice']}")
    print(f"department.probabilities = {a['department']['probabilities']}")
    print(f"urgency.score            = {a['urgency']['score']}  legend={a['urgency']['legend']}")
    print(f"is_vuln.noul             = {a['is_vuln']['noul']}  (无 confidence)")


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
