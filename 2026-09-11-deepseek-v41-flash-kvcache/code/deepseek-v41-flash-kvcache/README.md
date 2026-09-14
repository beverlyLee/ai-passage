# DeepSeek V4.1 Flash KV Cache 压缩 · 可复现代码

配套文章：[../DeepSeek-V4.1-Flash-KV压缩-掘金-2026-09-11.md](../DeepSeek-V4.1-Flash-KV压缩-掘金-2026-09-11.md)

所有脚本纯标准库实现，无第三方依赖。每个脚本都带 `--self-test`，在 CI 或本地可直接跑通。

```bash
cd code/deepseek-v41-flash-kvcache
python3 01-kv-cache-arithmetic.py --self-test
python3 02-ced-prefill-complexity.py --self-test
```

## 01 · KV Cache 字节算术与压缩比复现

**为什么写它**：技术报告只给了落地结论（890 bytes/token、约 1/4、437x），但没给"这数字怎么来的"。这个脚本把 FP4(E2M1) 分组量化的元素字节算清楚，再拆出"精度贡献"和"结构贡献"两段。

**输入格式**：无外部输入，参数为报告口径常量（`BYTES_FP16` / `BYTES_FP8` / `FP4_GROUP` 等）。

**实测输出**（python3 01-kv-cache-arithmetic.py）：
```
  FP4 + group   : 0.5625 B/val  (16×4bit + 1×8bit scale) / 16
  精度压缩比     : FP16/FP4 ≈ 3.56x
  V4.1 Flash    : 890  bytes/token  (≈1/4.00 of V4-Flash)
  V1 累计       : 388930 bytes/token  (≈437x 压缩)
  1M token 占用 : 0.89 GB
  精度贡献      : 3.56x
  结构贡献      : 1.125x  (CSA2 跨层复用 + SWA 有界重放)
```

**接入点**：把 `fp4_element_bytes()` 换成你自己的量化方案（如 FP8、INT4 不带 scale），即可横向对比不同精度下的 KV 字节数。

**CI 门禁**：`--self-test` 断言 `fp4_element_bytes()==0.5625`、精度压缩比≈3.56、相对 V4-Flash 3.5–4.5x、相对 V1 400–480x、1M token≈0.89 GB。

## 02 · CED prefill 复杂度对比

**为什么写它**：CED 把"长上下文 prefill"从 O(N·L) 拆成"编码器对 N + 解码器对 n"。这个脚本把层数减半的算力账算清楚。

**输入格式**：无外部输入，参数为 `L_TOTAL=40 / L_ENC=20 / L_DEC=20`。

**实测输出**（python3 02-ced-prefill-complexity.py）：
```
  N=1,000,000 n=     1 : 传统=  40,000,000  CED=  20,000,020  提速≈2.000x
  N=1,000,000 n= 1,000 : 传统=  40,000,000  CED=  20,020,000  提速≈1.998x
```

**接入点**：改 `L_ENC` / `L_DEC` 适配其他 CED 配比，或把 `n` 调大模拟"边读边写"负载，看提速比如何衰减。

**CI 门禁**：`--self-test` 断言长上下文下提速比落在 1.9–2.1x。

## 已知边界

- 所有"报告口径"数字（890 / 3560 / 437x / 0.89 GB）来自 DeepSeek-V4.1-Flash 技术报告（2026-09-10），脚本只做算术复现，不反向工程未公开的逐层维度。
- 精度贡献 3.56x 是"同元素数"下的上限估计；实际 KV 元素数由 CSA2 + SWA 的结构化压缩共同决定，二者不可简单相加，脚本用 `3.56 × 1.125 ≈ 4.0` 给出量级分解而非精确乘法。
- 基准分数（GPQA / HLE / Terminal-Bench 等）属 DeepSeek 自测口径，第三方评测待补，文章"本文不承诺什么"已注明。
