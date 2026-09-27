#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""机器校验 Laya 正文.md：禁用符号、复现输出与实跑一致、配图引用存在、结构齐全。"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTICLE = os.path.join(ROOT, "正文.md")
CODE = os.path.join(ROOT, "code", "laya_mechanism.py")
DIAG_DIR = os.path.join(ROOT, "diagram")

errors = []
warns = []


def fail(msg):
    errors.append(msg)


def warn(msg):
    warns.append(msg)


# --- 1. 禁用符号 ---
with open(ARTICLE, "r", encoding="utf-8") as f:
    text = f.read()

if "——" in text:
    fail("发现破折号(——)")
if "**" in text:
    # 排除 markdown 链接/图片里可能出现的 ** ？本文不应有粗体
    fail("发现粗体标记(**)")
# 黑名单词（金融/法律/医疗敏感，本篇应规避）
banned_words = ["支付", "交易", "风控", "资金", "医疗", "诊断", "处方"]
for w in banned_words:
    if w in text:
        warn(f"出现敏感词残词：{w}")

# --- 2. 结构齐全 ---
needed_sections = ["## 复现模块", "## 结尾钩子", "## 讲给别人听", "## 来源"]
for s in needed_sections:
    if s not in text:
        fail(f"缺少小节：{s}")
# 至少 3 个坑
pit = len(re.findall(r"## 第.+坑", text))
if pit < 3:
    fail(f"坑数量不足（实有 {pit}，需 >=3）")

# --- 3. 配图引用真实存在 ---
for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", text):
    rel = m.group(1)
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        fail(f"配图引用文件不存在：{rel}")
    else:
        print(f"  OK 配图存在: {rel}")

# --- 4. 复现输出与实跑逐行一致 ---
# 取脚本 --demo 的真实 stdout
demo = subprocess.run([sys.executable, CODE, "--demo"],
                      capture_output=True, text=True)
demo_out = demo.stdout
# 抽脚本 stdout 里的 JSON（state: 行之后到末尾的 {...}）
start = demo_out.index("{")
script_json = json.loads(demo_out[start:])

# 抽正文 复现模块 小节里的 json 代码块（最后一个 ```json ... ```）
repro_sec = text.split("## 复现模块", 1)[1]
blocks = re.findall(r"```json\n(.*?)```", repro_sec, re.S)
if not blocks:
    fail("复现模块未找到 json 代码块")
else:
    article_json = json.loads(blocks[-1])
    if article_json == script_json:
        print("  OK 复现模块 JSON 与实跑 --demo 完全一致")
    else:
        fail("复现模块 JSON 与实跑 --demo 不一致")
        # 差异详情
        def diff(a, b, path=""):
            if isinstance(a, dict):
                for k in set(a) | set(b):
                    diff(a.get(k), b.get(k), path + "/" + str(k))
            elif a != b:
                print(f"    差异 {path}: 正文={a!r} 实跑={b!r}")
        diff(article_json, script_json)

# 同时也校验 开头 那段 JSON（第一段 ```json）
first_blocks = re.findall(r"```json\n(.*?)```", text, re.S)
if first_blocks:
    head_json = json.loads(first_blocks[0])
    if head_json == script_json:
        print("  OK 开头 JSON 与实跑 --demo 完全一致")
    else:
        fail("开头 JSON 与实跑 --demo 不一致")

# --- 5. self-test 仍全绿 ---
st = subprocess.run([sys.executable, CODE, "--self-test"],
                    capture_output=True, text=True)
if "全部通过" not in st.stdout:
    fail("self-test 未全部通过")
else:
    print("  OK self-test 全部通过")

print()
if warns:
    print("警告:")
    for w in warns:
        print("  - " + w)
if errors:
    print("校验失败:")
    for e in errors:
        print("  - " + e)
    sys.exit(1)
else:
    print("全部校验通过。")
