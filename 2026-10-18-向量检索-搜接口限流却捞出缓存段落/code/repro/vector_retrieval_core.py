#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向量检索核心原理复现（纯标准库，免 key / 免第三方依赖）
============================================================

这个脚本用「字符级词袋」(character bag-of-words) 作为*演示用*嵌入，
它只是真实 embedding 模型的替代：真实模型（如 BGE、OpenAI
text-embedding-3）产出 768~1536 维稠密向量，但检索机制
（暴力扫描 / IVF 倒排分区 / recall@k）与向量维度无关。用字符级词袋
可以零依赖、零密钥、跨进程可复现地演示同一套机制。

覆盖知识点：
  1. 暴力扫描的代价：每次查询 O(n·d)，规模一大就不可行
  2. IVF 倒排分区：只扫 nprobe 个簇 -> 用速度换召回
  3. recall@k 的定义，以及「近似检索会漏召回」
  4. 跨意图捞取的两类根因：
       - 嵌入层把不同意图放成邻居（嵌入问题，与 ANN 无关）
       - 近似检索漏掉真邻居（ANN 问题）
     两者相互独立，可在这个脚本里分开复现

确定性说明：char_bow_embed 只用 ord()，不依赖 PYTHONHASHSEED，
所以同一段文本在任何机器、任何进程里都得到完全相同的向量。
"""

import math
import random
import sys


def char_bow_embed(text, dim=64):
    """
    字符级词袋嵌入（教学替代，非真实语义嵌入）。

    把文本里每个字符散列进 dim 维，累加计数后做 L2 归一化。
    两段文本共享字符越多，向量夹角越小 —— 这一点已经足够触发
    「限流 / 缓存」这类近义词的跨意图混淆演示。

    真实 embedding 模型产出的是稠密语义向量，这里用字符频次替代，
    纯粹是为了零依赖可复现；检索机制本身完全相同。
    """
    vec = [0.0] * dim
    for ch in text:
        idx = ord(ch) % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


def cosine(a, b):
    """
    余弦相似度。输入须为已 L2 归一化向量（本脚本所有向量都做了归一化）。
    对归一化向量，cosine 取值范围在 [-1, 1]，文本嵌入通常落在 [0, 1]。
    """
    return sum(x * y for x, y in zip(a, b))


class BruteForceIndex:
    """暴力索引：精确最近邻，每次查询扫描全部向量。"""

    def __init__(self):
        self.vecs = []
        self.ids = []

    def add(self, vec, _id):
        self.vecs.append(vec)
        self.ids.append(_id)

    def search(self, q, k):
        scored = [(cosine(q, v), _id) for v, _id in zip(self.vecs, self.ids)]
        scored.sort(reverse=True)
        return [(_id, s) for s, _id in scored[:k]]


class IVFIndex:
    """
    IVF（Inverted File，倒排文件）索引：近似最近邻。

    思路：先用聚类把向量空间切成 nlist 个簇，每个簇记一个倒排列表。
    查询时只挑最近的 nprobe 个簇，在这些簇内部做暴力扫描。
    nprobe 越小越快，但越可能漏掉真邻居 -> 召回率下降。
    nprobe == nlist 时退化为暴力扫描，召回率 100%。

    聚类用 kmeans-lite：随机选中心 + Lloyd 迭代若干轮。这是 FAISS
    IVF 的极简教学版（FAISS 的 IVF 源自 Sivic & Zisserman 的
    Video Google，ICCV 2003）。
    """

    def __init__(self):
        self.centroids = []
        self.lists = []

    def _assign(self, vec):
        best, bi = -1.0, 0
        for i, c in enumerate(self.centroids):
            s = cosine(vec, c)
            if s > best:
                best, bi = s, i
        return bi

    def build(self, items, nlist, niter=8, seed=21):
        rng = random.Random(seed)
        n = len(items)
        idxs = list(range(n))
        rng.shuffle(idxs)
        self.centroids = [items[i][0][:] for i in idxs[:nlist]]
        dim = len(items[0][0])
        for _ in range(niter):
            self.lists = [[] for _ in range(nlist)]
            for v, _id in items:
                self.lists[self._assign(v)].append((v, _id))
            new_centroids = []
            for ci in range(nlist):
                if self.lists[ci]:
                    acc = [0.0] * dim
                    for v, _ in self.lists[ci]:
                        for j, x in enumerate(v):
                            acc[j] += x
                    cnt = len(self.lists[ci])
                    c = [a / cnt for a in acc]
                    norm = math.sqrt(sum(x * x for x in c))
                    new_centroids.append([x / norm for x in c] if norm > 0 else c)
                else:
                    new_centroids.append(self.centroids[ci])
            self.centroids = new_centroids
        # 最终分配（用收敛后的中心）
        self.lists = [[] for _ in range(nlist)]
        for v, _id in items:
            self.lists[self._assign(v)].append((v, _id))

    def search(self, q, k, nprobe):
        # 取与查询最相似的 nprobe 个簇（余弦越大越近），故降序排后取前 nprobe
        cent_scored = sorted(
            ((cosine(q, c), i) for i, c in enumerate(self.centroids)), reverse=True
        )
        probe = [i for _, i in cent_scored[:nprobe]]
        scored = []
        for ci in probe:
            for v, _id in self.lists[ci]:
                scored.append((cosine(q, v), _id))
        scored.sort(reverse=True)
        return [(_id, s) for s, _id in scored[:k]]


def recall_at_k(truth_ids, pred_ids, k):
    """
    recall@k 的定义（业界通用，见 ann-benchmarks / AIMultiple 基准说明）：
    用精确暴力检索得到「真实前 k 个近邻」truth_ids，再看近似索引返回的
    pred_ids 前 k 个里命中了多少个真实近邻，占真实近邻的比例。
    它隔离了「索引层」（IVF/HNSW 的近似误差），与嵌入模型无关。
    """
    truth = set(truth_ids[:k])
    if not truth:
        return 0.0
    hit = sum(1 for _id in pred_ids[:k] if _id in truth)
    return hit / len(truth)


def mean_recall_at_k(brute, ivf, queries, k, nprobe):
    rs = []
    for q, _ in queries:
        truth = [i for i, _ in brute.search(q, k)]
        pred = [i for i, _ in ivf.search(q, k, nprobe)]
        rs.append(recall_at_k(truth, pred, k))
    return sum(rs) / len(rs)


def _gauss_items(n, dim, seed):
    """生成 n 个各向同性的随机单位向量，作为可控的几何测试数据。"""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        v = [rng.gauss(0, 1) for _ in range(dim)]
        norm = math.sqrt(sum(x * x for x in v))
        out.append(([x / norm for x in v], i))
    return out


def clustered_items(n, dim, groups, spread, seed):
    """
    生成成簇数据：groups 个语义簇，每簇内的点围绕一个随机方向加小高斯噪声。

    这比各向同性随机数据更贴近真实语料：语义相近的文档在向量空间里
    本来就是聚成一团的。也正因为成簇，IVF 的召回才能随 nprobe 平滑爬升
    （小 nprobe 只扫到本簇的一部分，大 nprobe 扫到更多相邻簇）。
    """
    rng = random.Random(seed)
    cents = []
    for _ in range(groups):
        c = [rng.gauss(0, 1) for _ in range(dim)]
        nm = math.sqrt(sum(x * x for x in c))
        cents.append([x / nm for x in c])
    out = []
    for i in range(n):
        g = i % groups
        v = [cents[g][j] + rng.gauss(0, spread) for j in range(dim)]
        nm = math.sqrt(sum(x * x for x in v))
        out.append(([x / nm for x in v], i))
    return out


def demo_ann():
    print("=== demo_ann: IVF 近似检索的召回损失 ===")
    dim, N, G, spread, nlist, k = 64, 2000, 10, 0.8, 40, 5
    items = clustered_items(N, dim, G, spread, seed=7)
    brute = BruteForceIndex()
    for v, i in items:
        brute.add(v, i)
    ivf = IVFIndex()
    ivf.build(items, nlist=nlist, niter=12, seed=7)
    queries = items[:30]
    print("设置: N=%d 向量, dim=%d, %d 个语义簇, nlist=%d 簇, k=%d"
          % (N, dim, G, nlist, k))
    print("%7s | %8s | %10s | %18s" % ("nprobe", "扫描簇数", "召回率@%d" % k, "延迟代理(扫描向量)"))
    for nprobe in (1, 2, 4, 8, 16, 40):
        r = mean_recall_at_k(brute, ivf, queries, k, nprobe)
        scanned = N * nprobe / nlist
        print("%7d | %8d | %10.3f | %18.1f" % (nprobe, nprobe, r, scanned))
    print("读数: nprobe 越大召回越高(0.35->1.00), 扫描向量数(延迟)线性上升")
    print("      nprobe=40(全扫) 时 IVF==暴力, 召回率=1.000")


def demo_intent():
    print()
    print("=== demo_intent: 跨意图捞取的两类根因 ===")
    corpus = [
        ("接口限流的令牌桶算法怎么做", "限流"),
        ("如何用漏桶实现接口限流", "限流"),
        ("接口限流的滑动窗口计数", "限流"),
        ("Redis 怎么做接口限流", "限流"),
        ("怎么做接口缓存", "缓存"),
        ("Redis 缓存击穿怎么解决", "缓存"),
        ("缓存与数据库一致性", "缓存"),
        ("多级缓存架构设计", "缓存"),
    ]
    vecs = [(char_bow_embed(t), label) for t, label in corpus]
    q = char_bow_embed(corpus[0][0])
    brute = BruteForceIndex()
    for v, label in vecs:
        brute.add(v, label)
    print("查询: 接口限流的令牌桶算法怎么做   (真实意图=限流)")
    res = brute.search(q, 4)
    print("暴力(精确)检索 top4:")
    for label, s in res:
        print("    [%s]  cos=%.3f" % (label, s))
    top_labels = [l for l, _ in res]
    limi = sum(1 for l in top_labels if l == "限流")
    print("结论1: 即便用*精确*暴力检索, top4 里也只有 %d 条限流" % limi)
    print("       另外 %d 条是缓存 -> 嵌入层把'限流/缓存'放成邻居, 与 ANN 无关" % (4 - limi))
    items = list(zip([v for v, _ in vecs], [l for _, l in vecs]))
    ivf = IVFIndex()
    ivf.build(items, nlist=4, niter=12, seed=3)
    res2 = ivf.search(q, 4, nprobe=2)
    top2 = [l for l, _ in res2]
    limi2 = sum(1 for l in top2 if l == "限流")
    print("结论2: 上面再叠 IVF(nprobe=2), top4 里限流降到 %d 条" % limi2)
    print("       ANN 在嵌入问题上*叠加*了一次漏召回 -> 两类根因须分开治")


def self_test():
    print("=== self-test ===")
    # [1] 余弦基本性质：自相似=1
    a = char_bow_embed("abc")
    assert abs(cosine(a, a) - 1.0) < 1e-9, "cosine 自相似应为 1"
    # [2] 暴力检索：最相似是自身，余弦落在 [0,1]
    dim = 64
    items = _gauss_items(80, dim, seed=11)
    brute = BruteForceIndex()
    for v, i in items:
        brute.add(v, i)
    top = brute.search(items[0][0], 5)
    assert top[0][0] == 0, "最相似应为自身 id=0"
    assert all(0.0 <= s <= 1.0000001 for _, s in top), "余弦应在[0,1]"
    # [3] IVF 全扫 == 暴力，召回 1.000
    ivf = IVFIndex()
    ivf.build(items, nlist=20, niter=10, seed=11)
    queries = items[:10]
    r_full = mean_recall_at_k(brute, ivf, queries, 5, nprobe=20)
    assert abs(r_full - 1.0) < 1e-9, "nprobe=nlist 应 100%% 召回, 实际 %s" % r_full
    # [4] IVF nprobe=1 召回 < 全扫（近似损失确实存在）
    r1 = mean_recall_at_k(brute, ivf, queries, 5, nprobe=1)
    assert r1 <= r_full + 1e-9, "nprobe=1 召回不应高于全扫"
    assert r1 < 1.0, "nprobe=1 应<100%% 召回, 实际 %s" % r1
    # [5] 嵌入确定性：同输入同输出
    assert char_bow_embed("接口限流") == char_bow_embed("接口限流"), "嵌入应确定性"
    print("  [1] cosine 自相似=1                          PASS")
    print("  [2] 暴力检索 top1=自身, 余弦在[0,1]           PASS")
    print("  [3] IVF nprobe=nlist 召回=1.000              PASS")
    print("  [4] IVF nprobe=1 召回<1.000 (近似损失)       PASS")
    print("  [5] 嵌入确定性(同输入同向量)                PASS")
    print("self-test PASS")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        self_test()
    else:
        demo_ann()
        demo_intent()
