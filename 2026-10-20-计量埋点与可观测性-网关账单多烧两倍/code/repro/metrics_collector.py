#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
metrics_collector.py — 多租户 AI 网关计量埋点最小可复现实现（纯标准库，免 key）

文章场景重现：
  网关只按 RPM（每分钟请求数）限流，并且只埋了「总请求数」一个总量指标。
  跑了三个月，账单翻了两倍，回查才发现旧仪表盘是瞎的：
    1. 没按租户 / 模型 / 路由 / 端点拆维度，所有流量混在一个数字里；
    2. 只记成功、没记 429 与重试，限流风暴全在盲区；
    3. 只记 request 数、没记 token 数，更没拆 cached / uncached，
       所以缓存一旦失效，token 账单翻倍也无人察觉。

本脚本演示「正确埋点」长什么样：给定一份请求日志，按租户聚合
  RPM / TPM（输入、输出、缓存命中分别统计）/ 429 比率 / 重试比率 / 错误比率，
并指出旧仪表盘只展示了请求数这一项、漏掉了其余所有维度。

运行：
  python3 metrics_collector.py            # 打印按租户聚合报告
  python3 metrics_collector.py --self-test  # 断言聚合数学正确
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Request:
    tenant: str
    model: str
    route: str
    endpoint: str
    ts: float
    status: int            # 200 / 429 / 500 ...
    input_tokens: int      # 本次请求 prompt 总 token（含将被缓存命中的部分）
    output_tokens: int
    cached_tokens: int     # 其中命中缓存、按缓存价计费的 token
    is_retry: bool         # 是否为限流/错误后的重试请求


def build_synthetic_log(window_s: float = 60.0) -> list[Request]:
    """构造一份确定性的请求日志，不依赖随机数，便于复现与断言。

    三个租户刻意做对比：
      acme   —— 缓存失效 + 限流风暴：缓存命中为 0，429 占 20%、重试占 30%
      globex —— 缓存健康：命中 3500/4000，429 仅 5%
      inyo   —— 小租户，无重试，用来验证聚合求和
    """
    reqs: list[Request] = []
    t = 0.0

    # --- acme：100 次请求，20 次 429，80 次成功（其中 30 次是重试） ---
    for i in range(100):
        if i < 20:  # 前 20 次被限流拒绝，admission 阶段就被挡，不计 token
            reqs.append(Request("acme", "gpt-x", "chat", "/v1/chat", t,
                                429, 0, 0, 0, False))
        else:
            is_retry = (i - 20) < 30  # 80 次成功里的前 30 次标记为重试
            reqs.append(Request("acme", "gpt-x", "chat", "/v1/chat", t,
                                200, 4000, 500, 0, is_retry))
        t += window_s / 100.0

    # --- globex：100 次请求，5 次 429，95 次成功（5 次重试），缓存健康 ---
    for i in range(100):
        if i < 5:
            reqs.append(Request("globex", "gpt-x", "chat", "/v1/chat", t,
                                429, 0, 0, 0, False))
        else:
            is_retry = (i - 5) < 5
            reqs.append(Request("globex", "gpt-x", "chat", "/v1/chat", t,
                                200, 4000, 500, 3500, is_retry))
        t += window_s / 100.0

    # --- inyo：50 次请求，2 次 429，48 次成功，0 重试，缓存部分命中 ---
    for i in range(50):
        if i < 2:
            reqs.append(Request("inyo", "haiku-y", "chat", "/v1/chat", t,
                                429, 0, 0, 0, False))
        else:
            reqs.append(Request("inyo", "haiku-y", "chat", "/v1/chat", t,
                                200, 2000, 300, 1500, False))
        t += window_s / 50.0

    return reqs


