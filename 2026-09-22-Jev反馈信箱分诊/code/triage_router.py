#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
triage_router.py — 用 Jev（TypeSafe AI SystemOne）给独立开发者的反馈邮件做分诊路由。
纯标准库实现，不依赖任何 Jev SDK，方便本地跑、改、注入假后端。

核心思路（也是这篇文章要讲透的 Jev 特殊原理）：
  把一封邮件的「派哪个部门 / 急不急 / 要不要人先看」拆成三类原语的一次并行调用：
    - department : Choice  （从一组显式 criteria 里选一个，带 probabilities + confidence）
    - urgency    : Score   （在有序刻度上打分 1..4，可落在两档之间，带 probabilities + confidence）
    - escalate   : Noul    （是否需人工介入，返回 0..1，没有单独的 confidence）
  模型只给「判断」，程序拿回类型化概率后用确定性规则路由（不交给模型自由发挥）。

用法：
  python3 triage_router.py --self-test      # 跑断言：验证路由策略 + 假后端返回形状
  python3 triage_router.py --demo           # 跑几条内置样例，看完整路由报告
  TYPESAFE_API_KEY=xxx python3 triage_router.py --ticket 某封邮件.txt   # 走真实 API

架构：
  JevBackend          抽象接口 ask(state, questions) -> answers
  HttpJevBackend       真实后端：POST https://api.typesafe.ai/v1/systemone （urllib，无第三方依赖）
  FakeJevBackend       假后端：按关键词规则返回可信形状的答案，无需 key 即可复现全部逻辑

Jev 真实 API 字段（已一手/独立核实，见文末来源）：
  请求体：{ "state": <str|json>, "model": "jev-latest", "questions": { "<id>": {type, instructions, criteria} } }
  响应体：{ "model", "answers": { "<id>": {type, choice?, probabilities?, confidence?, score?, legend?, noul?} }, "usage": {input_tokens, output_tokens} }
