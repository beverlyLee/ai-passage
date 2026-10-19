#!/usr/bin/env python3
"""rate_limit_core.py

四种限流算法的纯标准库实现，以及固定窗口的「边界双倍尖峰」演示。

只用 Python 标准库，无需任何依赖，无需 API key。
运行:
    python3 rate_limit_core.py --self-test    # 跑内置校验
    python3 rate_limit_core.py                # 演示固定窗口边界尖峰
"""

import argparse
import time
from collections import deque


class MockClock:
    """可手动推进的时钟，保证 self-test 与演示完全确定。"""

    def __init__(self, start: float = 0.0):
        self.t = start

    def now(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


class FixedWindow:
    """固定窗口计数器：固定时间窗内计数，窗口到期清零重置。

    优点：O(1) 内存，最简单。
    缺陷：在窗口边界可放出 2 倍配额（本文件 simulate_boundary 演示）。
    """

    def __init__(self, limit: int, window: float, clock: MockClock):
        self.limit = limit
        self.window = window
        self.clock = clock
        self.count = 0
        self.window_start = clock.now()

    def allow(self, n: int = 1) -> bool:
        now = self.clock.now()
        if now - self.window_start >= self.window:
            self.window_start = now
            self.count = 0
        if self.count + n <= self.limit:
            self.count += n
            return True
        return False


class SlidingWindowLog:
    """滑动窗口日志：记录每个请求时间戳，过期即删。

    优点：精确，无边界尖峰。
    缺陷：内存随请求数线性增长（O(n)）。
    """

    def __init__(self, limit: int, window: float, clock: MockClock):
        self.limit = limit
        self.window = window
        self.clock = clock
        self.log: deque = deque()

    def allow(self, n: int = 1) -> bool:
        now = self.clock.now()
        while self.log and self.log[0] <= now - self.window:
            self.log.popleft()
        if len(self.log) + n <= self.limit:
            for _ in range(n):
                self.log.append(now)
            return True
        return False


class TokenBucket:
    """令牌桶：令牌以固定速率补充至容量上限，允许突发（最多桶容量）。

    多数 LLM 供应商对外暴露的就是令牌桶（Anthropic 官方文档明确说它用令牌桶）。
    两个可独立调的参数：持续速率（rate）与突发容量（capacity）。
    """

    def __init__(self, rate: float, capacity: float, clock: MockClock):
        self.rate = rate          # tokens per second
        self.capacity = capacity
        self.clock = clock
        self.tokens = capacity
        self.last = clock.now()

    def allow(self, n: int = 1) -> bool:
        now = self.clock.now()
        elapsed = now - self.last
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last = now
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False


class LeakyBucket:
    """漏桶：请求入队，以固定速率漏出（处理），不允许突发。

    超出队列容量即丢弃。适合下游完全无法承受尖峰的脆弱系统（如写库）。
    """

    def __init__(self, rate: float, capacity: int, clock: MockClock):
        self.rate = rate          # requests drained per second
        self.capacity = capacity
        self.clock = clock
        self.queue: deque = deque()
        self.last = clock.now()

    def _leak(self) -> None:
        now = self.clock.now()
        drained = int((now - self.last) * self.rate)
        for _ in range(min(drained, len(self.queue))):
            self.queue.popleft()
        if drained:
            self.last = now

    def allow(self, n: int = 1) -> bool:
        self._leak()
        if len(self.queue) + n <= self.capacity:
            for _ in range(n):
                self.queue.append(self.clock.now())
            return True
        return False


def simulate_boundary(limit: int = 100, window: float = 60.0):
    """演示固定窗口的边界双倍尖峰。

    在第 59.9 秒把窗口打满，再在 60.1 秒（新窗口开头发满）。
    两批合计 2×limit 个请求在不到 1 秒内到达。
    """
    clock = MockClock(0.0)
    fw = FixedWindow(limit, window, clock)
    accepted_end = 0
    clock.advance(59.9)
    for _ in range(limit):
        if fw.allow():
            accepted_end += 1
    accepted_start = 0
    clock.advance(0.2)
    for _ in range(limit):
        if fw.allow():
            accepted_start += 1
    span = clock.now() - (window - 0.1)
    return accepted_end, accepted_start, span


def self_test():
    results = []

    # 1. 令牌桶允许突发至容量，之后受限
    clock = MockClock(0.0)
    tb = TokenBucket(rate=10, capacity=5, clock=clock)
    burst_ok = sum(1 for _ in range(5) if tb.allow())
    after_burst = tb.allow()  # 桶空，应拒绝
    results.append(("token_bucket_burst", burst_ok == 5 and after_burst is False))

    # 2. 令牌桶补充后恢复
    clock.advance(1.0)  # +10 tokens，封顶 5
    recovered = tb.allow()
    results.append(("token_bucket_refill", recovered is True))

    # 3. 固定窗口边界双倍尖峰
    end, start, span = simulate_boundary(limit=100, window=60.0)
    results.append(("fixed_window_boundary_2x", end == 100 and start == 100 and span < 1.0))

    # 4. 滑动窗口日志在边界不放大（前 100 个仍在 60s 窗内）
    clock = MockClock(0.0)
    sw = SlidingWindowLog(limit=100, window=60.0, clock=clock)
    clock.advance(59.9)
    a1 = sum(1 for _ in range(100) if sw.allow())
    clock.advance(0.2)  # t=60.1，前 100 个仅过 0.2s，仍在窗内
    a2 = sum(1 for _ in range(1) if sw.allow())
    results.append(("sliding_window_no_boundary", a1 == 100 and a2 == 0))

    # 5. 漏桶拒绝超出容量的突发
    clock = MockClock(0.0)
    lb = LeakyBucket(rate=5, capacity=3, clock=clock)
    burst = sum(1 for _ in range(10) if lb.allow())
    results.append(("leaky_bucket_rejects_burst", burst == 3))

    return results


def main():
    parser = argparse.ArgumentParser(description="四种限流算法演示")
    parser.add_argument("--self-test", action="store_true", help="跑内置校验")
    args = parser.parse_args()

    if args.self_test:
        results = self_test()
        print("self-test START")
        for name, ok in results:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        all_ok = all(ok for _, ok in results)
        print(f"self-test {'PASS' if all_ok else 'FAIL'} ({sum(ok for _, ok in results)}/{len(results)})")
        return 0 if all_ok else 1

    end, start, span = simulate_boundary(100, 60.0)
    print(f"固定窗口 limit=100/60s：窗口末尾接受 {end}，下一窗口开头接受 {start}")
    print(f"两批合计 {end + start} 个请求在 {span:.1f}s 内到达（理论峰值应为 100/60s）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
