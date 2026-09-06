#!/usr/bin/env bash
# ai-rework-rate.sh —— 统计 AI 标记提交的返工率与回滚率
# 约定：AI 生成的提交信息带 [ai] 前缀（或用 Co-authored-by: Claude 识别）
# 用法: ./03-ai-rework-rate.sh --since "90 days ago"
set -euo pipefail

SINCE="${SINCE:-90 days ago}"
AI_MARK="${AI_MARK:-'\[ai\]|Co-authored-by:.*(Claude|Copilot|Cursor)'}"
WINDOW_DAYS="${WINDOW_DAYS:-14}"   # 提交后多少天内的修改算返工

commits=$(git log --since="$SINCE" --pretty=format:'%H|%ad|%s' --date=short)
total_ai=0; reworked=0; reverted=0

while IFS='|' read -r sha date subject; do
  [ -z "$sha" ] && continue
  if ! echo "$subject" | grep -Eq "$AI_MARK" \
     && ! git show -s --format='%B' "$sha" | grep -Eq "$AI_MARK"; then
    continue
  fi
  total_ai=$((total_ai+1))

  # 返工：窗口内同一批文件被再次修改
  files=$(git show --pretty=format: --name-only "$sha" | grep -v '^$' | head -20 | paste -sd' ' -)
  [ -z "$files" ] && continue
  later=$(git log --since="$date" --until="$date +$WINDOW_DAYS days" \
          --pretty=format:'%H' -- $files 2>/dev/null | grep -v "$sha" | head -1 || true)
  [ -n "$later" ] && reworked=$((reworked+1))

  # 回滚：窗口内出现 revert
  git log --since="$date" --until="$date +$WINDOW_DAYS days" --pretty=format:'%s' \
    | grep -Eqi "revert.*${sha:0:7}|revert.*$(echo "$subject" | cut -c1-30)" \
    && reverted=$((reverted+1))
done <<< "$commits"

echo "AI 提交总数: $total_ai  (since $SINCE)"
[ "$total_ai" -eq 0 ] && { echo "无 AI 标记提交，检查 AI_MARK 正则"; exit 0; }
echo "返工率($WINDOW_DAYS 天内被再修改): $(awk "BEGIN{printf \"%.1f%%\", $reworked*100/$total_ai}")  ($reworked/$total_ai)"
echo "回滚率: $(awk "BEGIN{printf \"%.1f%%\", $reverted*100/$total_ai}")  ($reverted/$total_ai)"
