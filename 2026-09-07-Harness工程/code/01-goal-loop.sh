#!/usr/bin/env bash
# 01-goal-loop.sh — 目标循环骨架
# 对应文章问题 3 / 问题 4：Trigger / Goal / Verifier / 三个停止出口 + 每轮上下文重置
#
# 用法: ./01-goal-loop.sh "<任务指令>" [最大轮次] [预算上限(美元)]
# 依赖: claude CLI (或替换成任意 agent CLI)；GOAL_CMD 必须是可执行的确定性检查

set -u

TASK="${1:?用法: $0 \"<任务指令>\" [最大轮次] [预算上限美元]}"
MAX_TURNS="${2:-20}"
BUDGET_USD="${3:-5.00}"

# === Goal：必须是可验证的事实，不是愿望 ===
# 改成你自己的确定性检查。退出码 0 = 目标达成。
GOAL_CMD="npm test -- --run"          # 例：测试全绿
# GOAL_CMD="bash -c 'git status --porcelain | wc -l | grep -q ^0$'"   # 例：工作区干净

# === 状态放磁盘，不放上下文（外部持久化）===
STATE_DIR="$(pwd)/.goal-loop"
mkdir -p "$STATE_DIR"
LOG="$STATE_DIR/loop.log"
echo "loop start $(date '+%F %T') task=[$TASK] max_turns=$MAX_TURNS budget=$BUDGET_USD" >> "$LOG"

turn=0
while true; do
  turn=$((turn + 1))

  # --- 出口 1：成功（验证器确认，不是 agent 声明）---
  if eval "$GOAL_CMD" >/dev/null 2>&1; then
    echo "[$turn] SUCCESS: goal verified" >> "$LOG"
    echo "✅ 第 ${turn} 轮：目标达成（验证器确认）"
    exit 0
  fi

  # --- 出口 2：迭代上限 ---
  if [ "$turn" -gt "$MAX_TURNS" ]; then
    echo "[$turn] STOP: max turns exceeded" >> "$LOG"
    echo "⛔ 达到迭代上限 ${MAX_TURNS} 轮，硬停（人工介入）"
    exit 2
  fi

  # --- 出口 3：预算上限 ---
  spent=$("$STATE_DIR/../cost-report.sh" 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' || echo "0.00")
  if command -v bc >/dev/null 2>&1 && (( $(echo "$spent >= $BUDGET_USD" | bc -l) )); then
    echo "[$turn] STOP: budget $spent >= $BUDGET_USD" >> "$LOG"
    echo "⛔ 预算耗尽（已花 $spent / 上限 $BUDGET_USD），硬停"
    exit 3
  fi

  # --- 每轮全新上下文：状态在磁盘上，不在对话里（Ralph 模式）---
  echo "[$turn] running fresh-context pass..." >> "$LOG"
  claude -p "读当前仓库状态。目标：${TASK}
完成判据：'${GOAL_CMD}' 退出码 0。
只做推进目标的一个单元工作；若走不通，把原因追加到 ${STATE_DIR}/deadends.md（记录死胡同，防止重踩），
不要修改已有测试。做完即停。"

  echo "[$turn] pass done" >> "$LOG"
done
