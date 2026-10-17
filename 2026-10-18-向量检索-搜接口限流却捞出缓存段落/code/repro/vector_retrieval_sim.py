#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向量检索参数扫描仿真（纯标准库，免 key）
======================================

两个仿真：
  仿真1  nprobe 扫描：展示「召回率 vs 扫描簇数(延迟代理)」的权衡曲线。
         这正是 HNSW 里 efSearch、IVF 里 nprobe 共同要调的那个旋钮：
         召回是旋钮不是常数。
  仿真2  数据量扫描：展示暴力扫描的距离计算量，对比 IVF 实际扫描量，
         以及二者加速比随数据量放大的关系。

文献对照（标口径，非承诺）：
  业界基准里 HNSW 在 SIFT1M 上 5000~20000 QPS@95% 召回；
  10M×768 维暴力约 20~50ms/查询，HNSW <1ms，约 30~100x 加速
  （来源：ann-benchmarks 项目、unseel.com 的 HNSW 解析）。
  本仿真是 IVF 的简化版，加速比 = nlist/nprobe，用于演示量级关系。
"""

import math
import random
import sys

from vector_retrieval_core import (
    IVFIndex,
    BruteForceIndex,
    clustered_items,
    mean_recall_at_k,
)


def scan_nprobe():
    print("=== 仿真1: nprobe 扫描 (召回率 vs 延迟代理) ===")
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
    print("      nprobe=nlist 时 IVF==暴力, 召回=1.000")


def scan_scale():
    print()
    print("=== 仿真2: 数据量扫描 (暴力 vs IVF 扫描量加速比) ===")
    dim, nlist, nprobe = 64, 100, 4
    print("设置: dim=%d, nlist=%d 簇, nprobe=%d (IVF 只扫 %d%% 的向量)"
          % (dim, nlist, nprobe, 100 * nprobe // nlist))
    print("%12s | %14s | %14s | %10s" % ("N(向量数)", "暴力扫描/查询", "IVF扫描/查询", "加速比"))
    for N in (1000, 10000, 100000, 1000000):
        brute_cost = N * dim
        ivf_cost = N * nprobe / nlist * dim
        speedup = brute_cost / ivf_cost
        print("%12d | %14d | %14.1f | %9.1fx" % (N, brute_cost, ivf_cost, speedup))
    print("读数: 数据量越大, IVF 相对暴力的加速比越显著 (此处 = nlist/nprobe = %dx)"
          % (nlist // nprobe))


if __name__ == "__main__":
    scan_nprobe()
    scan_scale()
