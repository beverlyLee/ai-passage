#!/usr/bin/env python3
# 语义缓存最小可复现：缓存引擎核心（纯标准库，免 API key）
#
# 模拟 GPTCache 式的三层读取：
#   L1 精确缓存（SHA256 归一化串，命中即跳过 LLM）
#   L2 语义缓存（词袋向量 + 余弦相似度 + 可调阈值 τ）
#   写回（命中则跳过 LLM，未命中才调用并写回）
#
# 同时演示三类致命失败模式：
#   假阳性（相似但意图不同，如今天 vs 明天）
#   TTL 过期（过期条目被当作未命中重新调用 LLM）
#   LRU 驱逐（超过容量上限，最久未用被淘汰）
#
# 运行：
#   python semantic_cache_core.py            # 跑演示并打印可读结果
#   python semantic_cache_core.py --self-test  # 断言内部不变量，全过则退出 0
#
# 注意：本脚本用「词袋向量」代替真实 embedding 模型，只为把缓存架构本身跑通。
#       真实系统的相似度来自稠密向量（如 all-MiniLM-L6-v2 / text-embedding-3），
#       阈值也随向量空间密度而变。文中所有数字均由本脚本实际运行产生。

import argparse
import hashlib
import math
import re
import time
from collections import OrderedDict, defaultdict


def normalize(text):
    # 去噪：小写、去标点、压缩空白。真实系统还会做 PII 脱敏、模板归一、语种识别。
    t = text.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def exact_key(text):
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def tokenize(text):
    # 中文没有空格，若按空白切会整句成一个 token。这里把 ASCII 词保留，
    # 连续 CJK 拆成单字，得到一个对中文也合理的词袋。真实系统用 embedding。
    norm = normalize(text)
    return re.findall(r"[a-z0-9]+|[一-鿿]", norm)


def vectorize(text):
    # 简化词袋。真实系统用 embedding 模型产出稠密向量，这里仅演示架构与阈值逻辑。
    vec = defaultdict(float)
    for tok in tokenize(text):
        vec[tok] += 1.0
    return vec


