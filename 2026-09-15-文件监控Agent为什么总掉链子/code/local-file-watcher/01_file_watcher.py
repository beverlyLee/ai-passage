#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01_file_watcher.py — 本地文件监控 Agent 的事件层。

真实落地里，watchdog 的 on_modified 会被同一个保存动作触发多次，
编辑器还会制造 create+modify+move 的「事件风暴」，临时文件 / 缓存
目录则全是噪音。本模块把原始事件收敛成「每个文件每个窗口一个
确定性事件」，是监控 Agent 不刷屏、不误删、不漏判的前提。

纯标准库实现，便于直接进 CI。生产环境把 simulate_event_stream
换成 watchdog 的事件回调即可（接口完全一致：call handle_event）。
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional


@dataclass
class FileEvent:
    path: str
    op: str            # create | modify | delete | move
    ts: float = 0.0
    is_dir: bool = False


# 默认噪音路径：命中即丢弃，不进处理管线
DEFAULT_EXCLUDES = (
    ".git/", "node_modules/", "__pycache__/",
    ".DS_Store", "~", ".tmp", "/.cache/", "Library/Caches/",
)


class Watcher:
    """把高频原始事件收敛为低频确定性事件。"""

    def __init__(
        self,
        debounce: float = 0.4,
        dedup_ttl: float = 2.0,
        excludes: Iterable[str] = DEFAULT_EXCLUDES,
        now: Callable[[], float] = time.monotonic,
    ):
        self.debounce = debounce
        self.dedup_ttl = dedup_ttl
        self.excludes = tuple(excludes)
        self._now = now
        self._buffer: dict[str, FileEvent] = {}   # path -> 合并中的事件
        self._dedup: dict[str, float] = {}        # key -> 过期时间戳
        self.emitted: List[FileEvent] = []        # 测试可见

    # ---- 规则层 ----
    def _is_excluded(self, path: str) -> bool:
        return any(p in path for p in self.excludes)

    def _dedup_key(self, ev: FileEvent) -> str:
        return f"{ev.path}\x00{ev.op}"

    def _in_dedup(self, ev: FileEvent) -> bool:
        key = self._dedup_key(ev)
        exp = self._dedup.get(key)
        if exp is None:
            return False
        if self._now() > exp:
            del self._dedup[key]
            return False
        return True

    # ---- 入口：watchdog 的 on_modified 直接调用它 ----
    def handle_event(self, ev: FileEvent) -> Optional[FileEvent]:
        ev.ts = self._now() if ev.ts <= 0 else ev.ts
        if self._is_excluded(ev.path):
            return None                      # 噪音路径直接丢弃
        if self._in_dedup(ev):
            return None                      # 幂等：重复投递丢弃
        # 防抖合并：同一 path 只保留最后到达的事件
        self._buffer[ev.path] = ev
        return None

    # ---- 冲刷：到达 debounce 窗口后输出合并事件 ----
    def flush(self) -> List[FileEvent]:
        out: List[FileEvent] = []
        now = self._now()
        ready = [p for p, ev in self._buffer.items() if now - ev.ts >= self.debounce]
        for p in ready:
            ev = self._buffer.pop(p)
            self._dedup[self._dedup_key(ev)] = now + self.dedup_ttl
            out.append(ev)
            self.emitted.append(ev)
        return out


class Clock:
    """可注入时钟，供 self-test 做确定性时序。"""
    def __init__(self, t: float = 0.0):
        self.t = t
    def __call__(self) -> float:
        return self.t
    def advance(self, dt: float) -> None:
        self.t += dt


def simulate_event_stream(events: List[FileEvent], w: Watcher) -> List[FileEvent]:
    """演示用：顺序喂事件并冲刷。生产环境删掉本函数，直接 on_xxx -> handle_event。"""
    out: List[FileEvent] = []
    for ev in events:
        w.handle_event(ev)
        out += w.flush()
    return out


def _self_test() -> int:
    clk = Clock(0.0)
    w = Watcher(debounce=0.4, dedup_ttl=2.0, now=clk)

    # 1) 事件风暴：同一文件 3 次 modify 在 0.15s 内
    for _ in range(3):
        w.handle_event(FileEvent("a/report.md", "modify"))
        clk.advance(0.05)
    clk.advance(0.5)                       # 超过 debounce 窗口
    out = w.flush()
    assert len(out) == 1, f"事件风暴未合并: 输出 {len(out)} 个"
    print("[OK] 事件风暴合并为 1 个事件（3 次 modify -> 1）")

    # 2) 幂等：同一事件在 dedup_ttl 内重复投递
    w.handle_event(FileEvent("a/report.md", "modify"))
    clk.advance(0.5)
    out2 = w.flush()
    assert len(out2) == 0, f"幂等失效，重复触发: {out2}"
    print("[OK] 幂等去重生效（2s 内重复事件丢弃）")

    # 3) 排除：.git 路径被丢弃
    w.handle_event(FileEvent("proj/.git/index", "modify"))
    clk.advance(0.5)
    out3 = w.flush()
    assert all(".git" not in e.path for e in out3), "排除规则失效"
    print("[OK] 排除规则生效（.git 等噪音路径丢弃）")

    # 4) 不同文件分别处理
    w.handle_event(FileEvent("b/x.py", "create"))
    w.handle_event(FileEvent("b/y.py", "create"))
    clk.advance(0.5)
    out4 = w.flush()
    assert len(out4) == 2, f"多文件未分别处理: {len(out4)}"
    print("[OK] 不同文件分别独立处理")

    print("ALL_SELFTESTS_PASSED")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="本地文件监控 Agent 事件层：防抖 + 幂等 + 排除")
    p.add_argument("--self-test", action="store_true", help="运行内置自测")
    p.add_argument("--debounce", type=float, default=0.4)
    p.add_argument("--dedup-ttl", type=float, default=2.0)
    args = p.parse_args(argv)
    if args.self_test:
        return _self_test()
    print("事件层已加载。生产用法：watchdog on_modified -> Watcher.handle_event(event)；定时 flush()。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
