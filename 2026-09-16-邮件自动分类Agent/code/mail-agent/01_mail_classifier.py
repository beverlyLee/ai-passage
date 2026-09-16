#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
01_mail_classifier.py — 邮件自动分类 Agent 的分类层。

邮件 Agent 最难的不是「分类」，是「别分错」。一旦把老板的邮件标成
垃圾、把含身份证的邮件落库明文，后果比不分类严重得多。本模块演示
三类典型误分类与兜底：
  1) 误标垃圾：白名单发件人优先级高于一切垃圾规则；
  2) 规则冲突：多规则竞争同一封邮件时，按优先级 + 白名单裁决；
  3) 隐私泄露：落库前对身份证 / 银行卡 / 密钥等做脱敏。
纯标准库，可直接跑 self-test。真实环境把 Mail 的来源换成 imaplib 取信即可。
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Mail:
    uid: str
    from_addr: str
    to_addr: str
    subject: str
    body: str
    attachments: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)   # \Seen \Flagged 等
    folder: str = "INBOX"


@dataclass
class Rule:
    name: str
    priority: int          # 越小优先级越高
    folder: str            # 命中后移动到的目标文件夹
    pattern: str           # 在 subject/body/from 中匹配的子串
    is_spam: bool = False  # True 表示命中即判垃圾


@dataclass
class Verdict:
    uid: str
    label: str             # normal | spam | classified
    dest_folder: str       # 建议移动到的文件夹（白名单则保持原样）
    reason: str
    masked_body: str       # 已脱敏的 body，供落库
    protected: bool = False


# 隐私正则：身份证(18 位) / 银行卡(16-19 位) / 显式密钥
ID_CARD_RE = re.compile(r"\b\d{17}[\dXx]\b")
BANK_CARD_RE = re.compile(r"\b\d{16,19}\b")
SECRET_RE = re.compile(r"(?:api[_-]?key|secret|token|password)\s*[:=]\s*\S+", re.I)


def mask_text(text: str) -> str:
    """落库前脱敏：身份证保留前 4 后 2，银行卡保留前 4 后 4，密钥整体打码。"""
    text = ID_CARD_RE.sub(lambda m: m.group(0)[:4] + "***********" + m.group(0)[-2:], text)
    text = BANK_CARD_RE.sub(lambda m: m.group(0)[:4] + "********" + m.group(0)[-4:], text)
    text = SECRET_RE.sub(lambda m: m.group(0).split("=")[0].split(":")[0] + "=***REDACTED***", text)
    return text


class Classifier:
    def __init__(
        self,
        whitelist: List[str],
        rules: List[Rule],
        spam_keywords: List[str],
        spam_threshold: int = 3,
    ):
        self.whitelist = set(whitelist)
        self.rules = sorted(rules, key=lambda r: r.priority)   # 高优先级在前
        self.spam_keywords = spam_keywords
        self.spam_threshold = spam_threshold

    def _matches(self, mail: Mail, pattern: str) -> bool:
        return (
            pattern in mail.subject
            or pattern in mail.body
            or pattern in mail.from_addr
        )

    def _spam_score(self, mail: Mail) -> int:
        hay = (mail.subject + "\n" + mail.body).lower()
        return sum(1 for kw in self.spam_keywords if kw.lower() in hay)

    def classify(self, mail: Mail) -> Verdict:
        masked = mask_text(mail.body)

        # 1) 白名单优先于一切规则与评分（防误标垃圾的核心闸）
        if mail.from_addr in self.whitelist:
            return Verdict(
                mail.uid, "normal", mail.folder,
                reason=f"白名单发件人 {mail.from_addr}，原样保留",
                masked_body=masked, protected=True,
            )

        # 2) 规则冲突：按优先级依次裁决，命中即停（高优先级赢）
        for r in self.rules:
            if self._matches(mail, r.pattern):
                label = "spam" if r.is_spam else "classified"
                return Verdict(
                    mail.uid, label, r.folder,
                    reason=f"命中规则[{r.name}](优先级 {r.priority})",
                    masked_body=masked,
                )

        # 3) 无规则命中：按关键词评分兜底判垃圾
        score = self._spam_score(mail)
        if score >= self.spam_threshold:
            return Verdict(
                mail.uid, "spam", "垃圾箱",
                reason=f"关键词评分 {score} >= {self.spam_threshold}",
                masked_body=masked,
            )
        return Verdict(
            mail.uid, "normal", mail.folder,
            reason="无规则命中且评分未达阈值",
            masked_body=masked,
        )


def _self_test() -> int:
    wl = ["boss@company.com", "ceo@company.com"]
    rules = [
        Rule("发票归档", 1, "账单", "发票"),        # 高优先级：发票 -> 账单
        Rule("抽奖垃圾", 5, "垃圾箱", "中奖", is_spam=True),  # 低优先级：中奖 -> 垃圾
    ]
    spam_kw = ["优惠", "中奖", "免费", "点击", "立即领取"]
    c = Classifier(wl, rules, spam_kw)

    # 1) 误标垃圾防护：白名单发件人，即便正文满是垃圾词也不标垃圾
    m1 = Mail("u1", "boss@company.com", "me@x.com", "发票 优惠 中奖 立即领取",
              "这是老板的发票，含优惠中奖等词但不该被标垃圾")
    v1 = c.classify(m1)
    assert v1.label == "normal" and v1.protected, f"白名单误标垃圾: {v1}"
    print("[OK] 白名单优先级最高，老板的垃圾词邮件仍判 normal")

    # 2) 规则冲突：同一封同时命中「发票」与「中奖」，高优先级(1)赢
    m2 = Mail("u2", "vendor@x.com", "me@x.com", "发票与中奖通知",
              "您有一张发票，并且中奖了")
    v2 = c.classify(m2)
    assert v2.dest_folder == "账单", f"规则冲突裁决错: {v2}"
    print("[OK] 规则冲突按优先级裁决：发票(优先级1) 胜过 中奖(优先级5)")

    # 3) 隐私脱敏：落库的 body 不再含明文身份证/银行卡
    m3 = Mail("u3", "hr@x.com", "me@x.com", "入职材料",
              "身份证 11010119900307651X 银行卡 6222021234567890123 api_key=sk-abc123def")
    v3 = c.classify(m3)
    assert "11010119900307651X" not in v3.masked_body, "身份证未脱敏"
    assert "6222021234567890123" not in v3.masked_body, "银行卡未脱敏"
    assert "sk-abc123def" not in v3.masked_body, "密钥未脱敏"
    assert "1101" in v3.masked_body and "1X" in v3.masked_body, "脱敏格式异常"
    print("[OK] 隐私脱敏生效：身份证/银行卡/密钥落库前被遮盖")

    # 4) 评分兜底：未知发件人 + 多个垃圾词 -> 判垃圾
    m4 = Mail("u4", "spam@unk.com", "me@x.com", "免费优惠 中奖 点击立即领取",
              "免费优惠中奖点击立即领取，速来")
    v4 = c.classify(m4)
    assert v4.label == "spam" and v4.dest_folder == "垃圾箱", f"评分兜底失效: {v4}"
    print("[OK] 无规则命中时按关键词评分兜底判垃圾")

    print("ALL_SELFTESTS_PASSED")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="邮件自动分类 Agent 分类层：白名单优先 + 规则冲突裁决 + 隐私脱敏")
    p.add_argument("--self-test", action="store_true", help="运行内置自测")
    args = p.parse_args(argv)
    if args.self_test:
        return _self_test()
    print("分类层已加载。生产用法：imaplib 取信 -> Classifier.classify(mail) -> 得到 Verdict（含脱敏 body）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
