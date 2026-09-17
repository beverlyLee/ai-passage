#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02_action_safety.py — 邮件自动分类 Agent 的动作层（安全执行）。

分类判完只是「建议」，真正危险的是「落下的那一刀」。邮件 Agent 的
动作层有三道闸，任何一道漏了都会出事：
  1) 白名单优先：命中白名单的邮件绝不移动/删除；
  2) 默认 dry-run：必须显式 --apply 才真的动 IMAP；
  3) 删除走回收站：用 IMAP COPY+标记\\Deleted 移入 Trash，绝不 expunge
     （expunge 才是真删，不可恢复）。
另外两件事：重复触发靠 UID 幂等去重；IMAP 超时/断连必须抛告警，绝不能
静默吞掉让 Agent「以为成功了」。纯标准库，self-test 用内存 FakeIMAP。
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class Mail:
    uid: str
    from_addr: str
    folder: str = "INBOX"
    flags: List[str] = field(default_factory=list)


class ActionAlert(Exception):
    """动作执行失败时必须显式抛出，禁止静默吞掉。"""


class FakeIMAP:
    """内存版 IMAP，模拟文件夹/标记/永久删除，供 self-test 用。

    copy      = 逻辑移动到目标文件夹（保留原标记语义）
    store_del = 给原邮件打 \\Deleted（可撤销，未 expunge 前还能救）
    expunge   = 永久删除带 \\Deleted 的邮件（危险操作，生产禁用）
    """
    def __init__(self):
        self.store: Dict[str, Dict[str, Mail]] = {"INBOX": {}, "垃圾箱": {}, "账单": {}, "Trash": {}}
        self.connected = True
        self.expunged: List[str] = []     # 记录真正被永久删除的 uid
        self.cmds: List[str] = []        # 命令日志，测试可见

    def add(self, mail: Mail) -> None:
        self.store.setdefault(mail.folder, {})[mail.uid] = mail

    def health_check(self) -> None:
        if not self.connected:
            raise ConnectionError("IMAP 连接已断开（超时/网络抖动）")

    def copy(self, uid: str, src: str, dst: str) -> None:
        # IMAP COPY 语义：保留原件，仅在目标文件夹新增一份副本。
        # 副本独立，原件仍在 src 并可继续打 \\Deleted（expunge 前可恢复）。
        import copy as _copy
        self.cmds.append(f"COPY {uid} {src}->{dst}")
        m = self.store[src][uid]
        m2 = _copy.copy(m)
        m2.folder = dst
        self.store.setdefault(dst, {})[uid] = m2

    def store_del(self, uid: str, folder: str) -> None:
        self.cmds.append(f"STORE {uid} +FLAGS \\Deleted")
        self.store[folder][uid].flags.append("\\Deleted")

    def expunge(self, folder: str) -> None:
        self.cmds.append(f"EXPUNGE {folder}")
        for uid, m in list(self.store[folder].items()):
            if "\\Deleted" in m.flags:
                self.expunged.append(uid)
                del self.store[folder][uid]


class Actioner:
    def __init__(
        self,
        imap: FakeIMAP,
        whitelist: List[str],
        trash: str = "Trash",
        dry_run: bool = True,
        processed: Optional[Set[str]] = None,
    ):
        self.imap = imap
        self.whitelist = set(whitelist)
        self.trash = trash
        self.dry_run = dry_run
        self.processed: Set[str] = processed if processed is not None else set()

    def _whitelisted(self, mail: Mail) -> bool:
        return mail.from_addr in self.whitelist

    def move(self, mail: Mail, dest: str) -> str:
        # 幂等：同 UID 已处理过则跳过
        if mail.uid in self.processed:
            return "skipped:idempotent"
        # 白名单优先：绝不移动
        if self._whitelisted(mail):
            return "protected:whitelist"
        # dry-run：只报告，不碰 IMAP
        if self.dry_run:
            return "dry-run:no-op"
        try:
            self.imap.health_check()
            src = mail.folder                              # 先记下原件所在文件夹
            self.imap.copy(mail.uid, src, dest)           # move = copy
            self.imap.store_del(mail.uid, src)            # 标记原件 \\Deleted（可撤销）
            # 注意：这里不调用 expunge，原件仍在服务器、可恢复
        except Exception as e:
            raise ActionAlert(f"move({mail.uid}->{dest}) 失败: {e}")
        self.processed.add(mail.uid)
        return f"moved:{dest}"

    def delete(self, mail: Mail) -> str:
        """删除 = 移到回收站，绝不 expunge。"""
        if mail.uid in self.processed:
            return "skipped:idempotent"
        if self._whitelisted(mail):
            return "protected:whitelist"
        if self.dry_run:
            return "dry-run:no-op"
        try:
            self.imap.health_check()
            self.imap.copy(mail.uid, mail.folder, self.trash)
            self.imap.store_del(mail.uid, mail.folder)
            # 关键：不调用 self.imap.expunge()，所以没有永久删除
        except Exception as e:
            raise ActionAlert(f"delete({mail.uid}) 失败: {e}")
        self.processed.add(mail.uid)
        return f"deleted:{self.trash}"


