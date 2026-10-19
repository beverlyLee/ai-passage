#!/usr/bin/env python3
"""streaming_gateway_sim.py

流式网关的准入控制、TPM 计量、429 退避与并发维度，纯标准库模拟。

只用 Python 标准库，无需依赖，无需 API key。
运行:
    python3 streaming_gateway_sim.py --self-test   # 跑内置校验
    python3 streaming_gateway_sim.py               # 演示两个翻车点

设计要点（对应正文三个坑）:
  坑二 只限 RPM 不限 TPM：单请求吃满 token 预算，挡住其余正常请求。
  坑三 流式没有准入控制：限流判断放在首个 token 之后，只能把流掐断，
       前端拿到半截 JSON 直接崩。
  并发维度：流式连接长时间占用后端，必须限并发流数。
"""

import argparse


# 租户画像：每分钟请求数上限、每分钟 token 上限、最大并发流、优先级(大者优先)
TENANTS = {
    "free_shop": {"rpm": 60, "tpm": 20000, "max_conc": 3, "priority": 0},
    "paid_shop": {"rpm": 600, "tpm": 200000, "max_conc": 10, "priority": 1},
}


class Gateway:
    def __init__(self, check_tpm: bool = True, admit_before_first_token: bool = True):
        self.clock = 0.0
        self.check_tpm = check_tpm                  # 是否做 token 维度限流
        self.admit_before = admit_before_first_token  # 准入是否在首个 token 之前
        self.state = {}
        for k, cfg in TENANTS.items():
            self.state[k] = {
                "req": 0, "req_reset": 0.0,
                "tok": 0, "tok_reset": 0.0,
                "conc": 0,
            }

    def _rpm_ok(self, k: str) -> bool:
        st = self.state[k]
        if self.clock - st["req_reset"] >= 60.0:
            st["req"] = 0
            st["req_reset"] = self.clock
        return st["req"] + 1 <= TENANTS[k]["rpm"]

    def _tpm_ok(self, k: str, tok: int) -> bool:
        if not self.check_tpm:
            return True  # 不做 token 维度检查 -> 对 token 完全失明
        st = self.state[k]
        if self.clock - st["tok_reset"] >= 60.0:
            st["tok"] = 0
            st["tok_reset"] = self.clock
        return st["tok"] + tok <= TENANTS[k]["tpm"]

    def _conc_ok(self, k: str) -> bool:
        return self.state[k]["conc"] + 1 <= TENANTS[k]["max_conc"]

    def admit(self, k: str, tok: int):
        """在首个 token 发出前做准入。返回 (ok, reason, retry_after)。"""
        if not self._rpm_ok(k):
            return (False, "rpm", 60 - (self.clock - self.state[k]["req_reset"]))
        if not self._tpm_ok(k, tok):
            return (False, "tpm", 60 - (self.clock - self.state[k]["tok_reset"]))
        if not self._conc_ok(k):
            return (False, "concurrency", None)
        st = self.state[k]
        st["req"] += 1
        st["tok"] += tok
        st["conc"] += 1
        return (True, "ok", None)

    def stream_request(self, k: str, est_tokens: int, chunks: int = 5):
        """模拟一次流式请求。返回 (accepted, bytes_sent, reason)。

        admit_before_first_token=True：首个 token 前准入，超预算直接拒，bytes_sent=0。
        False：先发后掐，发到一半发现超预算，bytes_sent>0（半截流）。
        """
        if not self.admit_before:
            first_chunk = est_tokens // chunks
            sent = first_chunk  # 已经通过 SSE 发出去了
            ok, reason, _ = self.admit(k, est_tokens - first_chunk)
            if not ok:
                return (False, sent, reason)  # 半截流
            return (True, est_tokens, "ok")
        ok, reason, _ = self.admit(k, est_tokens)
        if not ok:
            return (False, 0, reason)
        return (True, est_tokens, "ok")


def self_test():
    results = []

    # 坑二：只限 RPM 不限 TPM 时，网关对 token 维度失明，大小请求都放行，
    #       真正被挡的是下游供应商返回 429（这里用「网关无法拦截」表达）。
    g_broken = Gateway(check_tpm=False, admit_before_first_token=True)
    big = g_broken.stream_request("free_shop", 50000)
    small = g_broken.stream_request("free_shop", 100)
    results.append(("broken_gateway_admits_both", big[0] is True and small[0] is True))

    # 修了：开启 TPM 检查，大请求被本地拦下，小请求保住
    g_fixed = Gateway(check_tpm=True, admit_before_first_token=True)
    big2 = g_fixed.stream_request("free_shop", 50000)
    small2 = g_fixed.stream_request("free_shop", 100)
    results.append(("fixed_gateway_rejects_big_keeps_small",
                    big2[0] is False and small2[0] is True and big2[2] == "tpm"))

    # 坑三：先发后掐会发出半截流；先准入后发则 0 字节干净拒绝
    g_after = Gateway(check_tpm=True, admit_before_first_token=False)
    r_after = g_after.stream_request("free_shop", 50000, chunks=5)
    results.append(("after_first_token_half_sent",
                    r_after[0] is False and r_after[1] > 0 and r_after[2] == "tpm"))

    g_before = Gateway(check_tpm=True, admit_before_first_token=True)
    r_before = g_before.stream_request("free_shop", 50000, chunks=5)
    results.append(("before_first_token_clean_reject",
                    r_before[0] is False and r_before[1] == 0 and r_before[2] == "tpm"))

    # 并发维度：超过 max_conc 直接拒（free_shop max_conc=3）
    g_c = Gateway(check_tpm=False, admit_before_first_token=True)
    for _ in range(3):
        g_c.stream_request("free_shop", 100)
    fourth = g_c.stream_request("free_shop", 100)
    results.append(("concurrency_cap_enforced",
                    fourth[0] is False and fourth[2] == "concurrency"))

    return results


def main():
    parser = argparse.ArgumentParser(description="流式网关限流模拟")
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

    print("== 坑二演示：只限 RPM 不限 TPM ==")
    g = Gateway(check_tpm=False)
    big = g.stream_request("free_shop", 50000)
    small = g.stream_request("free_shop", 100)
    print(f"  大文档请求(50000 tok) 网关放行={big[0]}，正常小请求(100 tok) 网关放行={small[0]}")
    print("  （网关对 token 失明，两者都放行；真正 429 的是下游供应商，雪崩从这里开始）")
    print("== 坑三演示：先发后掐 vs 先准入 ==")
    g_after = Gateway(check_tpm=True, admit_before_first_token=False)
    r = g_after.stream_request("free_shop", 50000, chunks=5)
    print(f"  先发后掐：拒绝={not r[0]}，但已发出字节(半截流)={r[1]}")
    g_before = Gateway(check_tpm=True, admit_before_first_token=True)
    r2 = g_before.stream_request("free_shop", 50000, chunks=5)
    print(f"  先准入后发：拒绝={not r2[0]}，已发出字节={r2[1]}（干净拒绝，前端可正常处理）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
