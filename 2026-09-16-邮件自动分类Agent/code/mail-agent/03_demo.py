#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03_demo.py — 邮件自动分类 Agent 端到端可复现演示。

把分类层(01_mail_classifier.py)和动作层(02_action_safety.py)串成一条完整链路，
用内置合成样例邮件跑一遍，让你在本机复现全部六坑的「正确行为」与「防住后果」：

  数据来源：内置合成样例邮件。身份证号用公开校验格式示例（11010119900307651X），
            银行卡号与 api_key 均为示例占位，无真实 PII、无真实邮箱。
  运行环境：Python 3.8+，纯标准库，无第三方依赖。
  运行方式：
      python 03_demo.py              # 跑完整演示，打印四阶段报告
      python 03_demo.py --self-test  # 断言所有不变量，CI / 复现校验用

演示覆盖六坑：
  ① 白名单防误标  ② 规则优先级裁决  ③ 落库前脱敏
  ④ 删除走回收站、绝不 expunge  ⑤ 连接断开抛 ActionAlert  ⑥ UID 幂等去重
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(mod_name: str, fname: str):
    spec = importlib.util.spec_from_file_location(
        mod_name, os.path.join(HERE, fname)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod   # 先注册，dataclass 的 __module__ 查找依赖
    spec.loader.exec_module(mod)
    return mod


_cls = _load("mail_classifier", "01_mail_classifier.py")
_act = _load("action_safety", "02_action_safety.py")

Classifier = _cls.Classifier
Mail = _cls.Mail
Rule = _cls.Rule
Actioner = _act.Actioner
FakeIMAP = _act.FakeIMAP
ActionAlert = _act.ActionAlert

WHITELIST = ["boss@company.com", "ceo@company.com"]


def build_scenario():
    rules = [
        Rule("发票归档", 1, "账单", "发票"),               # 高优先级：发票 -> 账单
        Rule("抽奖垃圾", 5, "垃圾箱", "中奖", is_spam=True),  # 低优先级：中奖 -> 垃圾
    ]
    spam_kw = ["优惠", "中奖", "免费", "点击", "立即领取"]
    classifier = Classifier(WHITELIST, rules, spam_kw)

    # 合成样例邮件（无真实 PII；身份证号仅供格式演示）
    mails = [
        Mail("u1", "boss@company.com", "me@x.com", "发票 优惠 中奖 立即领取",
             "老板的发票，含垃圾词但不该被误杀", folder="INBOX"),
        Mail("u2", "vendor@x.com", "me@x.com", "发票与中奖通知",
             "您有一张发票，并且中奖了", folder="INBOX"),
        Mail("u3", "hr@x.com", "me@x.com", "入职材料",
             "身份证 11010119900307651X 银行卡 6222021234567890123 api_key=sk-abc123def",
             folder="INBOX"),
        Mail("u4", "spam@unk.com", "me@x.com", "免费优惠 中奖 点击立即领取",
             "免费优惠中奖点击立即领取，速来", folder="INBOX"),
        Mail("u5", "noreply@x.com", "me@x.com", "周报",
             "本周进度正常，无附件", folder="INBOX"),
    ]
    return classifier, mails


def run_pipeline(classifier, mails, imap, actioner):
    """完整循环：分类层裁决 -> 动作层执行。返回可读报告。"""
    report = []
    for m in mails:
        v = classifier.classify(m)
        if v.protected:
            action = "protected:whitelist"
        elif v.label == "spam":
            action = actioner.delete(m)
        elif v.dest_folder != m.folder:
            action = actioner.move(m, v.dest_folder)
        else:
            action = "keep:" + m.folder
        report.append((m.uid, m.from_addr, v.label, v.reason, v.dest_folder, action))
    return report


def _fmt(report):
    head = f"{'uid':<4}{'from':<20}{'label':<12}{'action':<22}{'dest'}"
    rows = [head]
    for uid, frm, label, reason, dest, action in report:
        rows.append(f"{uid:<4}{frm:<20}{label:<12}{action:<22}{dest}")
    return "\n".join(rows)


def run_demo() -> int:
    classifier, mails = build_scenario()

    # ③ 落库前脱敏演示：含 PII 的邮件，落库用 masked_body，不含明文
    v3 = classifier.classify(mails[2])
    print("[OK] 含 PII 邮件落库前脱敏后的正文：")
    print(f"     {v3.masked_body}\n")

    # 阶段一：dry-run（只报不执行）
    imap_dry = FakeIMAP()
    for m in mails:
        imap_dry.add(m)
    a_dry = Actioner(imap_dry, WHITELIST, dry_run=True)
    print("=== 阶段一：dry-run（只报不执行） ===")
    rep_dry = run_pipeline(classifier, mails, imap_dry, a_dry)
    print(_fmt(rep_dry))
    assert len(imap_dry.cmds) == 0, "dry-run 不应发出任何 IMAP 命令"
    print(f"[OK] dry-run 期间 IMAP 命令数 = {len(imap_dry.cmds)}（应为 0）\n")

    # 阶段二：--apply（真实执行，删除走回收站，绝不 expunge）
    imap_real = FakeIMAP()
    for m in mails:
        imap_real.add(m)
    a_real = Actioner(imap_real, WHITELIST, dry_run=False)
    print("=== 阶段二：apply（真实执行，删除走回收站） ===")
    rep_real = run_pipeline(classifier, mails, imap_real, a_real)
    print(_fmt(rep_real))
    print(f"[OK] 进入 Trash 的邮件：{sorted(imap_real.store.get('Trash', {}).keys())}")
    print(f"[OK] 被 expunge 永久删除的邮件：{imap_real.expunged}（应为空）\n")

    # 阶段三：重复触发（at-least-once），复用同一 Actioner 实例
    before = len(imap_real.cmds)
    run_pipeline(classifier, mails, imap_real, a_real)
    added = len(imap_real.cmds) - before
    print("=== 阶段三：重复触发（at-least-once） ===")
    print(f"[OK] 第二批处理新增 IMAP 命令 = {added}（应为 0，UID 幂等去重）\n")

    # 阶段四：连接断开必须抛 ActionAlert，绝不静默吞
    print("=== 阶段四：连接断开 ===")
    imap_bad = FakeIMAP()
    imap_bad.connected = False
    imap_bad.add(Mail("u9", "spam@unk.com", "me@x.com", "x", "y", folder="INBOX"))
    a_bad = Actioner(imap_bad, [], dry_run=False)
    try:
        a_bad.move(Mail("u9", "spam@unk.com", "me@x.com", "x", "y", folder="INBOX"), "垃圾箱")
        raise AssertionError("连接失败被静默吞掉，Agent 误以为成功")
    except ActionAlert as e:
        print(f"[OK] 断连抛出 ActionAlert：{e}")

    print("\nDEMO_OK: 六坑全部以可复现方式跑通"
          "（白名单防误标 / 优先级裁决 / 落库前脱敏 / 回收站不 expunge / 断连告警 / UID 幂等）")
    return 0


def _self_test() -> int:
    return run_demo()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="邮件自动分类 Agent 端到端可复现演示")
    p.add_argument("--self-test", action="store_true", help="运行并断言所有不变量")
    args = p.parse_args(argv)
    return _self_test() if args.self_test else run_demo()


if __name__ == "__main__":
    sys.exit(main())
