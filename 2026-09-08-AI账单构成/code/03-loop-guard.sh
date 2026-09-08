#!/bin/bash
# 03-loop-guard.sh — agent 循环的三重止损包装器。
#
# 对应文章「问题 4（治循环复利）」：agent 成本随轮次复合增长，
# 唯一可靠防线是硬上限。本脚本包住任意 agent 命令，任一条件
# 触发即终止并落盘报告：
#   1) 轮次上限      MAX_TURNS
#   2) 累计金额上限  MAX_COST_USD  （从 agent 输出里抓 usage 行）
#   3) 连续无进展    MAX_STALL    （最近 N 轮输出哈希完全相同）
#
# 用法：
#   MAX_TURNS=50 MAX_COST_USD=2.00 MAX_STALL=3 \
#     ./03-loop-guard.sh -- your-agent-command --task "refactor foo"
#
# 约定：agent 每轮输出到 stdout；若能打印 usage JSON（含
# total_cost_usd 或 output_tokens），脚本会累计金额；打印不了
# 就只能靠轮次和无进展止损（OpenAI 风格 API 在 usage 字段里有
# total_tokens，可自行接到你的 agent 上）。

set -u

MAX_TURNS="${MAX_TURNS:-50}"
MAX_COST_USD="${MAX_COST_USD:-2.00}"
MAX_STALL="${MAX_STALL:-3}"
REPORT="${REPORT:-loop-guard-report.txt}"

if [ "${1:-}" != "--" ] || [ $# -lt 2 ]; then
  echo "用法: $0 -- <agent 命令及参数>" >&2
  exit 2
fi
shift

turn=0
cost=0.0
last_hash=""
stall=0
: > "$REPORT"

log() { echo "[loop-guard] $*" | tee -a "$REPORT"; }

log "start: $*  (max_turns=$MAX_TURNS max_cost=\$$MAX_COST_USD max_stall=$MAX_STALL)"

while [ "$turn" -lt "$MAX_TURNS" ]; do
  turn=$((turn + 1))

  # --- 跑一轮，抓输出 ---
  out=$("$@" 2>&1) || { log "turn $turn: agent 退出码非 0，停止"; break; }
  echo "$out" | tail -5 >> "$REPORT"

  # --- 止损 2：累计金额 ---
  # 兼容两种输出：直接给 total_cost_usd，或给 token 数按 $3/15 口径粗折
  c=$(echo "$out" | grep -oE '"total_cost_usd"[[:space:]]*:[[:space:]]*[0-9.]+' \
        | tail -1 | grep -oE '[0-9.]+$' || true)
  if [ -n "${c:-}" ]; then
    cost=$(echo "$cost + $c" | bc)
  fi
  if echo "$cost" | awk -v m="$MAX_COST_USD" '{exit !($1 > m)}'; then
    log "STOP turn $turn: 累计成本 \$${cost} 超过上限 \$$MAX_COST_USD"
    break
  fi

  # --- 止损 3：连续无进展（输出完全相同） ---
  h=$(echo "$out" | shasum | cut -d' ' -f1)
  if [ "$h" = "$last_hash" ]; then
    stall=$((stall + 1))
  else
    stall=0
  fi
  last_hash="$h"
  if [ "$stall" -ge "$MAX_STALL" ]; then
    log "STOP turn $turn: 连续 $stall 轮输出无变化（原地打转），累计 \$$cost"
    break
  fi
done

if [ "$turn" -ge "$MAX_TURNS" ]; then
  log "STOP: 达到轮次上限 $MAX_TURNS，累计 \$$cost"
fi

log "done: turns=$turn cost=\$${cost} report=$REPORT"
# 报告存在且含 STOP 即视为被熔断，返回非零，方便 CI 感知
grep -q "STOP" "$REPORT" && exit 1 || exit 0
