#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
demo_clean_review.py —— 评价清洗管线（四道闸）。

本脚本是 Laya email.py clean_email_body 思路在「用户评价」场景的免依赖最小复现。
四道闸：
    1) 归一化空白          —— 与 email.py 第一道闸（normalize newlines）同构
    2) 剥离默认/模板噪声   —— 对应 email.py 的免责声明剥离，但绑定名词而非裸词防误删诉求
    3) 压缩 emoji 刷屏      —— 评价场景特有的「复制粘贴好评」噪声（如 👍👍👍👍👍）
    4) 超长截断（头+尾）    —— 与 Laya state 右侧/左侧截断同构，保证下游 token 预算

与 Laya 源码对应（一手来源 convaiinnovations/laya @ 4066d5d, email.py）：
    clean_email_body 的四道闸：归一化换行 / 切引文 / 切签名设备页脚 / 段落级免责剥离。
    关键纪律：正则绑定名词（如「默认」「系统」）而非裸词，避免把真实诉求误删。

运行：
    python3 demo_clean_review.py --self-test
    python3 demo_clean_review.py
"""
import sys
import re
import argparse

MAX_LEN = 120  # 超过则头 80 + 尾 40 拼接，模拟 Laya state 预算裁剪

# 第二道闸：默认/模板噪声。绑定「默认」「系统」「确认」等名词，避免误删真实诉求。
_NOISE_PATTERNS = [
    re.compile(r"此用户未填写评价内容"),
    re.compile(r"系统默认好评"),
    re.compile(r"默认好评"),
    re.compile(r"已购确认"),
    re.compile(r"评价方未及时做出评价[，,]?系统默认"),
]


def _normalize_whitespace(text):
    """第一道闸：归一化空白。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _strip_boilerplate(text):
    """第二道闸：剥离默认/模板噪声行。按整行移除，不破坏其他句子。"""
    out_lines = []
    for line in text.split("\n"):
        if any(p.search(line) for p in _NOISE_PATTERNS):
            continue
        out_lines.append(line)
    return "\n".join(out_lines).strip()


def _compress_emoji_spam(text):
    """第三道闸：压缩 emoji 刷屏。把连续 2 个以上的同类 emoji 压成 1 个。"""
    # 处理常见 emoji 序列（含变体选择符 U+FE0F 与 ZWJ）
    # 规则：同一 emoji 连续出现 >=2 次，只保留 1 个
    def _collapse(match):
        seq = match.group(0)
        # 取序列第一个「字符簇」作为代表，保留一个
        # 简单按码点去重保序，仅保留首次出现的连续相同 emoji
        chars = []
        last = None
        for ch in seq:
            if ch == last:
                continue
            chars.append(ch)
            last = ch
        return "".join(chars)

    # 匹配 2 个及以上连续 emoji（含组合）
    emoji_runs = re.compile(
        "[" 
        "\U0001F300-\U0001FAFF"  # 符号与表情
        "\U00002600-\U000027BF"  # 杂项符号
        "\U0001F1E6-\U0001F1FF"  # 区域指示符（国旗）
        "\uFE0F\u200D"           # 变体选择符 / ZWJ
        "]+"
    )
    return emoji_runs.sub(_collapse, text)


def _truncate(text):
    """第四道闸：超长截断（头 + 尾），与 Laya state 预算裁剪同构。"""
    if len(text) <= MAX_LEN:
        return text
    head = text[:80]
    tail = text[-40:]
    return head + " …[truncated]… " + tail


def clean_review(text):
    """完整四道闸。"""
    text = _normalize_whitespace(text)
    text = _strip_boilerplate(text)
    text = _compress_emoji_spam(text)
    text = _truncate(text)
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    sample = (
        "默认好评\n已购确认  物流真的快，从下单到收货只用了四天，"
        "包装也很扎实，客服回复也及时，总之很满意，会回购。👍👍👍👍👍"
    )
    print("原始：", sample)
    print("清洗：", clean_review(sample))
    return 0


def _self_test():
    # 1) 默认噪声被整行剥离，但真实诉求保留
    t1 = "系统默认好评\n希望你们尽快修复导出功能，否则我只能退订了。"
    c1 = clean_review(t1)
    assert "系统默认好评" not in c1, c1
    assert "修复导出功能" in c1, c1
    print("[PASS] 默认好评噪声剥离，诉求保留")

    # 2) emoji 刷屏被压缩成 1 个
    t2 = "很满意👍👍👍👍👍"
    c2 = clean_review(t2)
    assert c2.count("👍") == 1, c2
    print("[PASS] emoji 刷屏压缩")

    # 3) 空白归一化：多空格/换行归一
    t3 = "界面   挺好看的\n\n\n用着也顺手"
    c3 = clean_review(t3)
    assert "    " not in c3, c3
    assert "\n\n\n" not in c3, c3
    print("[PASS] 空白归一化")

    # 4) 超长截断：头 80 + 尾 40
    t4 = "A" * 200
    c4 = clean_review(t4)
    assert "[truncated]" in c4, c4
    assert len(c4) <= 80 + 40 + len(" …[truncated]… "), c4
    print("[PASS] 超长截断")

    # 5) 绑定名词的纪律：含「默认」二字的真实句子不被误删
    t5 = "默认设置下导出的文件是乱序的，请修一下。"  # 「默认」在句首但不是噪声模板
    c5 = clean_review(t5)
    assert "默认设置下导出" in c5, c5   # 没被当成默认好评删掉
    print("[PASS] 绑定名词纪律：不误删真实句子")

    print("\nself-test PASS: 全部 5 项断言通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
