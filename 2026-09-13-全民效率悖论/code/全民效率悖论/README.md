# 全民效率悖论 · 可运行代码

两枚纯标准库 Python 脚本，对应正文机制①（期望-现实鸿沟）与机制③（认知负载激增）。
无第三方依赖，clone 后直接跑。

## 01-expectation-reality-gap.py —— 期望-现实鸿沟模拟器
把你"用 AI 省下的时间"和"花在核验/纠偏上的时间"对冲，算真实净增益与 botsitting 占比。
对应图2、机制①。

```bash
python3 01-expectation-reality-gap.py --self-test
python3 01-expectation-reality-gap.py --saved 11 --botsit 6.4 --fail-rate 0.34
```
- 自检内置 Foxit 高管（净得≈16 分钟）、Glean 知识工作者（纸面盈利但核验过半）、终端用户（净亏）三案例。

## 02-cognitive-load-detector.py —— AI 文本认知负载检测器
用突发度（句长标准差/均值）与词汇多样性 TTR 两个风格指标，判断文本"更像人写还是 AI 写"。
对应图4、机制③。指标越"套路化"（低突发度+低 TTR），越需要人亲自补结构/立场/判断——这正是认知负载的来源。

```bash
python3 02-cognitive-load-detector.py --self-test
python3 02-cognitive-load-detector.py --text "你的文本..."
cat a.txt | python3 02-cognitive-load-detector.py --stdin
```

> 说明：两脚本均为风格代理指标，用于"快速标记需人工整合的判断点"，非绝对判定，也不依赖任何语言模型。
