#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02_contract_agent.py — 加固 Agent：完成契约（completion contract）。

与 01 的唯一差别：在报完成之前，强制重新读取真实状态做复核。
把「完成」做成算出来的状态，而不是声明的状态。

纯标准库，后端可注入（FakeBackend），运行：
  python3 02_contract_agent.py --self-test
  python3 02_contract_agent.py
"""

import sys
import argparse


class FakeBackend:
    """可注入的假代码库后端（与 01 同构）。"""

    def __init__(self, real_call_sites, explored_dirs):
        self.real_call_sites = {k: list(v) for k, v in real_call_sites.items()}
        self.explored_dirs = list(explored_dirs)
        self.edited = set()

    def grep(self, symbol):
        hits = []
        for path, lines in self.real_call_sites.items():
            if any(path.startswith(d) for d in self.explored_dirs):
                for ln in lines:
                    hits.append((path, ln))
        return hits

    def edit(self, path, line):
        self.edited.add((path, line))
        return True

    def authoritative_call_sites(self):
        """真实环境的全量调用点——完成契约的复核依据。"""
        out = []
        for path, lines in self.real_call_sites.items():
            for ln in lines:
                out.append((path, ln))
        return out


def contract_agent(backend, symbol):
    """加固 Agent：grep -> edit -> 重新读取权威状态复核 -> 再决定能不能说 done。"""
    hits = backend.grep(symbol)
    for path, line in hits:
        backend.edit(path, line)

    # 完成契约：用权威真相复核，而不是用自己改过的数字收工
    authoritative = backend.authoritative_call_sites()
    missing = [
        (p, l) for (p, l) in authoritative
        if (p, l) not in backend.edited
    ]

    updated = len(backend.edited)
    if not missing:
        return {
            "reported_updated": updated,
            "verdict": "done",
            "missing": [],
            "message": f"已复核全部 {len(authoritative)} 处调用点，done",
        }
    # 有缺口：拒绝谎报，把缺口交出来
    return {
        "reported_updated": updated,
        "verdict": "incomplete",
        "missing": missing,
        "message": f"复核发现 {len(missing)} 处调用点未改，拒绝声明完成",
    }


def _make_backend():
    real = {
        "src/api/auth.ts": [12, 47],
        "src/middleware/token.ts": [8],
        "src/services/login.ts": [23, 91],
        "src/api/payment.ts": [3],
        "src/services/order.ts": [60],
        "src/services/session.ts": [40],
        "src/cron/cleanup.ts": [15],
        "src/cron/refresh.ts": [30],
        "src/jobs/admin.ts": [5],
        "src/jobs/rate_limit.ts": [72],
    }
    explored = ["src/api/", "src/middleware/", "src/services/"]
    return FakeBackend(real, explored)


def self_test():
    print("=== 02_contract_agent self-test ===")
    backend = _make_backend()
    claim = contract_agent(backend, "verifyToken")

    print(f"Agent 结论: {claim['verdict']}")
    print(f"Agent 消息: {claim['message']}")
    print(f"复核发现的缺口: {len(claim['missing'])} 处（应为 4）")

    ok = (
        claim["verdict"] == "incomplete"
        and len(claim["missing"]) == 4
        and all(not p.startswith(tuple(backend.explored_dirs)) for (p, _) in claim["missing"])
    )
    if ok:
        print("PASS: 完成契约拦住了假完成，把未探索目录的 4 处缺口暴露出来（而非谎报 done）。")
        return True
    else:
        print("FAIL: 完成契约未正确拦截。")
        return False


def demo():
    print("=== 02_contract_agent demo ===")
    backend = _make_backend()
    claim = contract_agent(backend, "verifyToken")
    print(f"Agent 结论: {claim['verdict']} -> {claim['message']}")
    if claim["missing"]:
        print("缺口明细（真实环境里没改到的调用点）:")
        for p, l in claim["missing"]:
            print(f"  {p}:{l}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true", help="运行自检并退出")
    args = parser.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    demo()


if __name__ == "__main__":
    main()
