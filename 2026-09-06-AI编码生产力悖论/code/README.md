# AI 编码生产力悖论 · 配套脚本

对应掘金文章《用 AI 写得更快，上线却更炸？拆解 AI 编码生产力悖论的 5 个机制，附 9 个坑的自检清单》。

把正文里的三段可运行脚本移出到这里，clone 后改两行路径即可跑。

## 文件

| 文件 | 作用 | 对应正文 |
|---|---|---|
| `01-ai-diff-gate.sh` | 超大 AI diff 门禁：净增行数 / 触及文件数双卡 + 覆盖率只升不降 | 问题 2（治"账算错"） |
| `02-mcp-budget.py` | 扫描 MCP server 工具定义占用的上下文 token 预算 | 问题 4（治"尺子没换"） |
| `03-ai-rework-rate.sh` | 统计 AI 标记提交的返工率 / 回滚率 | 问题 5（守底线） |

## 用法

```bash
# 1. diff 门禁（CI 中，base 默认 origin/main）
MAX_DIFF_LINES=400 MAX_FILES=15 ./01-ai-diff-gate.sh

# 2. MCP 工具定义预算扫描
python3 02-mcp-budget.py ~/.cursor/mcp.json --window 200000 --budget 0.10

# 3. AI 提交返工率（需先给 AI 提交打 [ai] 标记或用 Co-authored-by 识别）
./03-ai-rework-rate.sh --since "90 days ago"
```

跑出返工率与验证工时占比，就有了基线；若显著高于人类提交（参照 arXiv 那 71.7% 进迭代循环的数），说明瓶颈在验证不在生成。
