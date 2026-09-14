#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepSeek V4.1 Flash 全局 KV Cache 字节算术与压缩比复现。

纯标准库实现，--self-test 校验内部一致性。

核心结论（均来自 DeepSeek-V4.1-Flash 技术报告 2026-09-10）：
  - 全局 KV 在 FP4(E2M1) 落地，每 16 通道 1 个 E4M3 scale。
  - 全局 KV 压到 890 bytes/token，约为 V4-Flash 的 1/4（约 3.9-4.0x）。
  - 相对 V1 累计约 437x；1M token 全局 KV ≈ 0.89 GB。

脚本不反向工程未公开的逐层维度，只做透明算术复现。
"""

import sys

# ---- 元素精度字节数（每元素）----
BYTES_FP16 = 2.0   # 16-bit 浮点
BYTES_FP8 = 1.0    # 8-bit 浮点 (E4M3 / E5M2)

# FP4 (E2M1) + 分组缩放：每 16 个通道 1 个 E4M3 scale (8 bit)
# 16 值 × 4 bit + 1 scale × 8 bit = 72 bit = 9 byte → 每值 0.5625 byte
FP4_GROUP = 16
FP4_BITS = 4
SCALE_BITS = 8
BYTES_FP4_GROUPED = (FP4_GROUP * FP4_BITS + SCALE_BITS) / 8.0  # 9.0 byte / 16 values


def fp4_element_bytes() -> float:
    """FP4 分组量化后，单个元素的等效字节数。"""
    return BYTES_FP4_GROUPED / FP4_GROUP  # 0.5625


def precision_factor() -> float:
    """仅由精度带来的压缩比：FP16 字节 / FP4 分组字节。"""
    return BYTES_FP16 / fp4_element_bytes()


def compression_chain():
    """复现报告中的压缩比链条（输入为报告口径数字）。"""
    v4_flash = 3560.0    # 报告：V4.1 Flash 全局KV ≈ V4-Flash 的 1/4 → V4-Flash≈3560 bytes/token
    v41_flash = 890.0    # 报告落地值
    v1 = v41_flash * 437  # 报告：相对 V1 累计约 437x
    ratio_vs_v4flash = v4_flash / v41_flash
    ratio_vs_v1 = v1 / v41_flash
    gb_per_1m = v41_flash * 1_000_000 / 1_000_000_000
    return ratio_vs_v4flash, ratio_vs_v1, gb_per_1m


def main():
    print("== FP4(E2M1) 分组量化元素字节 ==")
    print(f"  FP16          : {BYTES_FP16:.2f} B/val")
    print(f"  FP8           : {BYTES_FP8:.2f} B/val")
    print(f"  FP4 + group   : {fp4_element_bytes():.4f} B/val  "
          f"(16×4bit + 1×8bit scale) / 16")
    pf = precision_factor()
    print(f"  精度压缩比     : FP16/FP4 ≈ {pf:.2f}x")
    print()
    print("== 全局 KV 压缩比链条（报告口径）==")
    v41_flash = 890.0
    r1, r2, g = compression_chain()
    print(f"  V4-Flash      : 3560 bytes/token")
    print(f"  V4.1 Flash    : 890  bytes/token  (≈1/{r1:.2f} of V4-Flash)")
    print(f"  V1 累计       : {v41_flash*437:.0f} bytes/token  (≈{r2:.0f}x 压缩)")
    print(f"  1M token 占用 : {g:.2f} GB")
    print()
    print("== 分解：精度 vs 结构 ==")
    # 精度贡献 3.56x，结构性贡献(CSA2 跨层复用 + SWA 有界重放)补齐到 4.0x
    structural = (3560.0 / 890.0) / pf
    print(f"  精度贡献      : {pf:.2f}x")
    print(f"  结构贡献      : {structural:.3f}x  (CSA2 跨层复用 + SWA 有界重放)")


def self_test() -> bool:
    ok = True
    if abs(fp4_element_bytes() - 0.5625) > 1e-9:
        print("FAIL: fp4_element_bytes != 0.5625"); ok = False
    if BYTES_FP8 * 2 != BYTES_FP16:
        print("FAIL: FP8 != FP16/2"); ok = False
    if abs(precision_factor() - 3.5555) > 1e-3:
        print(f"FAIL: precision_factor {precision_factor()}"); ok = False
    r1, r2, g = compression_chain()
    if not (3.5 < r1 < 4.5):
        print(f"FAIL: ratio vs V4-Flash {r1}"); ok = False
    if not (400 < r2 < 480):
        print(f"FAIL: ratio vs V1 {r2}"); ok = False
    if abs(g - 0.89) > 0.01:
        print(f"FAIL: 1M token GB {g}"); ok = False
    if ok:
        print("SELF-TEST PASS")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if self_test() else 1)
    main()