def _self_test() -> int:
    wl = ["boss@company.com"]
    imap = FakeIMAP()
    imap.add(Mail("u1", "boss@company.com", "INBOX"))
    imap.add(Mail("u2", "spam@unk.com", "INBOX"))
    imap.add(Mail("u3", "spam@unk.com", "INBOX"))

    # 1) 白名单优先：老板邮件不移动
    a = Actioner(imap, wl, dry_run=False)
    r1 = a.move(Mail("u1", "boss@company.com", "INBOX"), "垃圾箱")
    assert r1 == "protected:whitelist", f"白名单被移动: {r1}"
    assert imap.store["INBOX"].get("u1") is not None, "白名单邮件被移走"
    print("[OK] 白名单优先，老板邮件原样保留")

    # 2) dry-run 默认不碰 IMAP
    a2 = Actioner(imap, wl, dry_run=True)
    r2 = a2.move(Mail("u2", "spam@unk.com", "INBOX"), "垃圾箱")
    assert r2 == "dry-run:no-op" and len(imap.cmds) == 0, f"dry-run 仍执行: {imap.cmds}"
    print("[OK] 默认 dry-run，不实际发出任何 IMAP 命令")

    # 3) 删除走回收站：移入 Trash，且 expunge 从未被调用（可恢复）
    a3 = Actioner(imap, wl, dry_run=False)
    r3 = a3.delete(Mail("u2", "spam@unk.com", "INBOX"))
    assert r3 == "deleted:Trash", f"删除未走回收站: {r3}"
    assert imap.store["Trash"].get("u2") is not None, "未进入回收站"
    assert len(imap.expunged) == 0, f"误触发了 expunge: {imap.expunged}"
    print("[OK] 删除走回收站(Trash)，expunge 未调用，原件可恢复")

    # 4) 幂等：同一 uid 处理两次只动一次
    a4 = Actioner(imap, wl, dry_run=False, processed=set())
    before = len(imap.cmds)
    a4.move(Mail("u3", "spam@unk.com", "INBOX"), "账单")
    r4b = a4.move(Mail("u3", "spam@unk.com", "INBOX"), "账单")
    assert r4b == "skipped:idempotent", f"幂等失效: {r4b}"
    assert len(imap.cmds) - before == 2, f"重复触发执行了多次: {imap.cmds}"
    print("[OK] UID 幂等去重，同一封邮件只执行一次")

    # 5) 静默失败防护：连接断开时抛 ActionAlert，绝不吞异常
    imap_bad = FakeIMAP()
    imap_bad.connected = False
    imap_bad.add(Mail("u9", "spam@unk.com", "INBOX"))
    a5 = Actioner(imap_bad, wl, dry_run=False)
    raised = False
    try:
        a5.move(Mail("u9", "spam@unk.com", "INBOX"), "垃圾箱")
    except ActionAlert:
        raised = True
    assert raised, "连接失败被静默吞掉，Agent 误以为成功"
    print("[OK] 连接失败抛 ActionAlert，不静默吞异常")

    print("ALL_SELFTESTS_PASSED")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="邮件自动分类 Agent 动作层：白名单>dry-run>回收站，幂等+失败告警")
    p.add_argument("--self-test", action="store_true", help="运行内置自测")
    p.add_argument("--apply", action="store_true", help="实际执行移动/删除；默认 dry-run")
    args = p.parse_args(argv)
    if args.self_test:
        return _self_test()
    print("动作层已加载。生产用法：分类 Verdict -> Actioner.move/delete(mail)；默认 dry-run，显式 --apply 才落地。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
