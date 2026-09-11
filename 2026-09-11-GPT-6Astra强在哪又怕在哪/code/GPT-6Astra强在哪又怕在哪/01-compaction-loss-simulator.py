#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01-compaction-loss-simulator.py
================================

GPT-6 Astra 原理文配套脚本（第19篇）。

演示两件事：
1. 旧式「确定性 context compaction」为什么会在长 agent 会话里弄丢 *易失环境状态*
   （subshell 环境变量、临时目录指针、socket 句柄）—— 这些东西只被某个中间工具
   输出「按值携带」，没有任何地方重新派生它们。一旦启发式摘要把那条原始工具结果
   裁掉，后面的步骤就再也拿不回这个指针。
2. Astra 的「Structured Searchable Notes」子系统为什么能跨窗口保留这些细节：
   易失状态在 *产生时* 就被写入一个可检索笔记索引（不是靠把整段对话塞回上下文），
   所以无论窗口怎么被压缩，检索都能命中。

运行：
    python3 01-compaction-loss-simulator.py
    python3 01-compaction-loss-simulator.py --events examples/session_events.jsonl

无任何第三方依赖（仅标准库）。
"""

import argparse
import json
import sys
from dataclasses import dataclass, field

# 默认演示参数（--self-test 与「全部默认」判定都用它）
DEFAULT_BUDGET = 25      # 足够小：内置演示约 32 token，必然触发一次压缩
DEFAULT_KEY = "TMPDIR"


def estimate_tokens(text: str) -> int:
    """极简 token 估计：~4 字符 / token。仅用于本模拟的窗口预算判断。"""
    return max(1, len(text) // 4)


@dataclass
class Event:
    turn: int
    role: str            # "user" | "assistant" | "tool"
    content: str
    # 易失环境状态：key -> 值。只有携带它的那条原始事件里才有，无法从别处派生。
    volatile: dict = field(default_factory=dict)


def load_events(path: str):
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            events.append(
                Event(
                    turn=i,
                    role=obj.get("role", "tool"),
                    content=obj.get("content", ""),
                    volatile=obj.get("volatile", {}),
                )
            )
    return events


# ---------------------------------------------------------------------------
# 管线 A：旧式确定性 compaction（启发式摘要）
# ---------------------------------------------------------------------------
def run_compaction(events, window_budget):
    """
    模拟一个会压缩的窗口。
    - 每个事件按 token 累加进窗口。
    - 一旦窗口超过 budget，触发一次「摘要」：只保留第一条 + 最后两条，
      中间原始事件的 *内容被替换成一句摘要文本*，易失字段随之丢失。
    - 检索时只能看窗口里「当前还活着」的事件。
    """
    live = []          # 当前窗口内的事件（可能被摘要过）
    total_tokens = 0
    compacted_once = False

    for ev in events:
        cost = estimate_tokens(ev.content)
        # 触发压缩：超过预算就把中间事件压成摘要
        if total_tokens + cost > window_budget and len(live) > 3:
            kept_first = live[0]
            kept_tail = live[-2:]
            summary_text = (
                f"[摘要] 第{kept_first.turn+1}~{live[-1].turn+1}步之间的"
                f"{len(live)-3}次工具调用细节已被压缩，仅保留首尾步骤结论。"
            )
            live = [
                kept_first,
                Event(turn=-1, role="system", content=summary_text),
                *kept_tail,
            ]
            total_tokens = sum(estimate_tokens(e.content) for e in live)
            compacted_once = True
        live.append(ev)
        total_tokens += cost

    # 检索：在「当前还活着的窗口」里找一个 volatile key
    def retrieve(key):
        for e in reversed(live):
            if key in e.volatile:
                return e.volatile[key]
        return None

    return retrieve, compacted_once


# ---------------------------------------------------------------------------
# 管线 B：Structured Searchable Notes（Astra 模型）
# ---------------------------------------------------------------------------
def run_searchable_notes(events):
    """
    模拟 Astra 的内部可检索笔记子系统：
    - 易失状态在 *产生时* 就被写进一个独立索引（由内部自反注意力层治理）。
    - 该索引不受上下文窗口压缩影响，检索始终命中最早/最相关的那条记录。
    """
    notes_index = {}   # key -> value（覆盖写；保留最近一次设置）

    for ev in events:
        for k, v in ev.volatile.items():
            notes_index[k] = v   # 产生即入索引

    def retrieve(key):
        return notes_index.get(key)

    return retrieve


# ---------------------------------------------------------------------------
# 演示
# ---------------------------------------------------------------------------
def simulate(events, window_budget, probe_key):
    comp_retrieve, did_compact = run_compaction(events, window_budget)
    notes_retrieve = run_searchable_notes(events)

    comp_val = comp_retrieve(probe_key)
    notes_val = notes_retrieve(probe_key)

    print("=" * 64)
    print(f"探测易失键: {probe_key!r}  (在会话早期由某条工具输出按值携带)")
    print("-" * 64)
    print(f"[旧式 compaction]  窗口是否发生过压缩 : {did_compact}")
    print(f"[旧式 compaction]  检索结果           : {comp_val!r}")
    print(f"[Searchable Notes] 检索结果           : {notes_val!r}")
    print("-" * 64)
    if comp_val is None and notes_val is not None:
        print("结论: compaction 弄丢了易失指针，Searchable Notes 保留了下来。")
    elif comp_val == notes_val:
        print("结论: 两条管线都命中（本预算下未发生压缩，或指针在保留区内）。")
    else:
        print("结论: 两条管线结果不一致，见上。")
    print("=" * 64)
    return comp_val, notes_val


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default=None, help="JSONL 事件路径")
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET,
                    help=f"窗口 token 预算（默认 {DEFAULT_BUDGET}：足以让内置演示触发一次压缩并丢掉早期易失指针）")
    ap.add_argument("--key", default=DEFAULT_KEY, help="要探测的易失键名")
    ap.add_argument("--self-test", action="store_true",
                    help="强制跑「内置演示 + 默认预算」的自检场景（忽略 --events/--budget/--key）")
    args = ap.parse_args()

    self_test = args.self_test
    if self_test:
        # 自检场景固定为默认参数，避免"改了参数却仍按默认预期断言"
        events, budget, probe_key = None, DEFAULT_BUDGET, DEFAULT_KEY
        use_builtin = True
    else:
        budget, probe_key = args.budget, args.key
        use_builtin = args.events is None

    if use_builtin:
        # 内置演示会话：第 3 步（turn 2）设置了一个临时目录指针，
        # 之后会话继续推进，最终要在第 12 步根据它去清理那个目录。
        events = [
            Event(0, "user", "帮我在沙箱里编译这个仓库并跑测试。"),
            Event(1, "assistant", "我先建一个临时工作目录。"),
            Event(2, "tool", "mkdir 完成，返回环境快照。",
                  volatile={"TMPDIR": "/tmp/agent-7f3a9c", "BUILD_ENV": "CC=clang"}),
            Event(3, "tool", "git clone 完成，检出 main 分支。"),
            Event(4, "tool", "configure 完成，生成 Makefile。"),
            Event(5, "tool", "编译进行中……"),
            Event(6, "tool", "编译完成，产出 12 个目标文件。"),
            Event(7, "tool", "运行单元测试，部分用例超时重试。"),
            Event(8, "tool", "重试通过，覆盖率 87%。"),
            Event(9, "tool", "打包产物为 tarball。"),
            Event(10, "tool", "上传产物到内部分发节点。"),
            Event(11, "assistant", "现在需要清理第 3 步创建的临时目录。"),
            Event(12, "tool", "准备 rm -rf 那个 TMPDIR。"),  # 这里要拿回 TMPDIR
        ]
    else:
        events = load_events(args.events)

    comp_val, notes_val = simulate(events, budget, probe_key)

    # 自检只在「全部参数均为默认」或显式 --self-test 时跑。
    # 用户一旦改了 events / budget / key，预期结论就随之变化，
    # 不能继续按默认预期断言（否则 --budget 600 这类正常用法会崩）。
    run_check = self_test or (
        use_builtin and budget == DEFAULT_BUDGET and probe_key == DEFAULT_KEY
    )
    if run_check:
        assert notes_val is not None, "自检失败：Searchable Notes 不应丢失易失键"
        assert comp_val is None, "自检失败：默认预算下 compaction 应已丢失易失键"
        print("\n[SELF-CHECK] OK：compaction 丢指针 / searchable-notes 保留指针。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
