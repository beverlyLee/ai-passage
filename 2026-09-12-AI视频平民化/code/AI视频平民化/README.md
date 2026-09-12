# 第20篇外置代码：AI 视频平民化

对应正文《Sora 退场，国产三线崛起：AI 视频平民化背后的 5 个工程拐点》。
均纯标准库实现，带 `[SELF-CHECK]`，可直接进 CI。

| 文件 | 对应论点 | 说明 |
|---|---|---|
| `01-dit-attention-complexity.py` | 论点 1 算力墙 | Video DiT 注意力复杂度分级：dense O(N²) vs 线性 O(N) vs 稀疏滑窗 O(N·w) |
| `02-ai-video-cost-estimator.py` | 论点 5 分发闭环 | 同样一段视频，AI 生成侧 vs 传统专业制作的**量级**估算（不承诺精确降幅） |

## 用法

```bash
# 01：复现复杂度类比率（默认 5s/720p ≈ 115K tokens）
python3 01-dit-attention-complexity.py --self-test

# 02：复现成本量级（默认 60s/1080P/通义万相，传统 30000 元/分钟）
python3 02-ai-video-cost-estimator.py --self-test

# 02 改假设：可灵近似、720P、传统按 50000 元/分钟
python3 02-ai-video-cost-estimator.py --provider kling --res 720 --traditional-per-min 50000
```

## 自检口径（铁律：只在全默认或显式 --self-test 时断言，避免误伤正常用法）

- **01**：复杂度类顺序 `dense > sparse > linear`；线性注意力对长序列应为数量级更省（N/d>10）；局部窗口占比与 STA 论文 15.52% 一致；tokens 落在 5s/720p 实测区间（100K–130K）。
- **02**：通义万相刊例价内部关系 `1080P==4×480P`、`720P==2×480P`（防手抄错误，对应第19篇教训）；分辨率越高单价越高；默认场景 AI 成本==72.00 元、传统==30000 元、量级比值>100x。

## 已知边界

- 01 输出是**复杂度类比率**，不是墙钟时间；墙钟还受 FlashAttention、kernel fusion、显存带宽影响（正文 13.06s/3.53x 为厂商实测）。
- 02 是**量级估算**：传统侧依赖 `--traditional-per-min` 假设，AI 侧用公开 API 刊例价；**不承诺"成本下降 90%"之类的精确数字**。SANA-Video 2.0 比 Wan2.2 快 120× 为 NVIDIA 自测，需独立复现。
