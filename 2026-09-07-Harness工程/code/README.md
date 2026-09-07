# Harness 工程脚本集

对应掘金文章《同一个模型 30% 到 100%？拆解 Harness 工程的 5 个机制，附 8 个坑的自检清单》。

| 脚本 | 对应正文 | 作用 |
|---|---|---|
| `01-goal-loop.sh` | 问题 3（治循环断）/ 问题 4（治兜底断） | 目标循环骨架：while + 外部验证器 + 三个独立出口（成功 / 迭代上限 / 预算上限）+ 每轮上下文重置（Ralph 模式） |
| `02-stall-detector.py` | 问题 4（治兜底断） | 停滞检测：平台、同文件反复修改、候选趋同、失败原因重复，超阈值报警并输出重定向建议 |
| `03-harness-metrics.py` | 问题 5（守底线） | harness 度量面板：动作数、恢复频率、每轮 token、wall-clock、成本，并与裸模型基线对照 |

## 快速开始

```bash
# 1. 目标循环：改成你自己的确定性检查后直接跑
chmod +x 01-goal-loop.sh
./01-goal-loop.sh "把 src/ 下的回调风格全部迁移到 async/await" 20 5.00

# 2. 停滞检测：把每轮指标以 JSONL 落盘后扫描
python3 02-stall-detector.py metrics.jsonl --window 8 --file-churn 5

# 3. 度量面板：先裸跑一遍同任务生成 baseline.json，再对比
python3 03-harness-metrics.py run.jsonl --baseline baseline.json
```

## 指标落盘格式

`metrics.jsonl` / `run.jsonl` 每行一个 JSON：

```json
{"turn": 1, "score": 0.42, "files_changed": ["a.py"], "candidates": ["..."], "error": null,
 "actions": 12, "recovered": false, "tokens_in": 48000, "tokens_out": 3100, "wall_sec": 214, "cost_usd": 0.42}
```

`score` 必须来自验证器（测试退出码、基准吞吐、schema 校验），不是 agent 自评。

## 一句话总纲

模型出提议质量，harness 出累积能力。四个零件：Trigger、可验证 Goal、独立 Verifier、三个停止出口；记忆放磁盘不放上下文；supervisor 只建议不接管；没有裸模型基线就没有收益。
