#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02_rule_engine.py — 本地文件监控 Agent 的动作层（规则引擎）。

监控 Agent 最危险的不是漏判，是误删。一个错误的 glob 能在一秒内
清空整个 Downloads。本模块把「删除」做成不可轻易触发的动作：
  1) 白名单优先于一切删除规则（命中白名单绝不删）；
  2) 默认 dry-run，必须显式 --apply 才落地；
  3) 删除走「移动到回收站」而非 os.remove，留后悔药。
纯标准库。
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Rule:
    name: str
    pattern: str          # glob，如 old_*.jpg / *.log
    action: str           # 'delete' | 'move' | 'tag'
    dest: Optional[str] = None


@dataclass
class Verdict:
    path: str
    rule: Optional[str]
    action: Optional[str]
    deleted: bool = False
    protected: bool = False
    reason: str = ""


class RuleEngine:
    def __init__(
        self,
        rules: List[Rule],
        whitelist: List[str],
        trash_dir: str,
        dry_run: bool = True,
    ):
        self.rules = rules
        self.whitelist = whitelist
        self.trash_dir = trash_dir
        self.dry_run = dry_run
        os.makedirs(trash_dir, exist_ok=True)

    def _match(self, path: str, pat: str) -> bool:
        base = os.path.basename(path)
        return fnmatch.fnmatch(base, pat) or fnmatch.fnmatch(path, pat)

    def _whitelisted(self, path: str) -> bool:
        return any(self._match(path, w) for w in self.whitelist)

    def evaluate(self, path: str) -> Verdict:
        # 白名单优先于一切规则
        if self._whitelisted(path):
            return Verdict(path, None, None, protected=True, reason="命中白名单，跳过")
        for r in self.rules:
            if self._match(path, r.pattern):
                if r.action == "delete":
                    return self._delete(path, r)
                if r.action == "move" and r.dest:
                    return self._move(path, r)
                return Verdict(path, r.name, r.action, reason="命中规则")
        return Verdict(path, None, None, reason="无规则命中")

    def _delete(self, path: str, r: Rule) -> Verdict:
        if self.dry_run:
            return Verdict(path, r.name, "delete", reason="dry-run，未实际删除")
        dest = os.path.join(self.trash_dir, os.path.basename(path))
        # 同名冲突加后缀，避免覆盖回收站内已有文件
        if os.path.exists(dest):
            dest = dest + ".bak"
        shutil.move(path, dest)
        return Verdict(path, r.name, "delete", deleted=True, reason="已移至回收站")

    def _move(self, path: str, r: Rule) -> Verdict:
        if self.dry_run:
            return Verdict(path, r.name, "move", reason="dry-run，未实际移动")
        dest = os.path.join(r.dest, os.path.basename(path))
        os.makedirs(r.dest, exist_ok=True)
        shutil.move(path, dest)
        return Verdict(path, r.name, "move", reason="已移动")


def _self_test() -> int:
    tmp = tempfile.mkdtemp(prefix="rule_engine_test_")
    trash = os.path.join(tmp, ".trash")
    old = os.path.join(tmp, "old_photo_2020.jpg")
    keep = os.path.join(tmp, "important.pdf")
    with open(old, "w") as f:
        f.write("x")
    with open(keep, "w") as f:
        f.write("y")

    rules = [Rule("old_img", "old_*.jpg", "delete")]
    wl = ["*.pdf"]

    # 1) 白名单保护：*.pdf 即使写得再像也不删
    e = RuleEngine(rules, wl, trash, dry_run=False)
    v = e.evaluate(keep)
    assert v.protected, "白名单未保护 important.pdf"
    assert os.path.exists(keep), "白名单文件被删了！"
    print("[OK] 白名单优先级最高，*.pdf 不被删")

    # 2) dry-run 无副作用
    e2 = RuleEngine(rules, wl, trash, dry_run=True)
    v2 = e2.evaluate(old)
    assert not v2.deleted and os.path.exists(old), "dry-run 仍删了文件"
    print("[OK] dry-run 不实际删除（只报告）")

    # 3) apply 真正删除（移到回收站，原路径消失、可找回）
    e3 = RuleEngine(rules, wl, trash, dry_run=False)
    v3 = e3.evaluate(old)
    assert v3.deleted and not os.path.exists(old), "apply 未执行删除"
    assert os.path.exists(os.path.join(trash, "old_photo_2020.jpg")), "未进回收站"
    print("[OK] apply 删除走回收站，原路径清空、可找回")

    shutil.rmtree(tmp, ignore_errors=True)
    print("ALL_SELFTESTS_PASSED")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="本地文件监控 Agent 规则引擎（删除走回收站，默认 dry-run）")
    p.add_argument("--self-test", action="store_true", help="运行内置自测")
    p.add_argument("--apply", action="store_true", help="实际执行删除/移动；默认 dry-run")
    p.add_argument("--trash", default=os.path.join(tempfile.gettempdir(), "file_watcher_trash"))
    p.add_argument("paths", nargs="*", help="待评估文件")
    args = p.parse_args(argv)

    if args.self_test:
        return _self_test()

    rules = [Rule("old_img", "old_*.jpg", "delete")]
    wl = ["*.pdf", "*.docx", "*.key", "important_*"]
    e = RuleEngine(rules, wl, args.trash, dry_run=not args.apply)
    if not args.paths:
        print("用法：02_rule_engine.py [--apply] file1 file2 ... （默认 dry-run）")
        return 0
    for pth in args.paths:
        print(e.evaluate(pth))
    return 0


if __name__ == "__main__":
    sys.exit(main())