def cosine(a, b):
    common = set(a) & set(b)
    num = sum(a[k] * b[k] for k in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return num / (na * nb)


class SemanticCache:
    def __init__(self, threshold=0.85, ttl=3600.0, max_size=128,
                 llm_cost=0.002, clock=None):
        self.threshold = threshold      # 相似度命中阈值 τ
        self.ttl = ttl                  # 条目存活秒数
        self.max_size = max_size        # L2 语义缓存容量上限（LRU）
        self.llm_cost = llm_cost        # 每次 LLM 调用的示意成本（美元）
        self.clock = clock if clock is not None else time.time
        self.exact = {}                 # key -> (response, expires_at)
        self.sem = OrderedDict()        # norm -> (vector, response, expires_at)
        self.stats = {
            "exact_hit": 0,
            "sem_hit": 0,
            "miss": 0,
            "llm_calls": 0,
            "cost_saved": 0.0,
        }

    def _expired(self, expires_at):
        return self.clock() > expires_at

    def _fake_llm(self, query):
        # 确定性 mock 回答。真实场景这里调 GPTCache 后端或直连 LLM。
        return "LLM回答: " + query

    def get(self, query):
        k = exact_key(query)
        # L1 精确缓存
        if k in self.exact:
            resp, exp = self.exact[k]
            if not self._expired(exp):
                self.stats["exact_hit"] += 1
                self.stats["cost_saved"] += self.llm_cost
                return resp, "exact"
            del self.exact[k]
        # L2 语义缓存
        qvec = vectorize(query)
        best_sim = -1.0
        best_resp = None
        best_key = None
        for norm, (vec, resp, exp) in self.sem.items():
            if self._expired(exp):
                continue
            sim = cosine(qvec, vec)
            if sim > best_sim:
                best_sim = sim
                best_resp = resp
                best_key = norm
        if best_resp is not None and best_sim >= self.threshold:
            self.sem.move_to_end(best_key)   # LRU 刷新
            self.stats["sem_hit"] += 1
            self.stats["cost_saved"] += self.llm_cost
            return best_resp, "semantic"
        # 未命中：调 LLM 并写回
        self.stats["miss"] += 1
        self.stats["llm_calls"] += 1
        resp = self._fake_llm(query)
        now = self.clock()
        self.exact[k] = (resp, now + self.ttl)
        norm = normalize(query)
        self.sem[norm] = (qvec, resp, now + self.ttl)
        while len(self.sem) > self.max_size:
            old_norm, _ = self.sem.popitem(last=False)   # 淘汰最久未用
            self.exact.pop(exact_key(old_norm), None)     # L1 同步失效，避免精确层无限增长
        return resp, "miss"

    def hit_rate(self):
        total = (self.stats["exact_hit"] + self.stats["sem_hit"]
                 + self.stats["miss"])
        if total == 0:
            return 0.0
        return (self.stats["exact_hit"] + self.stats["sem_hit"]) / total


def run_demo():
    print("=== 语义缓存引擎核心演示（阈值 tau=0.85）===\n")
    cache = SemanticCache(threshold=0.85, ttl=3600.0)

    cold = [
        "Python 入门教程推荐",
        "深度学习需要什么显卡",
        "北京今天天气怎么样",
        "怎么用 Redis 做缓存",
        "Transformer 和 RNN 区别",
    ]
    print("[第一轮：冷启动，全部未命中，调用 LLM]\n")
    for q in cold:
        resp, src = cache.get(q)
        print("  Q: %s\n     -> %-8s | %s" % (q, src.upper(), resp))

    warm = [
        "Python 入门教程推荐",       # 精确命中
        "Python 入门教程推荐一下",     # 语义命中（近义追加，cos>=0.85）
        "北京今天天气怎么样",         # 精确命中
        "怎么用 Redis 做缓存",        # 精确命中
        "Transformer 和 RNN 区别",    # 精确命中
    ]
    print("\n[第二轮：热启动，重复与近义查询]\n")
    for q in warm:
        resp, src = cache.get(q)
        print("  Q: %s\n     -> %-8s | %s" % (q, src.upper(), resp))

    near = "Python 进阶教程推荐"      # 入门改进阶，关键词变了，低于阈值 -> 未命中
    resp, src = cache.get(near)
    print("\n[近义但改了关键词]\n  Q: %s\n     -> %-8s | %s" % (near, src.upper(), resp))

    print("\n[汇总统计]")
    s = cache.stats
    print("  精确命中 %d  语义命中 %d  未命中 %d"
          % (s["exact_hit"], s["sem_hit"], s["miss"]))
    print("  命中率 %.2f" % cache.hit_rate())
    print("  LLM 调用 %d 次，示意节省成本 $%.3f"
          % (s["llm_calls"], s["cost_saved"]))


def demo_false_positive():
    print("\n=== 假阳性陷阱：连运营阈值 0.85 都把『今天』和『明天』当同题 ===\n")
    cache = SemanticCache(threshold=0.85, ttl=3600.0)   # 就用运营阈值，证明这个坑不是调低才出现
    q_today = "北京今天天气怎么样"
    resp_today, _ = cache.get(q_today)
    q_tomorrow = "北京明天天气怎么样"
    resp_tomorrow, src = cache.get(q_tomorrow)
    print("  先问: %s\n    缓存(LLM) -> %s" % (q_today, resp_today))
    print("  再问: %s\n    命中来源 %s -> 返回 %s"
          % (q_tomorrow, src.upper(), resp_tomorrow))
    collision = ("今天" in resp_tomorrow) and ("明天" in q_tomorrow)
    print("  假阳性判定: %s"
          % ("发生碰撞，把问今天的人得到的答案答给了问明天的人" if collision else "未碰撞"))
    return collision


def demo_ttl():
    print("\n=== TTL 失效：过期条目被当作未命中，重新调用 LLM ===\n")
    seq = {"t": 0.0}

    def clock():
        return seq["t"]

    cache = SemanticCache(threshold=0.85, ttl=100.0, clock=clock)
    q = "Redis 怎么设置过期"
    cache.get(q)                                  # 写入，expires_at = 100
    calls_after_first = cache.stats["llm_calls"]
    seq["t"] = 200.0                              # 时间推进到过期之后
    resp, src = cache.get(q)                       # 应未命中，重新调用
    print("  写入时刻 t=0，TTL=100；查询时刻 t=200")
    print("  第二次查询来源 %s，LLM 调用计数 %d" % (src.upper(), cache.stats["llm_calls"]))
    expired_ok = (src == "miss") and (cache.stats["llm_calls"] == calls_after_first + 1)
    print("  TTL 生效判定: %s" % ("是" if expired_ok else "否"))
    return expired_ok


def demo_lru():
    print("\n=== LRU 驱逐：超过最大容量，最久未用被淘汰 ===\n")
    cache = SemanticCache(threshold=0.85, ttl=3600.0, max_size=2)
    for q in ["问题一", "问题二", "问题三"]:
        cache.get(q)                              # 三次冷启动，容量 2 -> 问题一被驱逐
    calls = cache.stats["llm_calls"]
    resp, src = cache.get("问题一")                # 被驱逐，应未命中
    print("  容量上限 2，写入 3 条后重新查询『问题一』")
    print("  来源 %s，LLM 调用计数 %d" % (src.upper(), cache.stats["llm_calls"]))
    evicted_ok = (src == "miss") and (cache.stats["llm_calls"] == calls + 1)
    print("  LRU 生效判定: %s" % ("是" if evicted_ok else "否"))
    return evicted_ok


def self_test():
    # 1. 精确命中不重复调用 LLM
    c = SemanticCache(threshold=0.85)
    c.get("同一句话")
    calls1 = c.stats["llm_calls"]
    c.get("同一句话")
    assert c.stats["exact_hit"] == 1
    assert c.stats["llm_calls"] == calls1 == 1
    print("self-test [1] 精确命中: PASS")

    # 2. 近义语义命中返回同一响应
    c2 = SemanticCache(threshold=0.85)
    r1, _ = c2.get("Python 入门教程推荐")
    r2, src = c2.get("Python 入门教程推荐一下")
    assert src == "semantic"
    assert r2 == r1
    print("self-test [2] 语义命中: PASS")

    # 3. 改关键词低于阈值 -> 未命中
    c3 = SemanticCache(threshold=0.85)
    c3.get("Python 入门教程推荐")
    r3, src3 = c3.get("Python 进阶教程推荐")
    assert src3 == "miss"
    print("self-test [3] 阈值拦截近义变体: PASS")

    # 4. 假阳性：低阈值下今天/明天碰撞
    assert demo_false_positive() is True
    print("self-test [4] 假阳性陷阱: PASS")

    # 5. TTL 过期重新调用
    assert demo_ttl() is True
    print("self-test [5] TTL 失效: PASS")

    # 6. LRU 驱逐
    assert demo_lru() is True
    print("self-test [6] LRU 驱逐: PASS")

    print("\nALL SELF-TESTS PASSED")
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        return self_test()
    run_demo()
    demo_false_positive()
    demo_ttl()
    demo_lru()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
