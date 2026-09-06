#!/usr/bin/env python3
# mcp_budget.py —— 扫描 MCP server 工具定义占用的上下文预算
# 用法: python3 02-mcp-budget.py ~/.cursor/mcp.json --window 200000
import json, sys, argparse


def est_tokens(s: str) -> int:
    # 粗估：英文按 4 字符/token，CJK 按 1.5 字符/token
    cjk = sum(1 for c in s if '\u4e00' <= c <= '\u9fff')
    return int((len(s) - cjk) / 4 + cjk / 1.5) + 1


def describe(tool: dict) -> str:
    name = tool.get('name', '')
    desc = tool.get('description', '')
    params = json.dumps(tool.get('inputSchema', {}), ensure_ascii=False)
    return f"{name}\n{desc}\n{params}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('config')
    ap.add_argument('--window', type=int, default=200_000)
    ap.add_argument('--budget', type=float, default=0.10, help='工具定义允许的窗口占比')
    a = ap.parse_args()

    cfg = json.load(open(a.config, encoding='utf-8'))
    servers = cfg.get('mcpServers', cfg)
    rows, total = [], 0
    for sname, sconf in servers.items():
        # 支持本地已缓存的工具清单，或退化为按 server 名粗估
        tools = sconf.get('tools') if isinstance(sconf, dict) else None
        if tools:
            cost = sum(est_tokens(describe(t)) for t in tools)
        else:
            cost = est_tokens(json.dumps(sconf, ensure_ascii=False))
        rows.append((sname, len(tools or []), cost))
        total += cost

    rows.sort(key=lambda r: -r[2])
    print(f"window={a.window:,}  budget={a.budget:.0%}  = {int(a.window*a.budget):,} tokens\n")
    print(f"{'server':<28}{'tools':>7}{'tokens':>10}{'%win':>8}{'%budget':>9}")
    for sname, n, cost in rows:
        print(f"{sname:<28}{n:>7}{cost:>10,}{cost/a.window:>8.1%}{cost/int(a.window*a.budget):>9.1%}")
    print(f"\nTOTAL {total:,} tokens = {total/a.window:.1%} of window")

    if total > a.window * a.budget:
        over = [s for s, _, c in rows if c > a.window * a.budget / max(len(rows), 1)]
        print(f"\n[FAIL] 工具定义超出 {a.budget:.0%} 预算。建议按会话剪枝，优先摘除：")
        for s in over[:5]:
            print(f"  - {s}")
        sys.exit(1)
    print("\n[PASS] 工具定义在预算内")


if __name__ == '__main__':
    main()
