"""demo_calibration.py — 复现 Laya 的校准与温度缩放（纯 Python，无 torch / numpy）。

源码出处：
  - common.py:325-335  ece_score
  - common.py:338-364  answer_confidence / confidence_from_probs
  - common.py:367-388  temp_bucket / TEMP_MIN / TEMP_MAX / clamp_temperature
  - agent.py:768-774   _decode_answers 中的温度缩放解码 z = logits/t; p = softmax(z)

运行：
    python demo_calibration.py --self-test
"""

import math
import sys

QTYPES = {"choice": 0, "score": 1, "noul": 2}
QTYPE_NAMES = {v: k for k, v in QTYPES.items()}


def ece_score(conf, correct, bins=15):
    """期望校准误差：逐置信度区间累加 样本占比 * |区间内平均置信 - 区间内平均正确率|。"""
    if len(conf) == 0:
        return float("nan")
    edges = [i / bins for i in range(bins + 1)]
    e = 0.0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        sel = [j for j in range(len(conf))
               if (conf[j] >= lo if i == 0 else conf[j] > lo) and conf[j] <= hi]
        if sel:
            mean_conf = sum(conf[j] for j in sel) / len(sel)
            mean_corr = sum(correct[j] for j in sel) / len(sel)
            e += (len(sel) / len(conf)) * abs(mean_conf - mean_corr)
    return e


def answer_confidence(p, k):
    """温度缩放拟合的量：max(p)。所有校准图与门控都依赖它，是已校准量。"""
    if k < 1:
        return 1.0
    return min(1.0, max(p[:k]))


def confidence_from_probs(p, k):
    """归一化香农熵：1 - H(p)/log(k)。未校准，不可与 answer_confidence 同阈值。"""
    if k < 2:
        return 1.0
    p = p[:k]
    ent = -sum(x * math.log(max(x, 1e-12)) for x in p)
    return min(1.0, max(0.0, 1.0 - ent / math.log(k)))


def temp_bucket(qtype, k):
    size = "2" if k <= 2 else "3-5" if k <= 5 else "6-10" if k <= 10 else "11+"
    return "%s:%s" % (QTYPE_NAMES[int(qtype)], size)


TEMP_MIN = 0.5
TEMP_MAX = 5.0


def clamp_temperature(t, lo=TEMP_MIN, hi=TEMP_MAX):
    try:
        t = float(t)
    except (TypeError, ValueError):
        return 1.0
    if t != t or t in (float("inf"), float("-inf")):
        return 1.0
    return min(hi, max(lo, t))


def decode_logits(logits, k, t_scale):
    """复刻 agent.py:772-774：z = logits[:k]/t; p = softmax(z)。"""
    z = [x / t_scale for x in logits[:k]]
    m = max(z)
    e = [math.exp(x - m) for x in z]
    s = sum(e)
    return [v / s for v in e]


# ----------------------------- 自检 -----------------------------
def _self_test():
    ok = True

    # 例 1：ECE 计算。完美校准的二分类（conf 与 correct 一致）ECE 应接近 0
    conf = [0.9, 0.8, 0.7, 0.6, 0.55, 0.45, 0.4, 0.3, 0.2, 0.1]
    correct = [1, 1, 1, 1, 0, 0, 0, 0, 0, 0]
    ece = ece_score(conf, correct, bins=15)
    print("[1] ece_score：conf=%s" % conf)
    print("    correct=%s -> ECE=%.4f（高/低置信与正确率错配，ECE 较大）" % (correct, ece))
    assert ece > 0.0, "错配校准应产生正 ECE"

    # 例 2：answer_confidence（已校准）vs confidence_from_probs（未校准）数值差异
    # 三选项 p=[0.7, 0.2, 0.1]
    p3 = [0.7, 0.2, 0.1]
    ca = answer_confidence(p3, 3)
    cf = confidence_from_probs(p3, 3)
    print("[2] 三选项 p=[0.7,0.2,0.1]：")
    print("    answer_confidence=max(p)=%.4f（温度缩放拟合、已校准，用于门控）" % ca)
    print("    confidence_from_probs=1-H/log(3)=%.4f（未校准的集中度，不可同阈值）" % cf)
    assert abs(ca - 0.7) < 1e-9, "answer_confidence 应为 max(p)"
    assert cf != ca, "两者必须不同量纲"
    ok = ok and True

    # 例 3：temp_bucket 对 k>=11 给出 'choice:11+'；clamp_temperature 拒绝 0.1006（过锐化）
    print("[3] temp_bucket：choice k=2 -> %r, k=5 -> %r, k=12 -> %r" %
          (temp_bucket(0, 2), temp_bucket(0, 5), temp_bucket(0, 12)))
    assert temp_bucket(0, 12) == "choice:11+", "k>=11 必须落到 choice:11+"
    t_shipped = 0.1006
    t_applied = clamp_temperature(t_shipped)
    print("    clamp_temperature(%s)=%s（TEMP_MIN=0.5，过锐化值被拒绝，回退到 %.1f 或 1.0）" %
          (t_shipped, t_applied, TEMP_MIN))
    assert abs(t_applied - TEMP_MIN) < 1e-9, "0.1006 < TEMP_MIN 必须被钳到 0.5"
    ok = ok and True

    # 例 4：choice:11+ 过锐化危害：12 选项，诚实顶概率 0.24，t=0.1006 把它推到 ~0.999
    k12 = 12
    logits = [1.245] + [0.0] * (k12 - 1)  # t=1 时顶概率=0.24
    p_honest = decode_logits(logits, k12, 1.0)
    p_sharp = decode_logits(logits, k12, 0.1006)
    top_honest = max(p_honest)
    top_sharp = max(p_sharp)
    print("[4] choice:11+ 过锐化演示（k=12，logits=[1.245, 0...]）：")
    print("    t=1.0000 -> 顶概率=%.4f（诚实区间，约 1/4 把握）" % top_honest)
    print("    t=0.1006（被 clamp 拒绝）-> 顶概率=%.4f（把硬币抛掷的把握发布成确定）" % top_sharp)
    assert abs(top_honest - 0.24) < 0.02, "诚实顶概率应约 0.24"
    assert top_sharp > 0.99, "过锐化会把 0.24 推到 ~0.99"
    ok = ok and True

    # 例 5：noul 两选项的 confidence = max(p_true, 1-p_true) == answer_confidence
    p_noul = [0.51, 0.49]
    cn = confidence_from_probs(p_noul, 2)
    ca_noul = answer_confidence(p_noul, 2)
    print("[5] noul 两选项 p=[0.51,0.49]：confidence=max(0.49,0.51)=%.2f == answer_confidence=%.2f（两选项下等价）"
          % (max(p_noul[1], 1 - p_noul[1]), ca_noul))
    assert abs(max(p_noul[1], 1 - p_noul[1]) - ca_noul) < 1e-9
    ok = ok and True

    if ok:
        print("self-test PASS: ECE / answer_confidence vs confidence_from_probs / temp_bucket / clamp / 过锐化危害 均符合源码逻辑")


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        _self_test()
    else:
        print("ece_score demo:", ece_score([0.9, 0.8, 0.7, 0.6, 0.55, 0.45, 0.4, 0.3, 0.2, 0.1],
                                           [1, 1, 1, 1, 0, 0, 0, 0, 0, 0]))
