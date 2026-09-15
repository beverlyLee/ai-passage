#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最小客服 agent-loop 演示：意图 → 检索 → 工具 → 生成，并测量 TTFT / 工具调用 / 幻觉风险。

说明：这是「机制模拟器」，不是真实 LLM 调用。它用可配置参数复现 AI 客服翻车的四类机制
（延迟 / 幻觉 / 上下文污染 / 静默失败），让读者看清「为什么」会翻车。真实企业数字见文章
参考来源（BestHub 23% 静默失败、Traversaal 调研 74% 企业回滚等；具体数字见文章，本文不引用未核实的个案数字）。脚本默认参数是示意值，
不是某家公司的真实配置。

运行：
    python3 01_agent_loop.py --self-test     # 内置断言，CI 直接跑
    python3 01_agent_loop.py --demo          # 打印一段多轮对话的逐轮指标
"""
import argparse
import random
import re

# 退款单号正确格式：RF + 10 位数字。生成器若产出不符此格式，即「幻觉退款 ID」。
REFUND_ID_RE = re.compile(r"^RF\d{10}$")


class KnowledgeBase:
    """极简知识库。retrieve 以 error_rate 概率返回「无关文档」，模拟检索不准。"""
    DOCS = {
        "refund": "退款需在签收后 7 天内申请，单号格式 RF + 10 位数字。",
        "coupon": "618 大促折扣规则：满 300 减 50，不与会员券叠加。",
    }

    def __init__(self, error_rate, rng):
        self.error_rate = error_rate
        self.rng = rng

    def retrieve(self, intent):
        if intent not in self.DOCS:
            return None
        # 检索不准：把 refund 用户导向 coupon 文档（或反之），下游就会基于错误信息作答
        if self.rng.random() < self.error_rate:
            wrong = "coupon" if intent == "refund" else "refund"
            return wrong
        return intent


class ToolSet:
    """模拟订单/退款工具。silent_fail_rate 是「每次工具调用静默失败」的直接概率——
    接口报错被模型「圆」成一条看似正常的结果（最危险的静默失败）。hard_fail_rate 是
    正常报错（可被捕获）的概率。"""
    def __init__(self, silent_fail_rate=0.23, hard_fail_rate=0.05, rng=None):
        self.silent_fail_rate = silent_fail_rate
        self.hard_fail_rate = hard_fail_rate
        self.rng = rng

    def query_order(self):
        if self.rng.random() < self.hard_fail_rate:
            return {"ok": False, "error": "tool_timeout"}
        if self.rng.random() < self.silent_fail_rate:
            # 静默失败：接口异常，但被模型「圆」成一条看似合理的假数据
            return {"ok": True, "silent": True, "status": "已发货（推测）"}
        return {"ok": True, "status": "运输中"}

    def issue_refund(self, amount):
        if self.rng.random() < self.hard_fail_rate:
            return {"ok": False, "error": "refund_failed"}
        if self.rng.random() < self.silent_fail_rate:
            # 静默失败：退款接口异常，却回了个非法单号（同时触发幻觉判定）
            return {"ok": True, "silent": True, "refund_id": "RF123"}
        return {"ok": True, "refund_id": "RF%010d" % self.rng.randint(0, 9999999999)}


def recognize_intent(text):
    """规则式意图识别（示意）。"""
    if "退款" in text or "退钱" in text:
        return "refund"
    if "券" in text or "优惠" in text or "折扣" in text:
        return "coupon"
    if "订单" in text or "物流" in text or "到哪" in text:
        return "order"
    return "unknown"


class CustomerServiceAgent:
    """最小客服 agent-loop。一次 handle() 跑完「意图→检索→工具→生成」并测量 TTFT。"""
    def __init__(self, retrieval_ms=1200, tool_ms=900, gen_ms=1100,
                 retrieval_error_rate=0.18, silent_fail_rate=0.23,
                 hard_fail_rate=0.05, seed=42):
        self.retrieval_ms = retrieval_ms
        self.tool_ms = tool_ms
        self.gen_ms = gen_ms
        self.rng = random.Random(seed)
        self.kb = KnowledgeBase(retrieval_error_rate, self.rng)
        self.tools = ToolSet(silent_fail_rate, hard_fail_rate, self.rng)

    def handle(self, user_text, history_turns=0):
        intent = recognize_intent(user_text)
        doc = self.kb.retrieve(intent)

        tool_result = None
        silent_fail = False
        tool_ms = 0
        if intent in ("order", "refund"):
            if intent == "order":
                tool_result = self.tools.query_order()
            else:
                tool_result = self.tools.issue_refund(100)
            silent_fail = bool(tool_result.get("silent"))
            tool_ms = self.tool_ms

        # TTFT（延迟预算）= 检索 + 工具 + 生成首字。机制模拟器直接用配置值，不做真实 sleep。
        ttft_ms = self.retrieval_ms + tool_ms + self.gen_ms

        reply, hallucination = self._generate(user_text, intent, doc, tool_result)
        return {
            "intent": intent,
            "retrieved_doc": doc,
            "tool_result": tool_result,
            "reply": reply,
            "ttft_ms": round(ttft_ms, 1),
            "hallucination": hallucination,   # 基于错误知识或非法退款 ID
            "silent_fail": silent_fail,        # 工具静默失败
            "context_polluted": history_turns >= 6,  # 长对话窗口溢出（示意）
        }

    def _generate(self, user_text, intent, doc, tool_result):
        # 幻觉判定 1：检索到了无关文档，仍基于它作答
        if intent in ("refund", "coupon") and doc is not None and doc != intent:
            return ("根据规则，您的情况可以这样处理……（基于错误知识作答）", True)
        # 工具硬失败（可被捕获）→ 安全兜底，不编造
        if tool_result and tool_result.get("ok") is False:
            return ("系统暂时无法处理，正在为您转接人工客服。", False)
        if intent == "refund":
            rid = tool_result.get("refund_id")
            if rid and not REFUND_ID_RE.match(rid):
                return ("您的退款单号是 %s，请留意查收。" % rid, True)
            return ("已为您提交退款，单号 %s，预计 3 个工作日到账。" % rid, False)
        if intent == "coupon":
            return ("当前可用优惠券：满 300 减 50。", False)
        if intent == "order":
            if tool_result.get("silent"):
                return ("您的订单已发货，预计明天送达。（实为推测）", True)
            return ("您的订单状态：%s。" % tool_result.get("status"), False)
        return ("抱歉，我帮您转接人工客服。", False)


def _demo():
    agent = CustomerServiceAgent(seed=7)
    turns = [
        "我要退款", "我的订单到哪了", "那张券怎么用", "再问下退款到哪步了",
        "订单还没动静", "券能叠加吗", "退款单号给我", "物流查不到",
    ]
    print("轮 | 意图    | TTFT(ms) | 幻觉 | 静默失败 | 回复")
    print("-" * 78)
    for i, t in enumerate(turns):
        r = agent.handle(t, history_turns=i)
        print("%2d | %-7s | %8.1f | %4s | %8s | %s" % (
            i + 1, r["intent"], r["ttft_ms"], r["hallucination"],
            r["silent_fail"], r["reply"][:30]))


def _self_test():
    # 1) 结构断言（零误差干净 agent：合法退款不应判幻觉）
    agent = CustomerServiceAgent(seed=1, retrieval_error_rate=0.0, hard_fail_rate=0.0)
    r = agent.handle("我要退款", history_turns=0)
    assert set(["intent", "retrieved_doc", "tool_result", "reply",
                "ttft_ms", "hallucination", "silent_fail",
                "context_polluted"]).issubset(r.keys())
    assert REFUND_ID_RE.match(r["tool_result"]["refund_id"]), "退款 ID 格式非法"
    assert r["hallucination"] is False, "合法退款不应被判幻觉"

    # 2) 幻觉检测：构造「检索到错误文档」场景
    bad = CustomerServiceAgent(retrieval_error_rate=1.0, seed=2)
    r2 = bad.handle("我要退款", history_turns=0)
    assert r2["hallucination"] is True, "检索到无关文档应被判幻觉"

    # 3) 静默失败检测
    silent = CustomerServiceAgent(silent_fail_rate=1.0, seed=3)
    r3 = silent.handle("我的订单到哪了", history_turns=0)
    assert r3["silent_fail"] is True, "工具静默失败应被标记"

    # 4) 上下文污染标志（长对话）
    r4 = agent.handle("物流查不到", history_turns=6)
    assert r4["context_polluted"] is True, "第 6 轮后应标记上下文污染"

    # 5) TTFT 量级合理（默认参数下应 > 2 秒，体现长链路延迟）
    assert r["ttft_ms"] > 2000, "默认链路 TTFT 应明显偏高"
    print("SELF-TEST PASS")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        _self_test()
    elif args.demo:
        _demo()
    else:
        _demo()
