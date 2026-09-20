#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01_bare_agent.py — 裸奔 Agent：工具返回含糊/只看到部分视野就自信报完成。

演示故障树「失败模式一 + 失败模式二」的最小骨架：
  - 工具返回即验收（不重新读取真实状态）
  - grep 只覆盖探索过的目录，漏掉的调用点从不在 Agent 的视野里
  - 于是 Agent 说 "done" 时，真实环境里还有调用点没改

纯标准库实现，后端可注入（FakeBackend），运行：
  python3 01_bare_agent.py --self-test
  python3 01_bare_agent.py              # 跑一遍演示
"""

import sys
import argparse


class FakeBackend:
    """可注入的假代码库后端。

    real_call_sites: 权威真相——符号 symbol 在所有目录里的真实调用点。
    explored_dirs:   Agent 会去 grep 的目录（模拟 Agent 的有限视野）。
    edited:          已经被 edit 命中的调用点集合。
    """

    def __init__(self, real_call_sites, explored_dirs):
        # real_call_sites: dict[filepath] -> list[int(line_no)]
        self.real_call_sites = {k: list(v) for k, v in real_call_sites.items()}
        self.explored_dirs = list(explored_dirs)
        self.edited = set()  # 存 (filepath, line_no)

    def grep(self, symbol):
        """Agent 的工具：只在 explored_dirs 里找 symbol。"""
        hits = []
        for path, lines in self.real_call_sites.items():
            in_explored = any(path.startswith(d) for d in self.explored_dirs)
            if in_explored:
                for ln in lines:
                    hits.append((path, ln))
        return hits

    def edit(self, path, line):
        """Agent 的工具：标记一处调用点被改过（模拟落地）。"""
        self.edited.add((path, line))
        return True

    def authoritative_call_sites(self):
        """真实环境能提供的全量调用点（相当于 IDE 的 Find All References）。"""
        out = []
        for path, lines in self.real_call_sites.items():
            for ln in lines:
                out.append((path, ln))
        return out


def bare_agent(backend, symbol):
    """裸奔 Agent：grep -> edit 看到的点 -> 直接按自己的记录报完成。

    关键缺陷：它从不调用 authoritative_call_sites() 复核，
    也从不打开 explored_dirs 之外的目录。
    """
    hits = backend.grep(symbol)
    updated = 0
    for path, line in hits:
        backend.edit(path, line)
        updated += 1
    # 声明即验收：用自己看到并改过的数字直接收工
    claim = {
        "reported_updated": updated,
        "verdict": "done",
        "message": "全部引用已更新，done",
    }
    return claim


def _make_backend():
    # 真实调用点：8 处在 Agent 会搜的目录，4 处在它从不去的目录（共 12 处）
    real = {
        "src/api/auth.ts": [12, 47],
        "src/middleware/token.ts": [8],
        "src/services/login.ts": [23, 91],
        "src/api/payment.ts": [3],
        "src/services/order.ts": [60],
        "src/services/session.ts": [40],
        "src/cron/cleanup.ts": [15],            # 未探索目录
        "src/cron/refresh.ts": [30],            # 未探索目录
        "src/jobs/admin.ts": [5],               # 未探索目录
        "src/jobs/rate_limit.ts": [72],         # 未探索目录
    }
    explored = ["src/api/", "src/middleware/", "src/services/"]
    return FakeBackend(real, explored)


def self_test():
    print("=== 01_bare_agent self-test ===")
    backend = _make_backend()
    claim = bare_agent(backend, "verifyToken")

    authoritative = backend.authoritative_call_sites()
    hidden_updated = sum(
        1 for (p, l) in authoritative
        if (p, l) in backend.edited and not any(p.startswith(d) for d in backend.explored_dirs)
    )
    total_hidden = sum(
        1 for (p, l) in authoritative
        if not any(p.startswith(d) for d in backend.explored_dirs)
    )

    print(f"Agent 声明已更新: {claim['reported_updated']} 处，结论: {claim['verdict']}")
    print(f"真实全量调用点: {len(authoritative)} 处")
    print(f"未探索目录里的真实调用点: {total_hidden} 处")
    print(f"其中被真正改到的: {hidden_updated} 处（应为 0）")

    # 断言：裸奔 Agent 会谎报完成，且 hidden 处真实落地为 0
    ok = (
        claim["verdict"] == "done"
        and claim["reported_updated"] == 8
        and total_hidden == 4
        and hidden_updated == 0
    )
    if ok:
        print("PASS: 裸奔 Agent 在只看到部分视野时谎报 done，hidden 处 0 落地（符合预期）。")
        return True
    else:
        print("FAIL: 与预期不符。")
        return False


def demo():
    print("=== 01_bare_agent demo ===")
    backend = _make_backend()
    claim = bare_agent(backend, "verifyToken")
    print(f"Agent 说: {claim['message']}（声称更新 {claim['reported_updated']} 处）")
    print("但真实环境里，src/cron、src/jobs 等目录还有调用点从未被碰过。")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true", help="运行自检并退出")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    demo()


if __name__ == "__main__":
    main()
