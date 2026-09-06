#!/usr/bin/env bash
# ci/ai-diff-gate.sh —— 超大 AI diff 门禁：超阈值直接失败，强制拆分提交
# 用法: ./01-ai-diff-gate.sh [base-branch]
set -euo pipefail

BASE="${1:-origin/main}"
MAX_DIFF_LINES="${MAX_DIFF_LINES:-400}"   # 单个 PR 的净增行数上限
MAX_FILES="${MAX_FILES:-15}"              # 触及文件数上限

changed=$(git diff --name-only "$BASE"...HEAD | wc -l | tr -d ' ')
added=$(git diff --numstat "$BASE"...HEAD | awk '{a+=$1} END {print a+0}')

echo "AI diff gate: +$added lines across $changed files (limit +$MAX_DIFF_LINES / $MAX_FILES files)"

if [ "$added" -gt "$MAX_DIFF_LINES" ]; then
  echo "::error::净增 $added 行超过上限 $MAX_DIFF_LINES。审查带宽约为生成带宽的 1/8，请拆分提交。"
  exit 1
fi
if [ "$changed" -gt "$MAX_FILES" ]; then
  echo "::error::触及 $changed 个文件超过上限 $MAX_FILES，跨模块改动请分 PR 提交。"
  exit 1
fi

# 覆盖率只升不降：从 main 取基线，低于基线即失败
if [ -f coverage/coverage-summary.json ] && [ -f baseline-coverage.json ]; then
  cur=$(jq -r '.total.lines.pct' coverage/coverage-summary.json)
  base=$(jq -r '.total.lines.pct' baseline-coverage.json)
  echo "coverage: $cur% (baseline $base%)"
  if awk "BEGIN{exit !($cur < $base - 0.5)}"; then
    echo "::error::行覆盖率从 ${base}% 降到 ${cur}%，AI diff 不允许降低覆盖率。"
    exit 1
  fi
fi
echo "AI diff gate: PASS"
