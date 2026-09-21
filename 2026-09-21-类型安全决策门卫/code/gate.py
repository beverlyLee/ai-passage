#!/usr/bin/env python3
# 工具风险门卫：用类型安全概率模型给 Agent 的危险工具调用当闸刀。
#
# 最小可运行示例，纯标准库，不依赖任何 Jev SDK。
# 假后端返回可复现的安全概率，方便本地跑、改、注入自己的真后端。
#
# 用法:
#   python3 gate.py --self-test     # 校验统计逻辑与阈值权衡
#   python3 gate.py --demo          # 跑一批真实感样本，打印放行/拦截/误判表
#
# 核心要盯紧的那一行在 decide(): safety_prob >= threshold
# 它把连续概率切成了布尔放行令，切的位置就是阈值。
import argparse
import random


class FakeJevBackend:
    """模拟一个类型安全概率决策模型的 Noul 输出。

    真实场景你换成对 TypeSafe / Jev API 的调用即可，接口保持一致：
    输入 state + 一个问题，返回 0~1 之间的「安全概率」。
    """

    def __init__(self, seed=7):
        self._rng = random.Random(seed)

    def safety_probability(self, request):
        # 用确定性噪声构造「校准过」的概率：
        # 安全请求大概率落在 0.7~0.99，危险请求大概率落在 0.33~0.77，
        # 两段有重叠，所以阈值才有意义、坑才真实存在。
        base = 0.92 if not request["is_dangerous"] else 0.55
        noise = self._rng.uniform(-0.22, 0.22)
        return max(0.0, min(1.0, base + noise))


def decide(safety_prob, threshold):
    """把连续概率切成布尔放行令。整篇文章盯紧的就是这一行。"""
    return safety_prob >= threshold


def evaluate(requests, backend, policy):
    """policy: 工具名 -> 阈值。门卫按工具风险分级放行。

    返回 (rows, false_block, false_pass)。
    false_block = 误拦截（真实安全却被挡）
    false_pass  = 误放行（真实危险却放行）
    """
    false_block = 0
    false_pass = 0
    rows = []
    for r in requests:
        p = backend.safety_probability(r)
        threshold = policy.get(r["tool"], policy["__default__"])
        allow = decide(p, threshold)
        status = "放行" if allow else "拦截"
        if not r["is_dangerous"] and not allow:
            false_block += 1
            verdict = "误拦截"
        elif r["is_dangerous"] and allow:
            false_pass += 1
            verdict = "误放行"
        else:
            verdict = "正确"
        rows.append((r["tool"], r["is_dangerous"], round(p, 3), threshold, status, verdict))
    return rows, false_block, false_pass


def _make_requests(n_safe, n_danger, seed=7):
    rng = random.Random(seed)
    reqs = []
    tools_safe = ["send_email", "read_file", "query_db"]
    tools_danger = ["run_shell", "delete_file", "drop_table"]
    for _ in range(n_safe):
        reqs.append({"tool": rng.choice(tools_safe), "is_dangerous": False})
    for _ in range(n_danger):
        reqs.append({"tool": rng.choice(tools_danger), "is_dangerous": True})
    return reqs


def _self_test():
    # 已知答案的样本，手算断言统计逻辑正确，并验证阈值权衡方向。
    # send_email 安全但概率 0.60（落在 0.5~0.7 之间），用来演示权衡。
    requests = [
        {"tool": "read_file", "is_dangerous": False, "_p": 0.95},
        {"tool": "run_shell", "is_dangerous": True, "_p": 0.20},
        {"tool": "send_email", "is_dangerous": False, "_p": 0.60},   # 安全、概率中等
        {"tool": "drop_table", "is_dangerous": True, "_p": 0.65},    # 危险且概率高 -> 误放行
    ]

    class Preset(FakeJevBackend):
        def safety_probability(self, request):
            return request["_p"]

    # 阈值 0.5：send_email(0.60) 放行正确，drop_table(0.65) 误放行 -> fb=0, fp=1
    policy = {"__default__": 0.5}
    _, fb, fp = evaluate(requests, Preset(), policy)
    assert fb == 0, f"阈值0.5 期望误拦截0, 实得{fb}"
    assert fp == 1, f"阈值0.5 期望误放行1, 实得{fp}"

    # 阈值 0.7：send_email(0.60) 被误拦截，drop_table(0.65) 被正确拦下 -> fb=1, fp=0
    # 抬高阈值用 1 条误拦截换掉了 1 条误放行，权衡真实存在。
    policy2 = {"__default__": 0.7}
    _, fb2, fp2 = evaluate(requests, Preset(), policy2)
    assert fp2 == 0, f"阈值0.7 期望误放行0, 实得{fp2}"
    assert fb2 == 1, f"阈值0.7 期望误拦截1, 实得{fb2}"

    print("self-test PASS: 统计逻辑与阈值权衡方向一致")


def _demo():
    backend = FakeJevBackend(seed=7)
    requests = _make_requests(60, 40)
    # 分级阈值：高危工具更严，低危更松（统一 0.9 会高危漏、低危堵）
    policy = {"__default__": 0.9, "run_shell": 0.95, "drop_table": 0.97, "delete_file": 0.95}
    rows, fb, fp = evaluate(requests, backend, policy)
    print(f"样本 {len(requests)} 条 | 误拦截 {fb} | 误放行 {fp}")
    print(f"{'工具':<12}{'危险':<6}{'安全概率':<10}{'阈值':<8}{'决策':<6}{'判定'}")
    for tool, danger, p, thr, status, verdict in rows[:12]:
        print(f"{tool:<12}{str(danger):<6}{p:<10}{thr:<8}{status:<6}{verdict}")
    print("... (仅显示前 12 条)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        _self_test()
    elif args.demo:
        _demo()
    else:
        _self_test()
        print("-" * 44)
        _demo()


if __name__ == "__main__":
    main()
