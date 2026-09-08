# AI 编码账单工具箱

对应掘金文章《「我明明没干啥，额度怎么就没了」？拆开 AI 编码账单的 5 个吞钱口，附 8 个坑的自检清单》（2026-09-08）。

| 脚本 | 对应正文 | 作用 |
|---|---|---|
| `01-bill-attribution.py` | 问题 1（立总根） | 把 usage 记录按 fresh input / cached input / cache write / visible output / reasoning 五类分段算钱，并按环境拆分，定位吞钱口 |
| `02-cache-prefix-diff.py` | 问题 3（治缓存没吃上） | 对比两次请求的 prompt，定位第一个前缀分叉点，并判断共同前缀是否低于厂商最小可缓存长度（静默失效场景） |
| `03-loop-guard.sh` | 问题 4（治循环复利） | agent 循环三重止损：轮次上限、累计金额上限、连续无进展，触发即退出并落盘报告 |

## 快速开始

```bash
# 1) 账单归因：把你的 usage 日志（JSONL/CSV）按五类计费项拆开
python3 01-bill-attribution.py usage.jsonl --pricing pricing.csv

# 2) 缓存前缀漂移检测：为什么命中率是 0
python3 02-cache-prefix-diff.py req_round1.txt req_round2.txt --provider anthropic

# 3) agent 循环止损：包住任意 agent 命令
MAX_TURNS=50 MAX_COST_USD=2.00 MAX_STALL=3 \
  ./03-loop-guard.sh -- your-agent --task "refactor foo"
```

## 价目表格式（01 用的 pricing.csv）

```csv
model,input,cached_input,cache_write,output
claude-sonnet-4-6,3.00,0.30,3.75,15.00
gpt-4o,2.50,2.50,2.50,10.00
```

单位是**每百万 token 的美元单价**。缓存读价是 0.1x 时的 0.30；OpenAI 无独立写费的模型把 cache_write 填成和 input 一样即可。价格随厂商调整变动，请以当期价目表为准。

## 已知边界

- token 粗估（02）按 4 字符≈1 token / 中文 1.5 字符≈1 token，只用于结构判断，不是精确 tokenizer
- 03 的金额止损依赖 agent 输出 usage 信息；没有 usage 时只剩轮次与无进展两道闸
- 非生产流量占比需要 usage 日志里有 environment 字段才能拆出来；没有的话先补标签
