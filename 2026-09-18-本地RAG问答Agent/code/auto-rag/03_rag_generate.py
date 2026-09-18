#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""#26 本地 RAG 问答 Agent —— 生成层（对「答案责任」建模错）可复现脚本。

复现一个真实坑：
  ⑥ 幻觉编造引用：模型把没检索到的内容，配上一段看起来合理的「引用」喂给用户。
     本脚本给出两道防线——引文合法性 + 引文与答案的关键词重叠——把编造挡在输出前。

运行：python3 03_rag_generate.py --self-test
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rag_core import tokenize  # noqa: E402


class UngroundedClaim(Exception):
    """答案出现了检索结果无法支撑的引用。"""


def extract_citations(answer: str):
    return [int(m) for m in re.findall(r"\[@(\d+)\]", answer)]


def citation_grounding(answer: str, retrieved_indices):
    """第一道防线：答案里 [@k] 引用的片段必须都在本次检索结果中。"""
    cited = extract_citations(answer)
    bad = [c for c in cited if c not in retrieved_indices]
    if bad:
        raise UngroundedClaim(f"引用了未检索到的片段: {bad}")
    return True


def token_grounding(answer: str, records_by_index: dict):
    """第二道防线：被引用的片段文本必须和答案有共同关键词，否则算凭空编造。"""
    cited = extract_citations(answer)
    claim_tokens = set(tokenize(answer))
    for c in cited:
        rec_text = records_by_index.get(c, "")
        rec_tokens = set(tokenize(rec_text))
        if not (claim_tokens & rec_tokens):
            raise UngroundedClaim(f"片段[{c}]与答案无关键词重叠, 疑似编造")
    return True


def guard(answer: str, retrieved_indices, records_by_index: dict):
    """组合两道防线；任一不过即判定幻觉。"""
    citation_grounding(answer, retrieved_indices)
    token_grounding(answer, records_by_index)
    return True


def test_faithful_answer_passes():
    """好路径：答案只引用检索到的、且包含答案关键词的片段。"""
    recs = {1: "七天无理由退款", 2: "运费由买家承担"}
    ans = "七天无理由退款, 运费由买家承担[@1][@2]"
    assert guard(ans, {1, 2}, recs) is True
    print("[1] 忠实答案：引用合法且有关键词重叠 -> 通过 -> OK")


def test_fabricated_citation_caught():
    """坑⑥：模型编造了没检索到的 [@9]，第一道防线应拦截。"""
    recs = {1: "七天无理由退款"}
    ans = "支持三十天超长退款[@9]"  # [@9] 根本不在检索结果
    caught = False
    try:
        guard(ans, {1}, recs)
    except UngroundedClaim:
        caught = True
    assert caught, "编造引用未被拦截"
    print("[2] 幻觉编造引用：[@9] 未检索到, 第一道防线拦截 -> OK")


def test_irrelevant_citation_caught():
    """坑⑥变体：引用了检索到的片段, 但该片段并不支撑答案 => 仍判编造。

    模型说「运费由商家承担」却错误引用了「客服处理退款申请」那段（根本没提运费），
    两段关键词完全不重叠，第二道防线应拦截。
    """
    recs = {1: "生鲜类不支持退款", 2: "客服会在两个工作日内处理退款申请"}
    ans = "运费由商家承担[@2]"  # [@2] 是退款处理条款, 与「运费」毫无关系
    caught = False
    try:
        guard(ans, {1, 2}, recs)
    except UngroundedClaim:
        caught = True
    assert caught, "无关引用未被拦截"
    print("[3] 无关引用：片段在检索中但关键词零重叠, 第二道防线拦截 -> OK")


def test_unguarded_slip():
    """对照：不做防护时, 编造引用会原样进入答案（这正是翻车的根因）。"""
    recs = {1: "七天无理由退款"}
    ans = "支持三十天超长退款[@9]"
    # 朴素管线只管把答案吐出去
    naive_out = ans
    fabricated = "[@9]" in naive_out and 9 not in recs
    assert fabricated, "无防护时编造引用直接漏出"
    print("[4] 无防护对照：编造引用原样漏出 -> OK（说明防护必要）")


def run_selftest():
    test_faithful_answer_passes()
    test_fabricated_citation_caught()
    test_irrelevant_citation_caught()
    test_unguarded_slip()
    print("ALL_SELFTESTS_PASSED")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        run_selftest()
    else:
        print("usage: python3 03_rag_generate.py --self-test")
