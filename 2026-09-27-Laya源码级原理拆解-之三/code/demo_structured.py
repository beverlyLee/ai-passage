#!/usr/bin/env python3
"""demo_structured.py — 复刻 laya/structured.py 的「schema -> 三原语」编译与投影。

纯标准库，不依赖 torch / numpy / laya。核心逻辑逐函数对齐源码：
_enum_field / _noul_field / _score_field / _field / plan_from_json_schema /
_project / decide。运行 `python demo_structured.py --self-test` 自检全绿，
标准输出即正文里引用的「预期输出」。

一手来源：/tmp/laya-src/laya/structured.py（MIT，NandhaKishorM/laya）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

MAX_PROPERTIES = 32
MAX_OPTIONS = 32
MAX_SCORE_LEVELS = 10


class SchemaError(ValueError):
    """A schema cannot be expressed as Laya questions; the message names the path."""


@dataclass
class _Field:
    name: str
    kind: str                      # "choice" | "score" | "noul"
    question: Dict[str, Any]
    options: List[Tuple[str, Any]] = field(default_factory=list)   # choice: (label, value)
    minimum: Optional[int] = None                                 # score: level 0 value


def _enum_field(path: str, name: str, values: Sequence[Any],
                description: Optional[str]) -> _Field:
    if len(values) > MAX_OPTIONS:
        raise SchemaError("%s: %d options exceeds MAX_OPTIONS=%d" % (path, len(values), MAX_OPTIONS))
    if not values:
        raise SchemaError("%s: 'enum' must not be empty" % path)
    if all(isinstance(v, bool) for v in values):
        return _noul_field(path, name, description)
    options = [(("null" if v is None else str(v)), v) for v in values]
    if len({label for label, _ in options}) != len(options):
        raise SchemaError("%s: enum values produce duplicate choice labels" % path)
    criteria = {label: None for label, _ in options}
    question = {
        "type": "choice",
        "instructions": description or ("What is `%s`?" % name),
        "criteria": criteria,
    }
    return _Field(name=name, kind="choice", question=question, options=options)


def _noul_field(path: str, name: str, description: Optional[str]) -> _Field:
    question = {
        "type": "noul",
        "instructions": description or ("Is `%s` true?" % name),
    }
    return _Field(name=name, kind="noul", question=question)


def _score_field(path: str, name: str, prop: Dict[str, Any],
                 description: Optional[str]) -> _Field:
    lo, hi = prop.get("minimum"), prop.get("maximum")
    if not isinstance(lo, int) or not isinstance(hi, int):
        raise SchemaError(
            "%s: a numeric field needs integer 'minimum' and 'maximum' to become a score" % path)
    if hi < lo:
        raise SchemaError("%s: 'maximum' %d is below 'minimum' %d" % (path, hi, lo))
    span = hi - lo + 1
    if span > MAX_SCORE_LEVELS:
        raise SchemaError(
            "%s: %d levels exceeds MAX_SCORE_LEVELS=%d; narrow the range or use an enum"
            % (path, span, MAX_SCORE_LEVELS))
    question = {
        "type": "score",
        "instructions": description or ("Score `%s` from %d to %d" % (name, lo, hi)),
        "criteria": [str(v) for v in range(lo, hi + 1)],
    }
    return _Field(name=name, kind="score", question=question, minimum=lo)


def _field(path: str, name: str, prop: Dict[str, Any]) -> _Field:
    if not isinstance(prop, dict):
        raise SchemaError("%s: property must be an object, got %s" % (path, type(prop).__name__))
    description = prop.get("description")
    if not ({"const", "enum", "type"} & set(prop)):
        union = prop.get("anyOf") or prop.get("oneOf")
        if union is not None:
            branches = [b for b in union if isinstance(b, dict) and b.get("type") != "null"]
            if len(branches) != 1:
                raise SchemaError(
                    "%s: only 'Optional[...]' unions (one non-null branch) are supported, got %d"
                    % (path, len(branches)))
            branch = dict(branches[0])
            branch.setdefault("description", description)
            return _field(path, name, branch)
    if "const" in prop:
        return _enum_field(path, name, [prop["const"]], description)
    if "enum" in prop:
        return _enum_field(path, name, prop["enum"], description)
    jtype = prop.get("type")
    if isinstance(jtype, list):                # nullable: ["string", "null"]
        non_null_types = [t for t in jtype if t != "null"]
        if len(non_null_types) > 1:
            raise SchemaError("%s: 'type' has multiple non-null types; unions are not supported" % path)
        jtype = non_null_types[0] if non_null_types else None
    if jtype == "boolean":
        return _noul_field(path, name, description)
    if jtype == "string":
        raise SchemaError(
            "%s: a free string cannot be a fixed option set; use 'enum' or a boolean" % path)
    if jtype in ("integer", "number"):
        return _score_field(path, name, prop, description)
    if jtype == "array":
        raise SchemaError("%s: arrays are not supported; ask one field per element" % path)
    if jtype == "object":
        raise SchemaError("%s: nested objects are not supported; flatten the schema" % path)
    if "$ref" in prop:
        raise SchemaError("%s: $ref/recursion is not supported; flatten the schema" % path)
    raise SchemaError("%s: unsupported schema %r" % (path, prop))


def plan_from_json_schema(schema: Dict[str, Any]) -> List[_Field]:
    if not isinstance(schema, dict):
        raise SchemaError("expected a JSON schema object, got %s" % type(schema).__name__)
    if schema.get("type") not in (None, "object") or "properties" not in schema:
        raise SchemaError("the top level must be an object with 'properties'")
    properties = schema["properties"]
    if not isinstance(properties, dict) or not properties:
        raise SchemaError("'properties' must be a non-empty object")
    if len(properties) > MAX_PROPERTIES:
        raise SchemaError("%d properties exceeds MAX_PROPERTIES=%d" % (len(properties), MAX_PROPERTIES))
    return [_field("properties.%s" % name, name, prop) for name, prop in properties.items()]


def questions_from_json_schema(schema: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {f.name: f.question for f in plan_from_json_schema(schema)}


def _project(answers: Dict[str, Any], fields: Sequence[_Field]) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    for f in fields:
        answer = answers.get(f.name)
        if answer is None:
            continue
        if f.kind == "noul":
            values[f.name] = bool(float(answer.get("noul", 0.0)) >= 0.5)
        elif f.kind == "score":
            probs = answer.get("probabilities") or {}
            if probs:
                idx = max(range(len(probs)), key=lambda i: float(probs.get(str(i), probs.get(i, 0.0))))
            else:
                idx = int(round(float(answer.get("score", 0.0)))) - int(f.minimum or 0)
            values[f.name] = int(f.minimum or 0) + idx
        else:  # choice
            label = str(answer.get("choice"))
            values[f.name] = next((value for lbl, value in f.options if lbl == label), label)
    return values


class FakeRunner:
    """一个确定性的假 runner：predict 直接吐出预先写好的答案，省掉模型前向。"""

    def __init__(self, answers: Dict[str, Any]):
        self.answers = answers

    def predict(self, state, questions, **kw):
        return {"answers": self.answers, "usage": {"input_tokens": 0, "output_tokens": 0}}


def decide(runner, state, schema=None, *, questions=None, return_details=False):
    if (schema is None) == (questions is None):
        raise ValueError("pass exactly one of schema= or questions=")
    fields = None
    if schema is not None:
        fields = plan_from_json_schema(schema)
        questions = {f.name: f.question for f in fields}
    result = runner.predict(state, questions)
    answers = result.get("answers", {}) or {}
    values = _project(answers, fields) if fields is not None else dict(answers)
    return values


# ----------------------------------------------------------------------------
# 演示用的邮件分诊 schema：和 laya/presets.py 的 email_questions 同款三原语结构
# ----------------------------------------------------------------------------
EMAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "enum": ["billing", "technical", "sales", "security", "hr", "other"],
            "description": "Which team should handle the email in `body`?",
        },
        "is_spam": {"type": "boolean"},
        "is_phishing": {"type": "boolean"},
        "urgency": {"type": "integer", "minimum": 0, "maximum": 2},
        "needs_reply": {"type": "boolean"},
    },
}

# 假 runner 的确定性答案：category->technical，urgency 概率 argmax 落第 1 档
EMAIL_ANSWERS = {
    "category": {"type": "choice", "choice": "technical", "confidence": 0.92,
                 "probabilities": {"billing": 0.01, "technical": 0.92, "sales": 0.02,
                                   "security": 0.01, "hr": 0.01, "other": 0.03}},
    "is_spam": {"type": "noul", "noul": 0.05, "confidence": 0.88},
    "is_phishing": {"type": "noul", "noul": 0.90, "confidence": 0.95},
    "urgency": {"type": "score", "score": 1.0, "probabilities": {"0": 0.1, "1": 0.7, "2": 0.2},
                "confidence": 0.80, "legend": ["no time pressure", "needs attention soon",
                                               "blocking issue or hard deadline"]},
    "needs_reply": {"type": "noul", "noul": 0.95, "confidence": 0.97},
}


def _demo():
    print("=== schema -> 三原语 编译 ===")
    questions = questions_from_json_schema(EMAIL_SCHEMA)
    for name, q in questions.items():
        if q["type"] == "choice":
            opts = list(q["criteria"].keys())
            print("  %-12s choice  (%d options)  %s" % (name, len(opts), q["instructions"]))
            print("               criteria = %s" % opts)
        elif q["type"] == "score":
            print("  %-12s score   (levels %s)  %s" % (name, q["criteria"], q["instructions"]))
        else:
            print("  %-12s noul     %s" % (name, q["instructions"]))

    print()
    print("=== decide() 投影回 schema 值 ===")
    values = decide(FakeRunner(EMAIL_ANSWERS), state={"subject": "x", "body": "x"}, schema=EMAIL_SCHEMA)
    for k, v in values.items():
        print("  %-12s = %r" % (k, v))

    print()
    print("=== Optional[Literal[...]] 解包（源码 _field 的 anyOf 分支）===")
    opt_schema = {"type": "object", "properties": {
        "tier": {"anyOf": [{"enum": ["free", "pro", "team"]}, {"type": "null"}]}}}
    print("  tier: Optional[Literal[free,pro,team]] ->",
          questions_from_json_schema(opt_schema)["tier"]["type"])

    print()
    print("=== 被拒的 schema（free string / array / object / $ref）===")
    for bad in [
        ("free string", {"type": "object", "properties": {"note": {"type": "string"}}}),
        ("array", {"type": "object", "properties": {"tags": {"type": "array"}}}),
        ("nested object", {"type": "object", "properties": {"addr": {"type": "object"}}}),
        ("$ref", {"type": "object", "properties": {"x": {"$ref": "#/defs/X"}}}),
    ]:
        label, sc = bad
        try:
            questions_from_json_schema(sc)
            print("  %-14s -> 意外通过（应被拒）" % label)
        except SchemaError as e:
            print("  %-14s -> 拒: %s" % (label, str(e).split(":")[0]))


def _self_test():
    # 1) 编译出的三原语数量与类型
    q = questions_from_json_schema(EMAIL_SCHEMA)
    assert q["category"]["type"] == "choice" and len(q["category"]["criteria"]) == 6
    assert q["urgency"]["type"] == "score" and q["urgency"]["criteria"] == ["0", "1", "2"]
    assert q["is_spam"]["type"] == "noul"
    # 2) 投影结果逐字段核对
    v = decide(FakeRunner(EMAIL_ANSWERS), state={}, schema=EMAIL_SCHEMA)
    assert v == {"category": "technical", "is_spam": False, "is_phishing": True,
                 "urgency": 1, "needs_reply": True}, v
    # 3) 全 bool enum -> noul
    assert questions_from_json_schema(
        {"type": "object", "properties": {"ok": {"enum": [True, False]}}})["ok"]["type"] == "noul"
    # 4) Optional[Literal] 解包为 choice
    assert questions_from_json_schema(
        {"type": "object", "properties": {"t": {"anyOf": [{"enum": ["a", "b"]}, {"type": "null"}]}}})
    # 5) reject 四类非法属性
    for sc in [
        {"type": "object", "properties": {"note": {"type": "string"}}},
        {"type": "object", "properties": {"tags": {"type": "array"}}},
        {"type": "object", "properties": {"addr": {"type": "object"}}},
        {"type": "object", "properties": {"x": {"$ref": "#/X"}}},
    ]:
        try:
            questions_from_json_schema(sc)
            raise AssertionError("should reject %r" % sc)
        except SchemaError:
            pass
    # 6) score 跨度超限
    try:
        questions_from_json_schema(
            {"type": "object", "properties": {"s": {"type": "integer", "minimum": 0, "maximum": 15}}})
        raise AssertionError("score span > 10 should reject")
    except SchemaError:
        pass
    print("self-test PASS: 编译/投影/解包/拒绝 全部符合预期")


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        _self_test()
    else:
        _demo()
