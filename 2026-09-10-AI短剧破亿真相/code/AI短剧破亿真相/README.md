# code/AI短剧破亿真相

两款**纯标准库、可直接运行**的脚本，对应正文的两个失败模式治理：

| 脚本 | 对应正文 | 作用 |
|---|---|---|
| `01-consistency-eval.py` | 问题 2 / 坑 1、坑 7 | 跨帧一致性评测门禁：参考特征 vs 每帧特征做余弦相似度，低于阈值判「一致性崩」 |
| `02-cost-estimator.py` | 问题 3 / 坑 3 | 单集算力成本估算 + 抽卡门禁：抽卡超上限即告警 |

## 运行

```bash
# 一致性评测（跑内置示例，含故意漂移帧以演示门禁差异）
python3 01-consistency-eval.py --self-test

# 成本估算（正常）
python3 02-cost-estimator.py --seconds 15 --price 1.0 --draws 10

# 成本估算（触发门禁：抽卡 300 > 上限 30）
python3 02-cost-estimator.py --seconds 15 --price 1.0 --draws 300 --budget 30
```

## 已知边界

- 一致性脚本的 `examples/` 特征是**手工构造的模拟向量**，仅演示评估口径。真实产线把 `feat` 换成 IP-Adapter / ConsisID / CLIP 输出的 identity embedding 即可。
- 成本脚本的单价取中值（Seedance ~1 元/秒、Sora2 ~1.5、Veo3 ~2.8），视频生成定价变动快，落地以厂商最新报价为准；未含音频/合规/人力。
- 阈值 0.85、门禁 30 次抽卡均为经验起点，按角色宽容度与预算调。

## 与正文的映射

- 坑 1（seed 不是身份锁）→ 用显式 `feat` 而非指望 seed 复现。
- 坑 3（抽卡无门禁）→ `--budget` 门禁；示例 `draws 300` 即对应 ShortsCrew「一部剧亏数万」的翻车面。
