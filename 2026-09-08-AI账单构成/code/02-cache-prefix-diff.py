#!/usr/bin/env python3
"""02-cache-prefix-diff.py — 找出让 prompt 前缀漂移的第一个位置。

对应文章「问题 3（治缓存没吃上）」：缓存是精确前缀匹配，
前缀里动一个 token，后面全部失效。本脚本对比连续两次请求的
prompt（文本文件），定位第一个分叉点，并判断共同前缀是否
达到了厂商的最小可缓存长度（低于会静默不缓存）。

用法：
  python3 02-cache-prefix-diff.py req1.txt req2.txt --provider anthropic
  python3 02-cache-prefix-diff.py req1.txt req2.txt --provider openai

provider 支持 anthropic / openai / gemini3（最小前缀分别约
1024 / 1024 / 4096 token；粗估按 4 字符 ≈ 1 token，中文按
1.5 字符 ≈ 1 token，仅供结构判断，不是精确 tokenizer）。
"""
import argparse
import sys

MIN_PREFIX = {
    "anthropic": 1024,
    "openai": 1024,
    "gemini3": 4096,
}


def est_tokens(text: str) -> int:
    """粗估 token 数：CJK 按约 1.5 字符/token，其他按 4 字符/token。"""
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return int(cjk / 1.5 + other / 4)


def first_divergence(a: str, b: str):
    """返回第一个分叉的字符位置与上下文片段。"""
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n if len(a) != len(b) else None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("req1")
    ap.add_argument("req2")
    ap.add_argument("--provider", default="anthropic", choices=list(MIN_PREFIX))
    args = ap.parse_args()

    a = open(args.req1, encoding="utf-8").read()
    b = open(args.req2, encoding="utf-8").read()

    pos = first_divergence(a, b)
    common = a if pos is None else a[:pos]
    common_tokens = est_tokens(common)
    min_tok = MIN_PREFIX[args.provider]

    if pos is None:
        print("两次请求完全一致，全量可命中缓存。")
        return

    line_no = common.count("\n") + 1
    col = pos - (common.rfind("\n") + 1) + 1
    ctx = a[max(0, pos - 40):pos + 40].replace("\n", "\\n")

    print(f"第一个分叉位置：第 {line_no} 行第 {col} 列（字符偏移 {pos}）")
    print(f"共同前缀约 {common_tokens} token")
    print(f"分叉处上下文：…{ctx}…\n")

    if common_tokens < min_tok:
        print(f"[!] 共同前缀低于 {args.provider} 的最小可缓存长度（{min_tok} token），"
              f"即使前缀稳定也【静默不缓存】，不报错。")
    else:
        print(f"[OK] 共同前缀达到 {min_tok} token 门槛，"
              f"把分叉点之后的内容移到 prompt 末尾即可恢复命中。")

    # 常见元凶提示
    culprits = []
    for pat, name in [("timestamp", "时间戳"), ("uuid", "UUID"),
                      ("random", "随机数"), ("Date(", "动态日期")]:
        if pat in a[pos:pos + 400] or pat in b[pos:pos + 400]:
            culprits.append(name)
    if culprits:
        print(f"[!] 分叉点附近疑似出现：{'、'.join(culprits)}。"
              f"动态内容一律放 prompt 末尾，或整个删掉。")


if __name__ == "__main__":
    sys.exit(main())
