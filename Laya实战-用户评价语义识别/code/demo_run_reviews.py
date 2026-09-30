#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
demo_run_reviews.py —— 全量脱敏评价跑批：清洗 -> 拆原子判断 -> 三原语聚合。

本脚本把「之五」数据集里的 10 条脱敏真实评价，跑完一条完整的 Laya 建模链路：
    1) 用 demo_clean_review.py 的四道闸清洗
    2) 一条评价按「连词 + 句末标点」拆成多条原子从句
    3) 每个从句映射到三原语：aspect=Choice / polarity=Score(0~2) / appeal=Noul(0~1)
    4) 按 aspect 聚合（同维度取多数极性 + 最大诉求度）

重要声明：本脚本的「模型」是一套确定性关键词启发式，仅用于演示与可复现。
真实生产环境里，第 2~4 步由 Laya 的 typed-decisions / multilingual checkpoint 承担
（经 router.py 路由到对应 checkpoint，见《之四：路由检测与服务部署》），无需手写规则。

运行：
    python3 demo_run_reviews.py --self-test
    python3 demo_run_reviews.py
"""
import sys
import os
import json
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from demo_clean_review import clean_review  # 复用清洗管线

# —— 三原语的 aspect 枚举（与 REVIEW_SCHEMA.aspect 一致）——
ASPECTS = ["物流", "客服", "价格", "稳定性", "界面", "质量", "包装", "学习", "功能", "其他"]

# 关键词 -> aspect 映射（覆盖中/英/葡/西）。一个从句可命中多个 aspect。
ASPECT_KEYWORDS = {
    "物流": ["物流", "快递", "发货", "收货", "到货", "配送", "entrega", "shipping",
            "delivery", "arrived"],
    "客服": ["客服", "服务", "态度", "atendimento", "serviço", "servicio", "support",
            "reply", "respondeu", "cliente"],
    "价格": ["价格", "钱", "省", "便宜", "会员", "vip", "订阅", "subscription", "worth",
            "caro", "preço", "barato", "frete"],
    "稳定性": ["卡顿", "崩溃", "闪退", "crash", "crashed", "稳定", "estável", "lento", "slow"],
    "界面": ["界面", "好看", "漂亮", "顺手", "ui", "design"],
    "质量": ["质量", "品质", "坏", "破", "roto", "broken", "灯珠", "死", "qualidade"],
    "包装": ["包装", "扎实", "embalado", "embalada", "packed"],
    "学习": ["学习", "葡萄牙语", "portuguese", "português", "learn", "voice recognition",
            "reconhecimento"],
    "功能": ["导出", "插图", "上限", "功能", "feature", "função"],
}

# 连词：用于把一条评价拆成原子从句
CONJUNCTIONS = ["但是", "但", "不过", "而", "就是", "且", "并", "but", "and", "mas", "pero", "aunque"]
SENT_END = "。！？!?;．."

NEG_WORDS = ["差", "慢", "崩溃", "卡顿", "敷衍", "不亮", "破", "roto", "broken", "crashed",
             "crash", "slow", "worse", "poor", "退订", "难用", "贵", "caro", "lento",
             "坏", "问题", "得不到", "未", "没", "não", "no", "demorou", "demorar", "ruim"]
POS_WORDS = ["快", "好", "满意", "扎实", "及时", "省", "推荐", "漂亮", "顺手", "bom", "boa",
             "great", "good", "perfect", "worth", "recomendo", "帮", "r\u00e1pido", "motivado",
             "r\u00e1pida", "satisfeito", "feliz"]
# 明确诉求（appeal 高）
EXPLICIT_APPEAL = ["希望你们尽快", "请修", "修复", "尽快修复", "提高上限", "增加", "希望增加",
                   "否则我只能退订", "fix", "repair", "please"]
# 建议性诉求（appeal 中）
SUGGEST_APPEAL = ["希望", "建议", "希望后续", "可以优化", "希望能", "希望可以"]


def _split_clauses(text):
    """把清洗后的评价拆成原子从句：连词替换为分隔符，再按句末标点切。"""
    low = text
    for c in CONJUNCTIONS:
        low = low.replace(c, " \u2423 ")  # 用特殊分隔符避免与正文冲突
    parts = []
    buf = ""
    for ch in low:
        buf += ch
        if ch in SENT_END:
            parts.append(buf.strip())
            buf = ""
    if buf.strip():
        parts.append(buf.strip())
    # 去掉分隔符残留
    return [p.replace("\u2423", " ").strip() for p in parts if p.strip()]


def _detect_aspects(clause):
    low = clause.lower()
    hits = []
    for aspect, kws in ASPECT_KEYWORDS.items():
        if any(kw in low for kw in kws):
            hits.append(aspect)
    if not hits:
        hits = ["其他"]
    return hits


def _polarity_window(clause, keyword):
    """在命中关键词的局部窗口内判定极性，避免一条从句里「好质量 + 慢物流」互相抵消。"""
    low = clause.lower()
    idx = low.find(keyword.lower())
    if idx < 0:
        window = low
    else:
        start = max(0, idx - 15)
        end = min(len(low), idx + len(keyword) + 15)
        window = low[start:end]
    neg = sum(1 for w in NEG_WORDS if w in window)
    pos = sum(1 for w in POS_WORDS if w in window)
    if neg > pos:
        return 0  # negative
    if pos > neg:
        return 2  # positive
    return 1     # neutral


def _appeal_noul(clause):
    low = clause.lower()
    if any(w in low for w in EXPLICIT_APPEAL):
        return 0.9
    if any(w in low for w in SUGGEST_APPEAL):
        return 0.5
    return 0.1


def analyze_review(review):
    """单条评价 -> 聚合后的结构化判断（按 aspect）。"""
    cleaned = clean_review(review["text"])
    clauses = _split_clauses(cleaned)
    # 收集 (aspect, polarity, appeal)：极性在每个 aspect 命中的局部窗口内独立判定
    rows = []
    for clause in clauses:
        aspects = _detect_aspects(clause)
        ap = _appeal_noul(clause)
        for a in aspects:
            # 取该 aspect 的第一个命中关键词作为窗口中心
            kw = next((k for k in ASPECT_KEYWORDS.get(a, []) if k.lower() in clause.lower()), "")
            pol = _polarity_window(clause, kw)
            rows.append({"aspect": a, "polarity": pol, "appeal": ap, "clause": clause})
    # 按 aspect 聚合：多数极性 + 最大诉求度
    by_aspect = {}
    for r in rows:
        by_aspect.setdefault(r["aspect"], []).append(r)
    judgments = []
    for aspect, group in by_aspect.items():
        pols = [g["polarity"] for g in group]
        # 多数票（平票取较高极性，倾向不漏负向）
        majority = max(set(pols), key=lambda p: (pols.count(p), p))
        appeal = max(g["appeal"] for g in group)
        judgments.append({
            "aspect": aspect,
            "polarity": majority,
            "polarity_label": {0: "negative", 1: "neutral", 2: "positive"}[majority],
            "appeal": appeal,
            "actionable": appeal >= 0.8,
            "clauses": [g["clause"] for g in group],
        })
    judgments.sort(key=lambda j: (-j["appeal"], j["aspect"]))
    return {
        "id": review["id"],
        "lang": review.get("lang", "?"),
        "cleaned": cleaned,
        "clause_count": len(clauses),
        "judgments": judgments,
    }


def load_reviews(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["reviews"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--data", default=os.path.join(HERE, "reviews.json"))
    args = parser.parse_args()

    if args.self_test:
        return _self_test(args.data)

    reviews = load_reviews(args.data)
    print("=" * 70)
    print("之五 数据集跑批（mock 模型：确定性关键词启发式，替代真实 Laya checkpoint）")
    print("=" * 70)
    for rv in reviews:
        res = analyze_review(rv)
        print(f"\n[{res['id']}] lang={res['lang']}  清洗后({res['clause_count']}从句): {res['cleaned'][:60]}…")
        for j in res["judgments"]:
            flag = " [诉求!]" if j["actionable"] else ""
            print(f"    - {j['aspect']:<4} polarity={j['polarity_label']:<8} appeal={j['appeal']:.1f}{flag}")
    return 0


def _self_test(data_path):
    reviews = load_reviews(data_path)
    by_id = {r["id"]: r for r in reviews}

    # R03：含明确诉求（修复导出 / 否则退订）-> 至少一条 judgment 的 actionable=True
    r03 = analyze_review(by_id["R03"])
    assert any(j["actionable"] for j in r03["judgments"]), r03["judgments"]
    print("[PASS] R03 含有可执行诉求被标记为 actionable")

    # R03：命中 价格/客服/稳定性 至少一个
    aspects03 = {j["aspect"] for j in r03["judgments"]}
    assert aspects03 & {"价格", "客服", "稳定性"}, aspects03
    print("[PASS] R03 正确识别到 价格/客服/稳定性 维度")

    # R02：纯好评、无明确诉求 -> 不应有 actionable
    r02 = analyze_review(by_id["R02"])
    assert not any(j["actionable"] for j in r02["judgments"]), r02["judgments"]
    # R02 至少含 物流/客服/包装 的正向
    assert any(j["polarity"] == 2 for j in r02["judgments"]), r02["judgments"]
    print("[PASS] R02 纯好评无诉求，极性为正向")

    # 多 aspect 拆分：R03 应被拆成 >=3 个从句（连词/句末拆分）
    assert r03["clause_count"] >= 3, r03
    print("[PASS] R03 被拆成多条原子从句（多维度并行判断）")

    # R10：含功能建议（希望增加本地仓）-> appeal 偏高
    r10 = analyze_review(by_id["R10"])
    assert any(j["appeal"] >= 0.5 for j in r10["judgments"]), r10["judgments"]
    print("[PASS] R10 功能建议被判为中等诉求度")

    # 清洗管线联动：默认好评噪声行在 R 系列之外不影响，这里单独验证 R 不经噪声
    # 全量 10 条都能产出至少 1 条 judgment
    for rv in reviews:
        res = analyze_review(rv)
        assert len(res["judgments"]) >= 1, res
    print("[PASS] 全量 10 条评价均产出结构化判断")

    print("\nself-test PASS: 全部 6 项断言通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
