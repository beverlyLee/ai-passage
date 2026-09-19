#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02_overthinking.py —— 推理模型「过度思考（overthinking）」模拟器（纯标准库）

你以为给推理模型更多的思考预算（更长的 thinking / 更高的 reasoning_effort），
准确率就一直往上走？大量实证研究显示不是：

  - TRACE（arXiv 2510.07880, Google DeepMind + UMich, 2025-10）：在简单任务上，
    long-thinking 模型比 short-thinking 慢 5–20 倍，却几乎没有实质准确率增益。
  - arXiv 2506.04210（马里兰等, 2025-06）：准确率随思考 token 增加呈**非单调**曲线——
    GSM-8K 上 385→1100 思考 token 时 82.2%→87.3%，但拉到 15980 token 反而跌到 70.3%。
  - arXiv 2507.04023v2（Srivastava 等, 2025-07）：覆盖 53 个 LLM、14 个基础数学任务，
    「Overthinking Score」显示推理模型常多耗约 18× token，有时准确率反而更低；
    在 constrained（强制短思考）时还会 catastrophic collapse，掉 28–36 个百分点。
  - Apple《The Illusion of Thinking》(arXiv 2506.06941, 2025)：低复杂度任务上标准模型
    更优，高复杂度任务两类推理模型都会崩。

本脚本用一个可解释的非单调曲线模型复现这套现象：
  - 每个任务有一个「最优思考预算」b*：想得不够或想得过头都会掉准确率。
  - 给的预算超过 b*，就开始「过度思考」——加的步骤越多，越容易自我怀疑、绕晕，准确率回落。
  - 用 Overthinking Score（实际用量 / 最优用量）量化浪费。

