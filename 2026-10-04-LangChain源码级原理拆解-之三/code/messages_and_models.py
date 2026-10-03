#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""之三配套复现脚本：LangChain 消息族与模型层输入归一。

纯标准库实现，不依赖 langchain-core，也不需要任何 API key。
复刻的是 langchain-core 1.3.2 里四个关键机制：

1. 消息族（BaseMessage / AIMessage / ToolMessage）与 content_blocks 双入口
2. _convert_to_message：字符串 / 二元组 / 字典三种形状归一成消息对象
3. add_ai_message_chunks：流式分片按字段合并（文本拼接、tool_call 按 index 拼、usage 相加）
4. _convert_input：模型层把 str 与消息列表分别包成 StringPromptValue 与 ChatPromptValue

运行：
    python messages_and_models.py            # 端到端演示
    python messages_and_models.py --self-test  # 自检
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Sequence

# ============================================================
# 一、消息族：对应 langchain_core/messages/base.py:93 与 ai.py:160
# ============================================================


class BaseMessage:
    """消息基类。六个字段是 LangChain 消息的全部公共面。

    对应 base.py:93-144：
      content            正文，str 或 list[str | dict]（多模态）
      additional_kwargs  供应商私有负载
      response_metadata  响应头 / logprobs / 模型名等
      type               反序列化用的判别字段
      name               可选的说话人名字
      id                 消息唯一标识
    """

    type: str = "base"

    def __init__(
        self,
        content: str | list[str | dict] | None = None,
        content_blocks: list[dict] | None = None,
        **kwargs: Any,
    ) -> None:
        # base.py:176-179，两个入口最终都落到 content 字段
        if content_blocks is not None:
            super().__setattr__("content", content_blocks)
        else:
            super().__setattr__("content", content)
        self.additional_kwargs: dict = kwargs.pop("additional_kwargs", None) or {}
        self.response_metadata: dict = kwargs.pop("response_metadata", None) or {}
        self.name: str | None = kwargs.pop("name", None)
        self.id: str | None = kwargs.pop("id", None)
        for key, value in kwargs.items():
            setattr(self, key, value)

    @property
    def text(self) -> str:
        """只取纯文本部分。base.py:263 的 text 属性在多模态下会跳过非文本块。"""
        content = getattr(self, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        return ""

    def __repr__(self) -> str:
        return f"{type(self).__name__}(type={self.type!r}, content={self.text!r})"


class HumanMessage(BaseMessage):
    type = "human"


class SystemMessage(BaseMessage):
    type = "system"


class AIMessage(BaseMessage):
    """模型输出。ai.py:160-183 比基类多三个字段。"""

    type = "ai"

    def __init__(self, content=None, content_blocks=None, **kwargs: Any) -> None:
        # ai.py:215-226，content_blocks 里若含 tool_call 块会自动抬升成 tool_calls
        if content_blocks is not None:
            blocks = [b for b in content_blocks if b.get("type") == "tool_call"]
            if blocks and "tool_calls" not in kwargs:
                kwargs["tool_calls"] = blocks
        super().__init__(content=content, content_blocks=content_blocks, **kwargs)
        self.tool_calls: list[dict] = kwargs.get("tool_calls") or []
        self.invalid_tool_calls: list[dict] = kwargs.get("invalid_tool_calls") or []
        self.usage_metadata: dict | None = kwargs.get("usage_metadata")


class ToolMessage(BaseMessage):
    """工具执行结果。tool.py:26 起，关键是 tool_call_id 必填。"""

    type = "tool"

    def __init__(self, content=None, **kwargs: Any) -> None:
        super().__init__(content=content, **kwargs)
        # tool.py:67，required 字段，LangSmith 里靠它把结果和请求配对
        self.tool_call_id: str = kwargs["tool_call_id"]
        # tool.py:82，默认 success，工具报错时要显式改
        self.status: str = kwargs.get("status", "success")
        self.name: str | None = kwargs.get("name")


# ============================================================
# 二、输入归一：对应 messages/utils.py:675 的 _convert_to_message
# ============================================================

_ROLE_TO_CLASS = {
    "human": HumanMessage,
    "system": SystemMessage,
    "ai": AIMessage,
    "tool": ToolMessage,
}


def _create_message_from_message_type(msg_type: str, content: Any, **kwargs: Any) -> BaseMessage:
    """utils.py 里的同名内部函数，按 role 字符串取类并实例化。"""
    if msg_type not in _ROLE_TO_CLASS:
        raise ValueError(f"Unknown message type: {msg_type}")
    return _ROLE_TO_CLASS[msg_type](content, **kwargs)


def _convert_to_message(message: Any) -> BaseMessage:
    """把四种输入形状归一成消息对象。对应 utils.py:675-732。

    1. BaseMessage 实例     原样返回
    2. 字符串               视为 ('human', 字符串)
    3. 二元组 (role, 模板)  按 role 取类
    4. 字典                 取 role 或 type，再取 content
    """
    if isinstance(message, BaseMessage):
        return message

    if isinstance(message, (str, Sequence)) and not isinstance(message, dict):
        if isinstance(message, str):
            # utils.py:701，裸字符串默认当 human
            return _create_message_from_message_type("human", message)
        try:
            msg_type, template = message
        except ValueError as exc:
            raise NotImplementedError(
                "Message as a sequence must be (role string, template)"
            ) from exc
        return _create_message_from_message_type(msg_type, template)

    if isinstance(message, dict):
        msg_kwargs = dict(message)
        try:
            # utils.py:713-715，role 与 type 二选一，先试 role
            msg_type = msg_kwargs.pop("role", None) or msg_kwargs.pop("type", None)
            # utils.py:717，content 为 None 时兜成空串，不报错
            msg_content = msg_kwargs.pop("content", None) or ""
        except KeyError as exc:
            raise ValueError(
                f"Message dict must contain 'role' and 'content' keys, got {message}"
            ) from exc
        if msg_type is None:
            raise ValueError(
                f"Message dict must contain 'role' and 'content' keys, got {message}"
            )
        return _create_message_from_message_type(msg_type, msg_content, **msg_kwargs)

    raise NotImplementedError(f"Unsupported message type: {type(message)}")


def convert_to_messages(messages: Iterable[Any]) -> list[BaseMessage]:
    """utils.py:735，逐个过 _convert_to_message。"""
    return [_convert_to_message(m) for m in messages]


# ============================================================
# 三、流式合并：对应 messages/base.py:366 与 ai.py:638
# ============================================================


def merge_content(first_content: Any, *contents: Any) -> Any:
    """base.py:366-406，content 的合并规则是一组分类型分派。

    分派顺序不能乱：
      累积值是 str + 新值是 str   直接字符串相加
      累积值是 str + 新值是 list  把 str 塞成 list 的第一个元素
      累积值是 list + 新值是 list merge_lists 按 index 合
      累积值是 list + 末元素是 str  追加到末元素，避免碎片堆积
    """
    merged: Any = "" if first_content is None else first_content

    for content in contents:
        if isinstance(merged, str):
            if isinstance(content, str):
                merged += content
            else:
                merged = [merged, *content]
        elif isinstance(content, list):
            merged = _merge_lists(merged, content)
        elif merged and isinstance(merged[-1], str):
            merged[-1] += content
        elif content == "":
            pass
        elif merged:
            merged.append(content)
    return merged


def _merge_lists(left: list, right: list) -> list:
    """按 dict 的 index 键合并，流式场景下 index 是唯一可靠的关联依据。"""
    merged = list(left)
    for item in right:
        if isinstance(item, dict) and isinstance(merged, list):
            index = item.get("index")
            if index is None:
                merged.append(item)
                continue
            for pos, existing in enumerate(merged):
                if isinstance(existing, dict) and existing.get("index") == index:
                    merged[pos] = _merge_dict_by_index(existing, item)
                    break
            else:
                merged.append(item)
        else:
            merged.append(item)
    return merged


def _merge_dict_by_index(left: dict, right: dict) -> dict:
    out = dict(left)
    for key, value in right.items():
        if isinstance(value, str) and isinstance(out.get(key), str):
            out[key] = out[key] + value
        else:
            out[key] = value
    return out


def _merge_dicts(left: dict, right: dict) -> dict:
    out = dict(left)
    for key, value in right.items():
        if isinstance(value, str) and isinstance(out.get(key), str):
            out[key] = out[key] + value
        else:
            out[key] = value
    return out


def add_usage(left: dict | None, right: dict | None) -> dict | None:
    """ai.py:721，token 计数逐字段相加，details 里的细分项也要加。"""
    if left is None and right is None:
        return None
    out = dict(left or {})
    for key, value in (right or {}).items():
        if key.endswith("_details") and isinstance(value, dict):
            base = dict(out.get(key) or {})
            for sub_key, sub_value in value.items():
                base[sub_key] = base.get(sub_key, 0) + sub_value
            out[key] = base
        else:
            out[key] = out.get(key, 0) + value
    return out


class AIMessageChunk(AIMessage):
    """流式分片。ai.py:413，同时继承 AIMessage 与 BaseMessageChunk。"""

    def __init__(self, content=None, **kwargs: Any) -> None:
        super().__init__(content=content, **kwargs)
        self.tool_call_chunks: list[dict] = kwargs.get("tool_call_chunks") or []
        self.chunk_position: str | None = kwargs.get("chunk_position")

    def __add__(self, other: "AIMessageChunk") -> "AIMessageChunk":
        return add_ai_message_chunks(self, other)


def add_ai_message_chunks(left: AIMessageChunk, *others: AIMessageChunk) -> AIMessageChunk:
    """ai.py:638-718，把多个分片合成一个。

    五件事各归各管：
      content             走 merge_content
      additional_kwargs   字符串字段拼接
      response_metadata   字符串字段拼接
      tool_call_chunks    走 merge_lists，按 index 配对
      usage_metadata      走 add_usage，数值相加（不是拼接）
    """
    content = merge_content(left.content, *(o.content for o in others))
    additional_kwargs = _merge_dicts(
        left.additional_kwargs, *[o.additional_kwargs for o in others]
    ) if others else dict(left.additional_kwargs)
    response_metadata = _merge_dicts(
        left.response_metadata, *[o.response_metadata for o in others]
    ) if others else dict(left.response_metadata)

    # 起点必须是 left 自身的分片，ai.py:660 是 merge_lists(left.tool_call_chunks, *others)
    tool_call_chunks: list[dict] = list(left.tool_call_chunks)
    for other in others:
        tool_call_chunks = _merge_lists(tool_call_chunks, other.tool_call_chunks)

    usage_metadata = left.usage_metadata
    for other in others:
        usage_metadata = add_usage(usage_metadata, other.usage_metadata)

    chunk_position = "last" if any(
        x.chunk_position == "last" for x in [left, *others]
    ) else None

    return AIMessageChunk(
        content=content,
        additional_kwargs=additional_kwargs,
        response_metadata=response_metadata,
        tool_call_chunks=tool_call_chunks,
        usage_metadata=usage_metadata,
        chunk_position=chunk_position,
    )


# ============================================================
# 四、模型层输入归一：对应 chat_models.py:444 与 llms.py:318
# ============================================================


class StringPromptValue:
    """纯文本提示的值对象。"""

    def __init__(self, text: str) -> None:
        self.text = text

    def to_messages(self) -> list[HumanMessage]:
        return [HumanMessage(self.text)]


class ChatPromptValue:
    """消息列表提示的值对象。"""

    def __init__(self, messages: list[BaseMessage]) -> None:
        self.messages = messages


def _convert_input(model_input: Any) -> Any:
    """chat_models.py:444-455 与 llms.py:318-329，两处代码逐字相同。

    三种输入形状，三种去向：
      PromptValue  原样返回
      str          包成 StringPromptValue
      消息类 Sequence 包成 ChatPromptValue，内部逐条 convert_to_messages
      其它         直接 ValueError

    注意：BaseChatModel 和 BaseLLM 的差别不在这里，而在 invoke 的返回形状。
    """
    if isinstance(model_input, (StringPromptValue, ChatPromptValue)):
        return model_input
    if isinstance(model_input, str):
        return StringPromptValue(model_input)
    if isinstance(model_input, Sequence):
        return ChatPromptValue(convert_to_messages(model_input))
    raise ValueError(
        f"Invalid input type {type(model_input)}. "
        "Must be a PromptValue, str, or list of BaseMessages."
    )


# ============================================================
# 五、近似 token 计数：对应 messages/utils.py:2186
# ============================================================


def count_tokens_approximately(
    messages: Iterable[Any],
    *,
    chars_per_token: float = 4.0,
    extra_tokens_per_message: float = 3.0,
) -> int:
    """utils.py:2186-2195 的默认参数口径：每 4 字符 1 token，每条消息额外 3 token。

    这是近似值，不是模型真实分词结果。真实计数要把消息丢给模型，
    这里只是给 trim_messages 一个不花钱的默认值。
    """
    total = 0.0
    for message in messages:
        msg = _convert_to_message(message)
        text = msg.text
        # tool.py:67 的 tool_call_id 也要计入，否则多工具轮次会被低估
        extra = getattr(msg, "tool_call_id", "") or ""
        total += len(text) / chars_per_token + extra_tokens_per_message
        total += len(extra) / chars_per_token
    return int(total)


def trim_messages(
    messages: Sequence[Any],
    *,
    max_tokens: int,
    strategy: str = "last",
) -> list[BaseMessage]:
    """utils.py:1082 的精简版，只保留最朴素的 last 策略。

    真实实现有一堆保护参数（start_on / end_on / include_system），
    核心逻辑就一句：从最新的那条往回塞，塞不下就停。
    """
    result: list[BaseMessage] = []
    for raw in reversed(messages):
        # 每轮把更老的一条放到 result 最前面，所以循环结束时 result 已是时序（最老在前）
        candidate = [_convert_to_message(raw), *result]
        if count_tokens_approximately(candidate) > max_tokens:
            break
        result = candidate
    return result


# ============================================================
# 贯穿案例：一条工单消息从裸字符串走到流式合并
# ============================================================


def run_case() -> None:
    print("=== 案例：一条退款工单如何穿过消息层与模型层 ===\n")

    # 1. 四种输入形状归一
    print("[1] 四种输入形状归一（_convert_to_message）")
    raw_inputs = [
        "我要退款订单号12345",
        ("system", "你是客服助手，回答控制在两句话内"),
        {"role": "human", "content": "订单号12345 还没到账"},
        HumanMessage("我等了三天了"),
    ]
    for raw in raw_inputs:
        msg = _convert_to_message(raw)
        print(f"    输入 {raw!r}")
        print(f"    归一 {type(msg).__name__}(type={msg.type!r})")
    print()

    # 2. 模型层输入归一
    print("[2] 模型层输入归一（_convert_input）")
    as_str = _convert_input("我要退款")
    as_msgs = _convert_input(["系统提示", ("human", "我要退款")])
    print(f"    str 输入      -> {type(as_str).__name__}, 消息数 {len(as_str.to_messages())}")
    print(f"    列表输入      -> {type(as_msgs).__name__}, 消息数 {len(as_msgs.messages)}")
    print(f"    消息类型列表  -> {[m.type for m in as_msgs.messages]}")
    print()

    # 3. AIMessage 的 tool_calls 从 content_blocks 抬升
    print("[3] content_blocks 里的 tool_call 自动抬升成 tool_calls")
    ai = AIMessage(
        content_blocks=[
            {"type": "text", "text": "我先查一下订单"},
            {
                "type": "tool_call",
                "name": "query_order",
                "args": {"order_id": "12345"},
                "id": "call_1",
            },
        ]
    )
    print(f"    content 块数  {len(ai.content)}")
    print(f"    tool_calls    {json.dumps(ai.tool_calls, ensure_ascii=False)}")
    print()

    # 4. ToolMessage 回填
    print("[4] ToolMessage 用 tool_call_id 挂回请求")
    tool_msg = ToolMessage(
        "已下单，金额 99 元",
        tool_call_id="call_1",
        name="query_order",
    )
    print(f"    tool_call_id  {tool_msg.tool_call_id}")
    print(f"    status        {tool_msg.status}")
    print()

    # 5. 流式分片合并
    print("[5] 流式分片逐字合并（add_ai_message_chunks）")
    chunks = [
        AIMessageChunk(
            content="正在",
            tool_call_chunks=[{"name": "query_order", "args": '{"order_id":', "index": 0, "id": "call_1"}],
            usage_metadata={"input_tokens": 30, "output_tokens": 1, "total_tokens": 31},
        ),
        AIMessageChunk(
            content="查询",
            tool_call_chunks=[{"name": None, "args": ' "12345"}', "index": 0, "id": None}],
            usage_metadata={"input_tokens": 0, "output_tokens": 1, "total_tokens": 1},
        ),
        AIMessageChunk(
            content="订单",
            tool_call_chunks=[],
            usage_metadata={"input_tokens": 0, "output_tokens": 1, "total_tokens": 1},
            chunk_position="last",
        ),
    ]
    merged = chunks[0]
    for chunk in chunks[1:]:
        merged = merged + chunk
    print(f"    分片数        {len(chunks)}")
    print(f"    合并后正文    {merged.text!r}")
    print(f"    合并后 usage  {json.dumps(merged.usage_metadata, ensure_ascii=False)}")
    print(f"    tool_call     {json.dumps(merged.tool_call_chunks, ensure_ascii=False)}")
    print(f"    chunk_position {merged.chunk_position}")
    print()

    # 6. 近似计数与裁剪
    print("[6] 近似 token 计数与裁剪（trim_messages）")
    history = [
        SystemMessage("你是客服助手"),
        HumanMessage("我要退款订单号12345"),
        AIMessage("请问是什么原因退款"),
        HumanMessage("买错了"),
        AIMessage("已为您发起退款"),
        HumanMessage("谢谢"),
    ]
    approx = count_tokens_approximately(history)
    print(f"    历史条数      {len(history)}")
    print(f"    近似 token    {approx}")
    trimmed = trim_messages(history, max_tokens=20, strategy="last")
    print(f"    裁剪后条数    {len(trimmed)}")
    print(f"    裁剪后类型    {[m.type for m in trimmed]}")
    print()


def self_test() -> int:
    """自检：每条断言都对应上面核实过的一个源码行为。"""
    checks: list[tuple[str, bool]] = []

    def check(name: str, condition: bool) -> None:
        checks.append((name, condition))

    # 消息族字段
    msg = HumanMessage("你好", name="小李")
    check("HumanMessage.type 为 human", msg.type == "human")
    check("name 字段独立于 content", msg.name == "小李")

    # text 属性只取文本块
    multimodal = HumanMessage(
        content_blocks=[
            {"type": "text", "text": "看图"},
            {"type": "image", "url": "http://x/y.png"},
        ]
    )
    check("text 跳过非文本块", multimodal.text == "看图")

    # _convert_to_message 四条分支
    check("裸字符串归一为 human", _convert_to_message("hi").type == "human")
    check("二元组按 role 取类", _convert_to_message(("system", "s")).type == "system")
    check("字典用 role 键", _convert_to_message({"role": "ai", "content": "a"}).type == "ai")
    check("字典用 type 键兜底", _convert_to_message({"type": "system", "content": "s"}).type == "system")
    check(
        "content 为 None 兜成空串",
        _convert_to_message({"role": "human", "content": None}).text == "",
    )
    check(
        "消息实例原样返回",
        _convert_to_message(msg) is msg,
    )

    # 非法形状
    try:
        _convert_to_message(123)
        check("非消息形状报 NotImplementedError", False)
    except NotImplementedError:
        check("非消息形状报 NotImplementedError", True)

    try:
        _convert_to_message({"content": "缺 role"})
        check("缺 role 报 ValueError", False)
    except ValueError:
        check("缺 role 报 ValueError", True)

    # AIMessage 的 tool_calls 抬升
    ai = AIMessage(
        content_blocks=[
            {"type": "text", "text": "查一下"},
            {"type": "tool_call", "name": "f", "args": {}, "id": "c1"},
        ]
    )
    check("content_blocks 里的 tool_call 抬升成功", len(ai.tool_calls) == 1)
    check("tool_call 保留 name", ai.tool_calls[0]["name"] == "f")

    # ToolMessage 必填校验
    try:
        ToolMessage("结果")
        check("ToolMessage 缺 tool_call_id 报错", False)
    except KeyError:
        check("ToolMessage 缺 tool_call_id 报错", True)

    tool_msg = ToolMessage("ok", tool_call_id="c1")
    check("ToolMessage 默认 status 为 success", tool_msg.status == "success")

    # merge_content 分派
    check("str + str 直接相加", merge_content("a", "b") == "ab")
    check("str + list 变列表", merge_content("a", ["b"]) == ["a", "b"])
    check("list + list 按 index 合", merge_content([{"index": 0, "t": "a"}], [{"index": 0, "t": "b"}]) == [{"index": 0, "t": "ab"}])
    check("追加到末元素避免碎片", merge_content(["a"], "b") == ["ab"])

    # add_ai_message_chunks
    left = AIMessageChunk(
        content="你",
        tool_call_chunks=[{"name": "f", "args": '{"a":', "index": 0, "id": "c1"}],
        usage_metadata={"input_tokens": 10, "output_tokens": 1, "total_tokens": 11},
    )
    right = AIMessageChunk(
        content="好",
        tool_call_chunks=[{"name": None, "args": "1}", "index": 0, "id": None}],
        usage_metadata={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
        chunk_position="last",
    )
    merged = left + right
    check("分片正文拼接", merged.text == "你好")
    check("tool_call 按 index 拼成合法 JSON", merged.tool_call_chunks[0]["args"] == '{"a":1}')
    check("usage 数值相加而非拼接", merged.usage_metadata["input_tokens"] == 15)
    check("usage total 相加", merged.usage_metadata["total_tokens"] == 18)
    check("chunk_position 冒泡为 last", merged.chunk_position == "last")

    # usage details 逐项相加
    u = add_usage(
        {"input_tokens": 1, "input_token_details": {"cache_read": 10}},
        {"input_tokens": 1, "input_token_details": {"cache_read": 5, "audio": 2}},
    )
    check("usage details 逐项相加", u is not None and u["input_token_details"]["cache_read"] == 15)
    check("usage details 新增键", u is not None and u["input_token_details"]["audio"] == 2)
    check("两个 None 相加返回 None", add_usage(None, None) is None)

    # _convert_input 三条分支
    check("str 包成 StringPromptValue", isinstance(_convert_input("x"), StringPromptValue))
    check("列表包成 ChatPromptValue", isinstance(_convert_input(["x"]), ChatPromptValue))
    pv = ChatPromptValue([HumanMessage("x")])
    check("PromptValue 原样返回", _convert_input(pv) is pv)

    try:
        _convert_input(123)
        check("非法输入报 ValueError", False)
    except ValueError:
        check("非法输入报 ValueError", True)

    # 近似计数与裁剪
    history = [
        SystemMessage("你是客服助手"),
        HumanMessage("我要退款订单号12345"),
        AIMessage("请问原因"),
        HumanMessage("买错了"),
    ]
    approx = count_tokens_approximately(history)
    check("近似计数为正整数", approx > 0)
    trimmed = trim_messages(history, max_tokens=8, strategy="last")
    check("裁剪后条数少于原始", len(trimmed) < len(history))
    check("裁剪保留最新一条", trimmed[-1].text == "买错了")
    check("裁剪结果保持时序", [m.type for m in trimmed] == ["ai", "human"])
    check("裁剪结果不超预算", count_tokens_approximately(trimmed) <= 8)

    # 输出一致性：案例跑通不抛异常
    try:
        run_case()
        check("端到端案例跑通", True)
    except Exception as exc:  # noqa: BLE001
        check(f"端到端案例跑通（{type(exc).__name__}: {exc}）", False)

    print("self-test PASS" if all(ok for _, ok in checks) else "self-test FAIL")
    for name, ok in checks:
        if not ok:
            print(f"  FAIL: {name}")
    return 0 if all(ok for _, ok in checks) else 1


def main() -> int:
    import sys

    if "--self-test" in sys.argv:
        return self_test()
    run_case()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
