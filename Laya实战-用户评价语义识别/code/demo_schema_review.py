#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
demo_schema_review.py —— 把「评价语义分析」JSON Schema 编译成 Laya 三原语。

本脚本是 Laya structured.py 编译漏斗的免依赖最小复现，用来演示：
    aspect   -> Choice  （预先枚举的维度，输出空间枚举）
    polarity -> Score   （整数刻度 0~2，span<=10）
    appeal   -> Noul    （连续值 0~1，不确定即升级）
以及编译期对「自由文本/数组/对象/$ref」的拒绝。

与 Laya 源码的对应关系（一手来源 convaiinnovations/laya @ 4066d5d）：
    plan_from_json_schema : 顶层 32 属性上限、遍历 properties
    _field                : const/enum/type/anyOf 分派
    _enum_field           : 全布尔退化 -> noul；否则 -> choice
    _score_field          : 整数刻度 span<=10
    _project              : 反向映射回原始枚举值

运行：
    python3 demo_schema_review.py --self-test
    python3 demo_schema_review.py
"""
import sys
import json
import argparse

MAX_TOP_LEVEL_PROPS = 32          # 与 Laya plan_from_json_schema 顶层上限一致
MAX_SCORE_SPAN = 10               # 与 Laya _score_field 的 span<=10 一致


def _is_all_boolean(values):
    return all(isinstance(v, bool) for v in values)


def _score_field(name, prop):
    """整数刻度 -> Score 原语。span 必须 <= 10。"""
    if prop.get("type") != "integer":
        raise ValueError(f"{name}: score field must be integer")
    lo = prop.get("minimum")
    hi = prop.get("maximum")
    if lo is None or hi is None:
        raise ValueError(f"{name}: score field needs minimum/maximum")
    span = hi - lo + 1
    if span > MAX_SCORE_SPAN:
        raise ValueError(f"{name}: score span {span} > {MAX_SCORE_SPAN}")
    return {
        "name": name,
        "primitive": "score",
        "minimum": lo,
        "maximum": hi,
        "span": span,
        # Score 原语在 Laya 里输出整数刻度，再由 _project 映射回语义标签
        "legend": _default_legend(lo, hi),
    }


def _default_legend(lo, hi):
    # polarity 约定 0=负 1=中 2=正（可落档间）
    if lo == 0 and hi == 2:
        return {0: "negative", 1: "neutral", 2: "positive"}
    return {i: str(i) for i in range(lo, hi + 1)}


def _enum_field(name, prop):
    """枚举 -> Choice，或全布尔时退化成 Noul。"""
    values = prop.get("enum")
    if values is None:
        raise ValueError(f"{name}: enum field needs enum list")
    if _is_all_boolean(values):
        # 全布尔 -> Laya 把「是否」当作连续不确定度，退化成 Noul
        return {
            "name": name,
            "primitive": "noul",
            "minimum": 0.0,
            "maximum": 1.0,
            "note": "all-boolean enum collapses to continuous noul",
        }
    return {
        "name": name,
        "primitive": "choice",
        "options": list(values),
        "project": {str(v): v for v in values},  # 反向映射回原始枚举值
    }


def _field(name, prop):
    """_field 分派：const / enum / type / anyOf。"""
    if "const" in prop:
        single = prop["const"]
        return _enum_field(name, {"enum": [single]})
    if "enum" in prop:
        return _enum_field(name, prop)
    if prop.get("type") == "integer":
        return _score_field(name, prop)
    if prop.get("type") == "number":
        # 连续数值 -> Noul 原语（输出 token 免费、不确定即升级）
        return {
            "name": name,
            "primitive": "noul",
            "minimum": prop.get("minimum", 0.0),
            "maximum": prop.get("maximum", 1.0),
        }
    # 自由文本 / 数组 / 对象 / $ref：Laya 在编译期直接拒绝
    if prop.get("type") in ("string", "array", "object") or "$ref" in prop:
        raise ValueError(f"{name}: free {prop.get('type', '$ref')} is rejected at compile time")
    raise ValueError(f"{name}: unsupported property spec")


def plan_from_json_schema(schema):
    """顶层编译漏斗：遍历 properties，逐一编译成三原语。"""
    props = schema.get("properties", {})
    if len(props) > MAX_TOP_LEVEL_PROPS:
        raise ValueError(f"too many top-level props: {len(props)} > {MAX_TOP_LEVEL_PROPS}")
    plan = {}
    for name, prop in props.items():
        plan[name] = _field(name, prop)
    return plan


# 评价语义分析 Schema：一份真实的、可被 Laya 编译的契约
REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "aspect": {
            "type": "string",
            "enum": ["物流", "客服", "价格", "稳定性", "界面", "质量", "包装", "学习", "功能", "其他"],
        },
        "polarity": {
            "type": "integer",
            "minimum": 0,
            "maximum": 2,
        },
        "appeal": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
    },
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    plan = plan_from_json_schema(REVIEW_SCHEMA)
    print("评价语义分析 Schema 编译结果（三原语）：")
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


def _self_test():
    # 1) 正常编译：aspect->choice, polarity->score, appeal->noul
    plan = plan_from_json_schema(REVIEW_SCHEMA)
    assert plan["aspect"]["primitive"] == "choice", plan["aspect"]
    assert plan["aspect"]["options"] == ["物流", "客服", "价格", "稳定性", "界面", "质量", "包装", "学习", "功能", "其他"]
    assert plan["polarity"]["primitive"] == "score"
    assert plan["polarity"]["span"] == 3 and plan["polarity"]["legend"][2] == "positive"
    assert plan["appeal"]["primitive"] == "noul"
    print("[PASS] 三原语编译：aspect=choice / polarity=score / appeal=noul")

    # 2) 全布尔枚举退化成 noul
    bool_plan = plan_from_json_schema({
        "type": "object",
        "properties": {
            "is_vuln": {"type": "boolean", "enum": [True, False]},
        },
    })
    assert bool_plan["is_vuln"]["primitive"] == "noul", bool_plan["is_vuln"]
    print("[PASS] 全布尔枚举 -> noul 退化")

    # 3) 自由文本在编译期被拒绝
    try:
        plan_from_json_schema({
            "type": "object",
            "properties": {"comment": {"type": "string"}},
        })
        raise AssertionError("free string should be rejected")
    except ValueError as e:
        assert "rejected" in str(e), str(e)
    print("[PASS] 自由文本字段编译期拒绝")

    # 4) 整数刻度 span 超限被拒绝
    try:
        plan_from_json_schema({
            "type": "object",
            "properties": {"rank": {"type": "integer", "minimum": 0, "maximum": 20}},
        })
        raise AssertionError("score span>10 should be rejected")
    except ValueError as e:
        assert "span" in str(e), str(e)
    print("[PASS] Score 刻度 span>10 编译期拒绝")

    # 5) 顶层属性数超限被拒绝
    try:
        plan_from_json_schema({
            "type": "object",
            "properties": {f"k{i}": {"type": "integer", "minimum": 0, "maximum": 1} for i in range(33)},
        })
        raise AssertionError("33 props should be rejected")
    except ValueError as e:
        assert "too many" in str(e), str(e)
    print("[PASS] 顶层 32 属性上限拒绝")

    print("\nself-test PASS: 全部 5 项断言通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
