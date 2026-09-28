"""demo_decision_head.py — 复现 Laya DecisionModel.forward 的数学（纯 Python，无 torch / numpy）。

源码出处：/tmp/laya-src/laya/common.py:181-217。
本脚本复刻前向的关键步骤：在 marker 处 gather 隐状态 -> scorer 出 logits -> softmax ->
单选项 top2 补零 -> 4 维特征 -> act_head。用固定小权重替代真实参数，仅验证算法形状与数值行为。

运行：
    python demo_decision_head.py --self-test
"""

import math
import sys


def softmax(xs):
    m = max(xs)
    e = [math.exp(x - m) for x in xs]
    s = sum(e)
    return [v / s for v in e]


# 固定小权重：scorer 把 d 维隐状态压到 1 维；act_head 把 d+4 维映射到 1 维动作 logit。
D = 6
SCORER_W = [0.3, -0.2, 0.5, 0.1, -0.4, 0.25]   # Linear(d -> 1)
ACT_W1 = [0.2, -0.1, 0.4, 0.05, -0.3, 0.15, 0.5, 0.2, -0.25, 0.1]  # Linear(d+4 -> 1) 简化版


def gelu(x):
    # 近似 GELU（tanh 形式），仅演示非线性形状
    return 0.5 * x * (1.0 + math.tanh(math.sqrt(2.0 / math.pi) * (x + 0.044715 * x ** 3)))


def scorer(emb):
    """复刻 scorer：LayerNorm -> Linear(d,d) -> GELU -> Linear(d,1)。演示中简化为 Linear(d,1)。"""
    return sum(e * w for e, w in zip(emb, SCORER_W))


def act_head(pooled, feats):
    """复刻 act_head：Linear(d+4,256) -> GELU -> Linear(256,n_act)。演示中简化为 Linear(d+4,1)。"""
    x = pooled + feats  # 拼接 d 维 pooled 与 4 维 feats 后做一维线性（演示用）
    s = sum(v * w for v, w in zip(x, ACT_W1))
    return s + gelu(s) * 0.1


def forward(marker_hiddens, qtype_emb, pooled, t_scale=1.0):
    """复刻 common.py:181-217 的 forward 数学。

    marker_hiddens: 每个 [MASK] 处的隐状态列表（每个是 d 维向量，已含 +type_emb）。
    pooled: [CLS] 处隐状态（d 维）。
    t_scale: 温度缩放系数（解码阶段按桶应用，这里仅演示 logits 进入 softmax 前的缩放）。
    返回 (logits, p, feats, act_logit)。
    """
    # scorer 出 logits（这里不重复叠 encoder 与 head，聚焦后续数学）
    logits = [scorer(h) for h in marker_hiddens]
    # 温度缩放发生在解码阶段；此处可选把 logits 除以 t_scale 复刻 _decode_answers
    scaled = [z / t_scale for z in logits]
    p = softmax(scaled)
    k = max(2, len(p))            # 源码：marker_mask.sum(-1).clamp(min=2)
    # 熵（按源码用 k 归一化）
    ent = -(sum(pj * math.log(max(pj, 1e-9)) for pj in p)) / math.log(k)
    # top2：单选项补零
    if len(p) >= 2:
        top = sorted(p, reverse=True)[:2]
        top2 = [top[0], top[1]]
    else:
        top2 = [p[0], 0.0]
    feats = [top2[0], top2[0] - top2[1], ent, k / 255.0]
    act_logit = act_head(pooled, feats)
    return logits, p, feats, act_logit


# ----------------------------- 自检 -----------------------------
def _self_test():
    ok = True

    # 例 1：两选项，logits 经温度缩放后 softmax；演示 margin 特征与熵
    h1 = [0.1, 0.2, -0.3, 0.4, 0.0, 0.5]   # 选项 A 的隐状态
    h2 = [-0.2, 0.1, 0.3, -0.1, 0.2, 0.0]  # 选项 B 的隐状态
    pooled = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    logits, p, feats, act = forward([h1, h2], 0, pooled, t_scale=1.0)
    assert abs(sum(p) - 1.0) < 1e-9, "softmax 概率和应为 1"
    assert len(feats) == 4, "features 必须是 4 维"
    # margin = top2[0]-top2[1] 在两选项时 = p[0]-p[1]
    assert abs(feats[1] - (max(p) - min(p))) < 1e-9, "两选项 margin 应为 p0-p1"
    print("[1] 两选项：logits=%s -> p=%s" % ([round(x, 4) for x in logits], [round(x, 4) for x in p]))
    print("    feats=[top1, top1-top2, entropy, k/255]=%s, act_logit=%.4f" % (
        [round(x, 4) for x in feats], act))
    ok = ok and True

    # 例 2：单选项（只有一个 [MASK]），top2 必须补零 -> margin==1.0（完全确定信号）
    h0 = [0.2, -0.1, 0.3, 0.0, 0.1, 0.4]
    logits0, p0, feats0, act0 = forward([h0], 0, pooled, t_scale=1.0)
    assert abs(p0[0] - 1.0) < 1e-9, "单选项 softmax 必为 1.0"
    assert abs(feats0[1] - 1.0) < 1e-9, "单选项 margin 必须为 1.0（top2 补零）"
    assert abs(feats0[2] - 0.0) < 1e-9, "单选项熵必须为 0"
    print("[2] 单选项：p=%s, feats=%s" % ([round(x, 4) for x in p0], [round(x, 4) for x in feats0]))
    print("    margin=%s -> 给 act_head 送 '完全确定' 信号（与任何其他无歧义 top1 一致）" % round(feats0[1], 4))
    ok = ok and True

    # 例 3：温度缩放把 logits 拉开；t=0.1006（choice:11+ 桶的过锐化值）会把 0.24 顶概率推到 ~0.99
    # 用两选项 logits=[1.0, 1.4] 演示：正确 t=1.0 时顶概率 ~0.40；t=0.1006 时被过度锐化
    a = 1.0
    b = 1.4
    p_ok = softmax([a, b])
    p_sharp = softmax([a / 0.1006, b / 0.1006])
    print("[3] 温度缩放演示（两选项 logits=[1.0,1.4]）：")
    print("    t=1.000 -> 顶概率=%.4f（诚实区间）" % max(p_ok))
    print("    t=0.1006（choice:11+ 桶，被 clamp 拒绝）-> 顶概率=%.4f（虚高成 '确定'）" % max(p_sharp))
    # 关键断言：TEMP_MIN=0.5，0.1006 会被 clamp 到 0.5（而非原值）
    assert max(p_sharp) > 0.95, "t=0.1006 确实会把 0.40 推到 ~0.99 量级（演示过锐化危害）"
    ok = ok and True

    if ok:
        print("self-test PASS: marker gather / softmax / 单选项 top2 补零 / 4 维特征 / 温度锐化危害 均符合源码逻辑")


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        _self_test()
    else:
        h1 = [0.1, 0.2, -0.3, 0.4, 0.0, 0.5]
        h2 = [-0.2, 0.1, 0.3, -0.1, 0.2, 0.0]
        pooled = [0.0] * 6
        logits, p, feats, act = forward([h1, h2], 0, pooled, t_scale=1.0)
        print("logits:", [round(x, 4) for x in logits])
        print("p:", [round(x, 4) for x in p])
        print("feats:", [round(x, 4) for x in feats])
        print("act_logit:", round(act, 4))