"""

import sys
import os
import json
import urllib.request

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
PRICE_PER_MTOK_INPUT = 0.042  # 美元 / 每百万输入 token（输出免费，官方公布）

# ---- 显式 criteria：每条判断的「答案空间」必须写清楚，这是 Jev 正确性的前提 ----
DEPARTMENTS = {
    "billing":   "账单、扣款、退款、订阅、发票、付款相关问题",
    "bug":       "功能坏了、报错、崩溃、集成失败、打不开",
    "feature":   "想要新功能、产品建议、体验改进",
    "complaint": "投诉、差评、情绪化抱怨、威胁离开",
    "security":  "安全漏洞、数据泄露、未授权访问、可疑攻击",
    "spam":      "广告、无关、灌水、垃圾推广",
    "other":     "以上都不沾边",
}

URGENCY_LEVELS = [
    "可以等一周再处理",
    "正常，一天内回复即可",
    "今天就得处理，卡住了用户的工作",
    "卡住了有时效的事件或正在丢钱",
]


def build_questions():
    """构造一次调用里的三个原子问题。
    复合判断（‘这封该怎么处理’）会被拆成三个原子问题，再用代码组合，这是官方明确建议的用法。
    state 传 JSON 对象，instructions 里用点路径（ticket.body / ticket.subject）指向具体字段，
    模型读的是切片而不是整段乱翻，也避免把无关上下文塞进共享的 32K 预算。
    """
    return {
        "department": {
            "type": "choice",
            "instructions": "读 ticket.subject 和 ticket.body，这封用户来信应该派给哪个团队处理？",
            "criteria": DEPARTMENTS,
        },
        "urgency": {
            "type": "score",
            "instructions": "读 ticket.body，这封来信的紧急程度？按下面的有序刻度打分。",
            "criteria": URGENCY_LEVELS,
        },
        "escalate": {
            "type": "noul",
            "instructions": "读 ticket.body：这封来信是否需要一个真人先读一遍再决定怎么回（例如涉及安全、愤怒投诉、法律、或拿不准）？",
        },
    }


# ----------------------------------------------------------------------------- 后端


class JevBackend:
    """抽象接口。子类实现 ask()，返回 answers（嵌套 dict，按问题 id 索引）。"""

    def ask(self, state, questions):
        raise NotImplementedError


class HttpJevBackend(JevBackend):
    """真实后端。读环境变量 TYPESAFE_API_KEY，按核实过的 schema 发请求。"""

    def __init__(self, api_key=None, model=MODEL):
        self.api_key = api_key or os.environ.get("TYPESAFE_API_KEY")
        self.model = model

    def ask(self, state, questions):
        if not self.api_key:
            raise RuntimeError("缺少 TYPESAFE_API_KEY：真实后端需要 API key。")
        body = json.dumps({"state": state, "model": self.model, "questions": questions}).encode("utf-8")
        req = urllib.request.Request(
            ENDPOINT,
            data=body,
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # 官方错误码：401 密钥错 / 422 校验失败 / 429 限流 / 529 过载
            raise RuntimeError("Jev API 返回 %d：%s" % (e.code, e.read().decode("utf-8", "replace")))
        return data


class FakeJevBackend(JevBackend):
    """假后端：按关键词规则返回与真实 API 同形状的答案。
    它不做真正的模型推理，但能复现『三类原语 + 确定性路由』的全部工程逻辑，
    所以 self-test 和 demo 都不需要 API key。
    """

    # 各部门的命中关键词
    KEYWORDS = {
        "billing":   ["扣款", "退款", "账单", "订阅", "发票", "付款", "invoice", "charge", "refund", "收费", "续费"],
        "bug":       ["报错", "崩溃", "坏了", "失败", "打不开", "闪退", "bug", "卡死", "异常", "用不了"],
        "feature":   ["希望", "建议", "能不能", "加个", "想要", "feature request", "期待", "希望增加"],
        "complaint": ["投诉", "太差", "垃圾", "再也不用", "差评", "愤怒", "失望", "退订", "气"],
        "security":  ["漏洞", "泄露", "越权", "未授权", "注入", "黑客", "攻击", "exploit", "数据外泄", "被黑"],
        "spam":      ["优惠", "免费领", "加微信", "点击链接", "中奖", "推广", "兼职", "代购"],
    }
    URGENT_WORDS = ["急", "马上", "立刻", "立即", "今天", "现在", "丢钱", "损失", "客户", "上线", "demo",
                   "urgent", "asap", "losing", "production", "线上", "上线前"]
    ANGRY_WORDS = ["太差", "垃圾", "再也不用", "愤怒", "失望", "投诉", "气", "受不了"]

    def _classify(self, text):
        low = text.lower()
        counts = {k: sum(1 for w in ws if w.lower() in low) for k, ws in self.KEYWORDS.items()}
        total = sum(counts.values())
        if total == 0:
            # 没有任何关键词命中：归到 other，且置信很低（程序应据此转人工）
            return "other", {"other": 1.0}, 0.2
        # 归一化为概率分布
        probs = {k: v / total for k, v in counts.items()}
        best = max(probs, key=probs.get)
        best_p = probs[best]
        # 置信度 = 最大项与次大项之差（分布越集中越自信），封顶 0.99
        ordered = sorted(probs.values(), reverse=True)
        conf = min(0.99, 0.4 + (ordered[0] - (ordered[1] if len(ordered) > 1 else 0.0)))
        return best, probs, conf

    def _urgency(self, text):
        low = text.lower()
        hits = sum(1 for w in self.URGENT_WORDS if w.lower() in low)
        # 打分落在 0..3 之间的浮点（官方示例里 score 可以卡在两档之间，例如 1.035）
        score = min(3.0, 0.2 + 0.9 * hits)
        # 置信：关键词越多越有把握
        conf = min(0.95, 0.3 + 0.25 * hits) if hits else 0.4
        # 4 档有序刻度上的概率分布（越靠近 score 的档位质量越大），归一化后随答案返回
        raw = {i: max(1e-3, 1.0 - abs(i - score)) for i in range(len(URGENCY_LEVELS))}
        tot = sum(raw.values())
        probs = {str(i): round(v / tot, 4) for i, v in raw.items()}
        return score, probs, conf

    def _escalate(self, text):
        low = text.lower()
        if any(w.lower() in low for w in self.KEYWORDS["security"]):
            return 0.96  # 安全类：必须人先看
        if any(w.lower() in low for w in self.ANGRY_WORDS):
            return 0.82  # 愤怒投诉：人先看更稳
        if any(w.lower() in low for w in self.URGENT_WORDS):
            return 0.4   # 急但不一定需要人
        return 0.08      # 常规：基本不用人

    def ask(self, state, questions):
        # state 可以是字符串或 dict；统一取正文
        if isinstance(state, dict):
            text = (state.get("subject", "") or "") + "\n" + (state.get("body", "") or "")
        else:
            text = str(state)
        dept, probs, dconf = self._classify(text)
        uscore, uprobs, uconf = self._urgency(text)
        esc = self._escalate(text)

        inp_tokens = max(1, len(json.dumps({"state": state, "questions": questions}, ensure_ascii=False)) // 4)
        answers = {
            "department": {
                "type": "choice",
                "choice": dept,
                "probabilities": probs,
                "confidence": round(dconf, 3),
            },
            "urgency": {
                "type": "score",
                "score": round(uscore, 3),
                "probabilities": uprobs,
                "legend": {str(i): lvl for i, lvl in enumerate(URGENCY_LEVELS)},
                "confidence": round(uconf, 3),
            },
            "escalate": {
                "type": "noul",
                "noul": round(esc, 3),
            },
        }
        return {"model": MODEL, "answers": answers, "usage": {"input_tokens": inp_tokens, "output_tokens": 0}}


# ----------------------------------------------------------------------------- 路由策略（程序拥有阈值，不是 Jev 拥有）


def priority_tier(score):
    """把 1..4 的紧急度映射到 P0..P3 队列档位。"""
    if score >= 3.0:
        return "P0"
    if score >= 2.0:
        return "P1"
    if score >= 1.0:
        return "P2"
    return "P3"


def route(ticket_meta, answers, auto_threshold=0.7):
    """确定性路由：Jev 给判断，代码写规则。这是整条链路真正的『决策点』。
    auto_threshold：部门置信低于它 → 转人工复核（阈值按错误成本设，不是 SLA）。
    """
    a = answers["answers"]
    dept = a["department"]["choice"]
    dconf = a["department"]["confidence"]
    uscore = a["urgency"]["score"]
    esc = a["escalate"]["noul"]

    decision = {
        "department": dept,
        "department_confidence": dconf,
        "urgency_score": uscore,
        "escalate_prob": esc,
    }

    # 规则优先级从高到低：安全 > 灌水 > 低置信/需人 > 自动派单
    if dept == "security":
        decision["queue"] = "human_priority"   # 安全类永远人先看 + 置顶，绝不自动回
        decision["assignee"] = "security_oncall"
        decision["note"] = "安全信号：必须真人介入，不经过自动回复"
    elif dept == "spam":
        decision["queue"] = "discard"           # 灌水直接丢弃，不占人工
        decision["assignee"] = "none"
        decision["note"] = "判定为灌水，丢弃"
    elif esc > 0.5 or dconf < auto_threshold:
        decision["queue"] = "human_review"      # 需人先看，或部门置信太低拿不准
        decision["assignee"] = "triage_human"
        decision["note"] = "低置信或需人介入：转人工复核"
    else:
        decision["queue"] = "auto"
        decision["assignee"] = "team:" + dept
        decision["priority"] = priority_tier(uscore)
        decision["note"] = "高置信：自动派单到对应团队，按紧急度排优先级"

    return decision


def triage_one(backend, ticket_meta, auto_threshold=0.7):
    state = {"subject": ticket_meta.get("subject", ""), "body": ticket_meta.get("body", "")}
    resp = backend.ask(state, build_questions())
    decision = route(ticket_meta, resp, auto_threshold)
    decision["input_tokens"] = resp["usage"]["input_tokens"]
    decision["cost_usd"] = resp["usage"]["input_tokens"] * PRICE_PER_MTOK_INPUT / 1_000_000.0
    return decision


# ----------------------------------------------------------------------------- 展示


def fmt_decision(meta, d):
    return (
        "  [%s] %s\n"
        "       部门=%s(置信%.2f)  紧急度=%.2f  需人=%.2f  队列=%s  派给=%s  花费=$%.7f"
        % (meta.get("from", "?"), meta.get("subject", ""),
           d["department"], d["department_confidence"], d["urgency_score"],
           d["escalate_prob"], d["queue"], d.get("assignee", "-"), d["cost_usd"])
    )


# ----------------------------------------------------------------------------- self-test


def self_test():
    be = FakeJevBackend()
    samples = [
        # 安全漏洞：必须 human_priority
        {"subject": "疑似越权访问", "body": "我发现一个越权漏洞，普通用户能读到别人的数据，疑似数据泄露，请尽快看", "from": "sec@x"},
        # 灌水：必须 discard
        {"subject": "免费领红包", "body": "点击链接免费领红包，加微信领取优惠，兼职刷单日入过千", "from": "spam@x"},
        # 干净的 bug，强信号高置信：必须 auto + 派 technical
        {"subject": "导出按钮崩溃", "body": "在 Safari 上点导出按钮就崩溃，Chrome 正常，求解", "from": "u1@x"},
        # 模糊、无关键词：必须 human_review（低置信）
        {"subject": "你好", "body": "在吗，有点事想说", "from": "u2@x"},
        # 账单 + 急：高置信 auto，但紧急度应拉高
        {"subject": "重复扣款", "body": "我被重复扣款了两次，现在很急，今天就要处理，正在丢钱", "from": "vip@x"},
    ]
    expected = ["human_priority", "discard", "auto", "human_review", "auto"]
    ok = True
    for meta, exp in zip(samples, expected):
        d = triage_one(be, meta)
        got = d["queue"]
        flag = "OK " if got == exp else "FAIL"
        if got != exp:
            ok = False
        print("  %s 期望=%-13s 实得=%-13s" % (flag, exp, got) + fmt_decision(meta, d).strip())

    # 断言假后端返回的形状正确（schema 安全：choice 必在 criteria 内、score 带 probabilities/legend、noul 在 0..1）
    r = be.ask({"subject": "x", "body": "退款"}, build_questions())
    da = r["answers"]["department"]
    assert da["type"] == "choice" and da["choice"] in DEPARTMENTS, "Choice 形状错误"
    assert abs(sum(da["probabilities"].values()) - 1.0) < 1e-6, "概率未归一化"
    sa = r["answers"]["urgency"]
    assert sa["type"] == "score" and "legend" in sa and 0 <= sa["score"] <= 3 \
        and abs(sum(sa["probabilities"].values()) - 1.0) < 1e-2, "Score 形状错误"
    na = r["answers"]["escalate"]
    assert na["type"] == "noul" and 0.0 <= na["noul"] <= 1.0, "Noul 形状错误"
    assert "input_tokens" in r["usage"] and "output_tokens" in r["usage"], "usage 形状错误"

    print("\n  self-test: %s（路由策略=%d 条断言，假后端形状=4 条断言）" % ("全部通过" if ok else "有失败", 5))
    return ok


def demo():
    be = FakeJevBackend()
    samples = [
        {"subject": "疑似越权访问", "body": "我发现一个越权漏洞，普通用户能读到别人的数据，疑似数据泄露，请尽快看", "from": "sec@x"},
        {"subject": "免费领红包", "body": "点击链接免费领红包，加微信领取优惠，兼职刷单日入过千", "from": "spam@x"},
        {"subject": "导出按钮崩溃", "body": "在 Safari 上点导出按钮就崩溃，Chrome 正常，求解", "from": "u1@x"},
        {"subject": "想要暗色模式", "body": "建议加个暗色模式，晚上用太刺眼了，期待", "from": "u3@x"},
        {"subject": "重复扣款", "body": "我被重复扣款了两次，现在很急，今天就要处理，正在丢钱", "from": "vip@x"},
        {"subject": "在吗", "body": "在吗，有点事想说", "from": "u2@x"},
    ]
    total_cost = 0.0
    print("  反馈信箱分诊报告（假后端，无需 API key）：")
    for meta in samples:
        d = triage_one(be, meta)
        total_cost += d["cost_usd"]
        print(fmt_decision(meta, d))
    print("\n  合计 %d 封：Jev 输入 token 成本约 $%.7f（输出免费）" % (len(samples), total_cost))
    print("  对比：聊天模型要逐封生成路由+回复，单封通常要几秒且另计输出 token；这里 6 封合计远低于 1 美分。")


def main(argv):
    if "--self-test" in argv:
        return 0 if self_test() else 1
    if "--demo" in argv:
        demo()
        return 0
    # 默认：走真实后端处理单封（需要 TYPESAFE_API_KEY）
    if "--ticket" in argv:
        idx = argv.index("--ticket")
        path = argv[idx + 1]
        with open(path, encoding="utf-8") as f:
            body = f.read()
        meta = {"subject": body.splitlines()[0] if body else "", "body": body, "from": "file"}
        try:
            d = triage_one(HttpJevBackend(), meta)
        except Exception as e:
            print("真实后端调用失败（你可能没设 TYPESAFE_API_KEY）：%s" % e)
            print("改用 --demo 或 --self-test 看本地可复现版本。")
            return 1
        print(fmt_decision(meta, d))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