@dataclass
class TenantAgg:
    tenant: str
    requests: int = 0
    success: int = 0
    http_429: int = 0
    http_5xx: int = 0
    retries: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def rpm(self) -> float:
        # 日志窗口固定为 60s，故 requests 即每分钟请求数
        return self.requests

    @property
    def tpm(self) -> float:
        return self.total_tokens  # 60s 窗口，total_tokens 即每分钟 token 数

    @property
    def error_rate(self) -> float:
        if self.requests == 0:
            return 0.0
        return (self.http_429 + self.http_5xx) / self.requests

    @property
    def rate_limited_rate(self) -> float:
        if self.requests == 0:
            return 0.0
        return self.http_429 / self.requests

    @property
    def retry_rate(self) -> float:
        if self.requests == 0:
            return 0.0
        return self.retries / self.requests

    @property
    def cache_hit_ratio(self) -> float:
        if self.input_tokens == 0:
            return 0.0
        return self.cached_tokens / self.input_tokens


def aggregate_per_tenant(reqs: list[Request]) -> dict[str, TenantAgg]:
    aggs: dict[str, TenantAgg] = defaultdict(lambda: TenantAgg(""))
    for r in reqs:
        a = aggs[r.tenant]
        a.tenant = r.tenant
        a.requests += 1
        if r.status == 200:
            a.success += 1
        elif r.status == 429:
            a.http_429 += 1
        elif r.status >= 500:
            a.http_5xx += 1
        if r.is_retry:
            a.retries += 1
        a.input_tokens += r.input_tokens
        a.output_tokens += r.output_tokens
        a.cached_tokens += r.cached_tokens
    return dict(aggs)


def print_report(aggs: dict[str, TenantAgg]) -> None:
    header = (f"{'tenant':8} {'req':>5} {'rpm':>5} {'tok':>9} {'tpm':>9} "
              f"{'cached':>8} {'cHit%':>6} {'429%':>6} {'retry%':>7} {'err%':>6}")
    print(header)
    print("-" * len(header))
    for name in sorted(aggs):
        a = aggs[name]
        print(f"{a.tenant:8} {a.requests:5d} {a.rpm:5.0f} {a.total_tokens:9d} "
              f"{a.tpm:9.0f} {a.cached_tokens:8d} {a.cache_hit_ratio*100:6.1f} "
              f"{a.rate_limited_rate*100:6.1f} {a.retry_rate*100:7.1f} "
              f"{a.error_rate*100:6.1f}")
    print()
    print("旧仪表盘只展示了 rpm 这一列，并且把所有租户混成一个总数。")
    print("于是 acme 的 429 风暴（20%）、重试（30%）、缓存失效（cHit 0%）")
    print("和 token 暴涨（tpm 360000）全部藏在看不见的维度里。")


def self_test() -> int:
    reqs = build_synthetic_log()
    aggs = aggregate_per_tenant(reqs)

    total_req = sum(a.requests for a in aggs.values())
    checks = []

    # 1) 总量求和正确
    checks.append(("总请求数 = 250", total_req == 250))

    # 2) acme 的 429 比率精确等于注入的 20%
    checks.append(("acme 429 比率 == 0.20", abs(aggs['acme'].rate_limited_rate - 0.20) < 1e-9))

    # 3) acme 的重试比率精确等于注入的 30%
    checks.append(("acme 重试比率 == 0.30", abs(aggs['acme'].retry_rate - 0.30) < 1e-9))

    # 4) acme 的 TPM 精确等于 80 次成功 * (4000+500) = 360000
    checks.append(("acme tpm == 360000", aggs['acme'].tpm == 360000))

    # 5) acme 缓存命中为 0（缓存失效场景）
    checks.append(("acme 缓存命中比率 == 0", aggs['acme'].cache_hit_ratio == 0.0))

    # 6) globex 缓存健康，命中 3500/4000 = 87.5%
    checks.append(("globex 缓存命中比率 == 0.875",
                   abs(aggs['globex'].cache_hit_ratio - 0.875) < 1e-9))

    # 7) 错误比率 >= 429 比率（4xx/5xx 是 429 的超集）
    checks.append(("acme 错误比率 >= 429 比率",
                   aggs['acme'].error_rate >= aggs['acme'].rate_limited_rate))

    ok = True
    for label, passed in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed

    print()
    print("SELF-TEST: " + ("ALL PASS" if ok else "FAILED"))
    return 0 if ok else 1


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    reqs = build_synthetic_log()
    aggs = aggregate_per_tenant(reqs)
    print_report(aggs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