全部纯标准库；后端可注入；--self-test 跑断言；--n 批量复现。
"""

import argparse
import random
import sys


# ----------------------------------------------------------------------------
# 1. 任务画像：每个任务有自己的最优思考预算与峰值准确率
# ----------------------------------------------------------------------------
# b_star    : 最优思考 token 数（想这么多最准）
# acc_max   : 在该最优预算下的峰值准确率
# complexity: 仅用于展示
TASKS = {
    "加法-1+1":            {"b_star": 200,  "acc_max": 0.985, "complexity": "低"},
    "格式化JSON":          {"b_star": 300,  "acc_max": 0.980, "complexity": "低"},
    "一句话解释K8s":       {"b_star": 600,  "acc_max": 0.940, "complexity": "中"},
    "小学数学应用-GSM":    {"b_star": 1100, "acc_max": 0.873, "complexity": "中"},
    "多步逻辑推断":        {"b_star": 2500, "acc_max": 0.820, "complexity": "高"},
    "形式化证明草图":      {"b_star": 4200, "acc_max": 0.750, "complexity": "高"},
}


def accuracy_at_budget(task_name, budget, noise_seed=0):
    """给定任务与思考预算，返回该次回答的准确率（确定性 + 少量抖动）。

    曲线形状（非单调）：
      - 预算 < b*：想得越久越准（向峰值爬升，用饱和增长建模）。
      - 预算 > b*：过度思考，准确率按超出量线性回落（越想越错）。
    """
    spec = TASKS[task_name]
    b_star = spec["b_star"]
    acc_max = spec["acc_max"]

    if budget <= b_star:
        # 饱和增长：acc_max * (1 - exp(-budget / tau))，tau = b_star / 2 时到 b* 约 86%
        tau = b_star / 2.0
        base = acc_max * (1.0 - 2.718281828 ** (-budget / tau))
    else:
        # 过度思考惩罚：每超出 1 个 token，掉一点；封底到 0.5 避免无意义负值
        overflow = budget - b_star
        penalty = min(0.45, overflow / b_star * 0.30)  # 超出 1.5× 时封顶 0.45
        base = acc_max - penalty

    # 确定性抖动，保证同输入同输出
    rnd = random.Random(f"{noise_seed}:{task_name}:{int(budget)}")
    jitter = (rnd.random() - 0.5) * 0.02
    return max(0.0, min(1.0, base + jitter))


def find_peak(task_name, max_budget=20000, step=50):
    """网格搜最优预算与峰值准确率（演示用，非生产搜索）。"""
    best_b, best_a = 0, -1.0
    b = 0
    while b <= max_budget:
        a = accuracy_at_budget(task_name, b, noise_seed=1)
        if a > best_a:
            best_a, best_b = a, b
        b += step
    return best_b, best_a


def overthinking_score(task_name, budget):
    """Overthinking Score（参考 2507.04023v2 的定义精神）：实际用量 / 最优用量。

    只在预算超过最优时 > 1，表示「白想了多少倍」。
    """
    optimal_b, _ = find_peak(task_name)
    if optimal_b <= 0:
        return 1.0
    return budget / optimal_b


def regression_from_peak(task_name, budget):
    """相比峰值掉了多少准确率（过度思考的代价）。"""
    _, peak = find_peak(task_name)
    cur = accuracy_at_budget(task_name, budget, noise_seed=1)
    return max(0.0, peak - cur)


# ----------------------------------------------------------------------------
# 2. 批量报告
# ----------------------------------------------------------------------------
def report_task(task_name, budgets):
    spec = TASKS[task_name]
    optimal_b, peak = find_peak(task_name)
    line = "=" * 64
    print(line)
    print(f"任务={task_name}  复杂度={spec['complexity']}  最优预算≈{optimal_b} token  峰值准确率={peak:.3f}")
    print(f"{'预算token':>10} | {'准确率':>7} | {'OverScore':>9} | {'较峰值掉点':>9}")
    print("-" * 64)
    for b in budgets:
        a = accuracy_at_budget(task_name, b, noise_seed=1)
        score = overthinking_score(task_name, b)
        reg = regression_from_peak(task_name, b)
        flag = "  <- 过度思考" if score > 1.05 else ""
        print(f"{b:>10} | {a:>7.3f} | {score:>9.2f} | {reg:>9.3f}{flag}")
    print(line)


def run_batch(task_names, budgets):
    for t in task_names:
        report_task(t, budgets)


# ----------------------------------------------------------------------------
# 3. 自检
# ----------------------------------------------------------------------------
def _self_test():
    easy = "加法-1+1"

    # (1) 非单调：低复杂度任务上，给远超最优的预算，准确率反而比最优时低（越想越错）
    optimal_b, _ = find_peak(easy)
    acc_opt = accuracy_at_budget(easy, optimal_b, noise_seed=1)
    acc_huge = accuracy_at_budget(easy, optimal_b * 30, noise_seed=1)
    assert acc_huge < acc_opt, \
        f"过度思考应使简单题掉点：最优 {acc_opt:.3f} vs 海量预算 {acc_huge:.3f}"

    # (2) Overthinking Score 在预算远超最优时应 > 1（白想了很多倍）
    score = overthinking_score(easy, optimal_b * 20)
    assert score > 1.0, "预算远超最优时 Overthinking Score 应 > 1"

    # (3) 中等任务：适度增加预算应有益（先涨后跌），即最优预算下高于极小值
    med = "小学数学应用-GSM"
    acc_tiny = accuracy_at_budget(med, 50, noise_seed=1)
    acc_opt_med, _ = find_peak(med)
    acc_best = accuracy_at_budget(med, acc_opt_med, noise_seed=1)
    assert acc_best > acc_tiny, "中等任务：适度思考应优于几乎不思考"

    # (4) 确定性：同输入同输出
    assert accuracy_at_budget("格式化JSON", 500, noise_seed=1) == \
           accuracy_at_budget("格式化JSON", 500, noise_seed=1), "相同输入必须产出相同准确率"

    # (5) 封底：超大量预算不应把准确率打到非正
    assert accuracy_at_budget(easy, 10_000_000, noise_seed=1) > 0.0, "准确率应封底为正"

    print("SELF-TEST PASS")
    return True


# ----------------------------------------------------------------------------
# 4. 入口
# ----------------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(description="推理模型过度思考（overthinking）模拟器")
    p.add_argument("--self-test", action="store_true", help="跑断言自检")
    p.add_argument("--n", type=int, default=0, help="批量跑：对前 N 个任务各测一组预算")
    args = p.parse_args(argv)

    if args.self_test:
        _self_test()
        return 0

    # 默认一组预算，覆盖「想太少 / 刚好 / 想过头」
    demo_budgets = [50, 200, 500, 1100, 3000, 8000, 20000]

    if args.n > 0:
        names = list(TASKS)[: args.n]
        run_batch(names, demo_budgets)
        return 0

    # 默认：只演示最有反差的两个任务
    run_batch(["加法-1+1", "小学数学应用-GSM"], demo_budgets)
    return 0


if __name__ == "__main__":
    sys.exit(main())
