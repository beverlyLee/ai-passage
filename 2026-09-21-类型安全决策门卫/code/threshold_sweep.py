#!/usr/bin/env python3
# 阈值扫描：量化「概率阈值定错」这个坑真实存在。
#
# 纯标准库。给定一批带真值标签的放行请求，扫 0.50~0.99 的阈值，
# 打印每个阈值下的误拦截率与误放行率。这条曲线不存在两全其美点，
# 只有权衡。这正是正文里阈值坑的证据。
#
# 用法:
#   python3 threshold_sweep.py --self-test
#   python3 threshold_sweep.py
import argparse
import random
import unicodedata


def _w(s):
    """字符串在终端里的显示宽度（CJK 字符记 2 格）。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in str(s))


def _pad(s, width, align="left"):
    """按显示宽度补齐，避免中文把表格列挤歪。"""
    s = str(s)
    gap = max(0, width - _w(s))
    return (" " * gap + s) if align == "right" else (s + " " * gap)


def safety_probability(req, rng):
    base = 0.92 if not req["is_dangerous"] else 0.55
    return max(0.0, min(1.0, base + rng.uniform(-0.22, 0.22)))


def rates_at(requests, rng, threshold):
    fb = fp = 0
    for r in requests:
        p = safety_probability(r, rng)
        allow = p >= threshold
        if not r["is_dangerous"] and not allow:
            fb += 1
        if r["is_dangerous"] and allow:
            fp += 1
    n_safe = sum(1 for r in requests if not r["is_dangerous"])
    n_danger = len(requests) - n_safe
    fbr = fb / n_safe if n_safe else 0.0
    fpr = fp / n_danger if n_danger else 0.0
    return fbr, fpr


def make_requests(n_safe, n_danger, seed):
    rng = random.Random(seed)
    reqs = []
    for _ in range(n_safe):
        reqs.append({"is_dangerous": False})
    for _ in range(n_danger):
        reqs.append({"is_dangerous": True})
    return reqs


def sweep(requests, seed, lo=0.50, hi=0.99, step=0.05):
    cols = [(8, "left"), (12, "right"), (12, "right"), (12, "right"), (12, "right")]
    heads = ["阈值", "误拦截率", "误放行率", "误拦截数", "误放行数"]
    print("".join(_pad(h, w, a) for h, (w, a) in zip(heads, cols)))
    n_safe = sum(1 for x in requests if not x["is_dangerous"])
    n_danger = len(requests) - n_safe
    n = int(round((hi - lo) / step)) + 1
    for i in range(n):
        t = round(lo + i * step, 2)
        r = random.Random(seed)  # 固定 seed 让各阈值可比
        fbr, fpr = rates_at(requests, r, t)
        fb = round(fbr * n_safe)
        fp = round(fpr * n_danger)
        cells = [f"{t:.2f}", f"{fbr*100:.1f}", f"{fpr*100:.1f}", str(fb), str(fp)]
        print("".join(_pad(c, w, a) for c, (w, a) in zip(cells, cols)))


def _self_test():
    reqs = make_requests(100, 100, seed=3)
    r = random.Random(3)
    fbr_lo, fpr_lo = rates_at(reqs, r, 0.50)
    r2 = random.Random(3)
    fbr_hi, fpr_hi = rates_at(reqs, r2, 0.99)
    # 阈值越低误放行越多，阈值越高误拦截越多（权衡方向正确）
    assert fpr_lo >= fpr_hi, "阈值低应误放行更高"
    assert fbr_lo <= fbr_hi, "阈值高应误拦截更高"
    # 极端值符合直觉：阈值 0.0 不误拦截；阈值 1.0 不误放行
    r3 = random.Random(3)
    fbr0, _ = rates_at(reqs, r3, 0.0)
    r4 = random.Random(3)
    _, fpr1 = rates_at(reqs, r4, 1.0)
    assert fbr0 == 0.0, "阈值0.0 不应误拦截"
    assert fpr1 == 0.0, "阈值1.0 不应误放行"
    print("self-test PASS: 阈值权衡方向正确，极端值符合预期")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        _self_test()
    else:
        _self_test()
        print("-" * 52)
        reqs = make_requests(400, 400, seed=7)
        sweep(reqs, seed=7)


if __name__ == "__main__":
    main()
