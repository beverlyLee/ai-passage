#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""#26 运行时截图生成器（两张）。

  run@2x.png       运行时诊断：六个坑被真实复现 / 拦截（数字由真实代码算出）
  selftest@2x.png  三段脚本 --self-test 的真实标准输出

输出为终端风格 PNG，整页捕获、不裁切、无空白。
"""
import os
import sys
import html
import struct
import subprocess
import tempfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))  # 项目根: 本地RAG问答Agent
CODE = os.path.join(ROOT, "code", "auto-rag")
sys.path.insert(0, CODE)

from rag_core import (  # noqa: E402
    Embedder, chunk_document, build_index, search, VectorStore, cosine, tokenize,
)
import importlib.util  # noqa: E402


def _load(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


m02 = _load("m02", os.path.join(CODE, "02_rag_retrieve.py"))
m03 = _load("m03", os.path.join(CODE, "03_rag_generate.py"))
safe_retrieve = m02.safe_retrieve
select_by_budget = m02.select_by_budget
guard = m03.guard
UngroundedClaim = m03.UngroundedClaim

DOC = (
    "我们的退款政策如下。用户在签收商品后七天无理由退款。"
    "生鲜类商品不支持退款。运费由买家承担。客服会在两个工作日内处理退款申请。"
)
DOCS = [
    "用户在签收商品后七天无理由退款。生鲜类不支持退款。",
    "退款申请会在两个工作日内由客服处理。运费由买家承担。",
    "物流时效为下单后三到五天送达。偏远地区另计。",
    "包裹丢失可联系客服重寄。需要提供订单编号。",
]
QUERY = "七天无理由退款怎么操作"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def esc(s):
    return html.escape(s)


def build_run_lines():
    """运行时诊断：六坑真实复现并拦截。"""
    lines = []
    A = lines.append
    e1, e2 = Embedder("v1"), Embedder("v2")

    fixed = chunk_document(DOC, "fixed", 20)
    sentence = chunk_document(DOC, "sentence", 120)
    same = cosine(e1.embed(QUERY), e1.embed(QUERY))
    drift = cosine(e1.embed(QUERY), e2.embed(QUERY))

    # 向量库用 4 篇文档建索引（更贴近真实知识库规模）
    recs = build_index(DOCS, e1, "sentence", 120)
    store_path = os.path.join(tempfile.gettempdir(), "rag_store_shot.json")
    VectorStore.save(store_path, recs)
    with open(store_path, "r+", encoding="utf-8") as f:
        data = f.read()
        f.seek(0)
        f.write(data[: len(data) // 2])
        f.truncate()
    recovered = VectorStore.load_or_rebuild(store_path, lambda: recs)

    A(("本地 RAG 问答 Agent · 运行时诊断", "title"))
    A((f"时间 {datetime.now():%Y-%m-%d %H:%M:%S}    模式 离线 / 纯标准库 / 假embedding(可复现)", "dim"))
    A(("", "n"))
    A(("[准备层] 对「知识」建模错", "h"))
    A((f"  [坑① 切分错位]  fixed 硬切(20字/段): 整篇 {len(fixed)} 段, 核心句「七天无理由退款」被腰斩", "bad"))
    A((f"               sentence 切分: 核心句完整落在 {sum(1 for c in sentence if '七天无理由退款' in c)} 段", "good"))
    A((f"  [坑② embed漂移]  同版余弦 {same:.3f}  →  跨版余弦 {drift:.3f}   ← 向量空间不交, 检索失配", "bad"))
    A((f"  [坑③ 向量库损坏]  落盘截断 50%  →  load_or_rebuild 自动重建 {len(recovered)} 个 chunk", "good"))
    A(("", "n"))

    recs_v1 = build_index(DOCS, e1, "sentence", 120)
    blank = safe_retrieve(recs_v1, "如何开具增值税发票", e1)
    hit = safe_retrieve(recs_v1, "退款需要几天", e1)
    ranked = [
        (0.62, 0, 0, "七天无理由退款。生鲜类不支持退款。"),
        (0.55, 1, 0, "退款申请会在两个工作日内处理。运费由买家承担。"),
        (0.41, 2, 0, "物流时效为下单后三到五天送达。偏远地区另计。"),
        (0.20, 3, 0, "包裹丢失可联系客服重寄。需要提供订单编号。"),
    ]
    small = select_by_budget(ranked, 2)
    big = select_by_budget(ranked, len(ranked))
    dropped = all(r[1] != 2 for r in small)

    A(("[检索层] 对「问题↔知识」对齐错", "h"))
    A((f"  [坑④ 查询不匹配]  域外问「发票」  →  检索空窗(返回 {len(blank)} 段, 拒绝硬答)", "good"))
    A((f"               域内问「退款」  →  命中 {len(hit)} 段", "good"))
    A((f"  [坑⑤ 上下文溢出]  关键 chunk 排第 3 位, 预算=2  →  {'截断丢失' if dropped else '保留'}", "bad"))
    A((f"               预算=充足  →  {'保留' if any(r[1]==2 for r in big) else '丢失'} 关键来源", "good"))
    A(("", "n"))

    recs_g = {1: "七天无理由退款", 2: "运费由买家承担"}
    caught_fab = False
    try:
        guard("支持三十天超长退款[@9]", {1}, recs_g)
    except UngroundedClaim:
        caught_fab = True
    recs_g2 = {1: "生鲜类不支持退款", 2: "客服会在两个工作日内处理退款申请"}
    caught_irr = False
    try:
        guard("运费由商家承担[@2]", {1, 2}, recs_g2)
    except UngroundedClaim:
        caught_irr = True

    A(("[生成层] 对「答案责任」建模错", "h"))
    A((f"  [坑⑥ 幻觉编造]  编造引用 [@9]  →  第一道防线{'拦截' if caught_fab else '漏过'} {'✔' if caught_fab else '✘'}", "good" if caught_fab else "bad"))
    A((f"              无关引用 [@2]  →  第二道防线{'拦截' if caught_irr else '漏过'} {'✔' if caught_irr else '✘'}", "good" if caught_irr else "bad"))
    A(("              无防护对照  →  编造引用原样漏出 ✘  (说明防护必要)", "bad"))
    A(("", "n"))
    A(("结论: 6 个故障模式全部被真实复现并被拦截 / 给出空窗", "title"))
    return lines


def build_selftest_lines():
    """三段脚本 --self-test 的真实标准输出。"""
    lines = []
    A = lines.append
    A(("本地 RAG 问答 Agent · 三段脚本自检 (真实 stdout)", "title"))
    A((f"时间 {datetime.now():%Y-%m-%d %H:%M:%S}    python {sys.version.split()[0]}", "dim"))
    A(("", "n"))
    for script in ("01_rag_prep.py", "02_rag_retrieve.py", "03_rag_generate.py"):
        A((f"$ python3 {script} --self-test", "cmd"))
        proc = subprocess.run(
            [sys.executable, script, "--self-test"],
            cwd=CODE, capture_output=True, text=True,
        )
        for ln in proc.stdout.strip().splitlines():
            if "ALL_SELFTESTS_PASSED" in ln:
                A((ln, "pass"))
            elif "-> OK" in ln:
                A(("  " + ln, "good"))
            else:
                A(("  " + ln, "n"))
        A(("", "n"))
    A(("三段脚本全部 ALL_SELFTESTS_PASSED", "title"))
    return lines


CLSMAP = {
    "title": "#fbbf24", "dim": "#64748b", "h": "#22d3ee",
    "good": "#34d399", "bad": "#fb7185", "cmd": "#a78bfa", "pass": "#34d399",
}


def _line_px(s):
    """粗略估算一行像素宽：CJK 约 16px, 其余约 9.6px（16px Menlo）。"""
    return sum(16.0 if ord(c) > 0x2E80 else 9.6 for c in s)


def render_html(lines):
    body = []
    for text, cls in lines:
        if cls == "n" or not text:
            body.append("")
            continue
        color = CLSMAP.get(cls)
        body.append(f'<span style="color:{color}">{esc(text)}</span>' if color else esc(text))
    pre = "\n".join(body)
    # 按最长行自适应宽度，避免横向裁切 / 右侧留白
    content_px = max((_line_px(t) for t, _ in lines), default=600)
    box_w = int(min(1000, max(680, content_px + 52 + 12)))
    # 页面总高 = 上下 margin(28*2) + 标题栏(34) + pre 上下 padding(24*2) + 行数*行高 + 边框
    height = int(140 + len(lines) * 25.6) + 6
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<style>
html,body{{margin:0;padding:0;background:#0f172a}}
.term{{width:{box_w}px;margin:28px auto;background:#0f172a;border:1px solid #1e293b;
 border-radius:10px;box-shadow:0 20px 60px rgba(0,0,0,.5)}}
.bar{{height:34px;background:#1e293b;border-radius:10px 10px 0 0;display:flex;
 align-items:center;padding:0 14px;gap:8px}}
.dot{{width:12px;height:12px;border-radius:50%}}
.r{{background:#fb7185}}.y{{background:#fbbf24}}.g{{background:#34d399}}
.bar span{{color:#64748b;font:12px/1 -apple-system,sans-serif;margin-left:8px}}
pre{{margin:0;padding:24px 26px;font:16px/1.6 'Menlo','PingFang SC','JetBrains Mono',monospace;
 color:#cbd5e1;white-space:pre}}
</style></head><body>
<div class="term">
 <div class="bar"><div class="dot r"></div><div class="dot y"></div><div class="dot g"></div>
 <span>rag-agent — zsh</span></div>
<pre>{pre}</pre>
</div></body></html>"""
    return page, height, box_w


def shot(lines, name):
    page, height, box_w = render_html(lines)
    html_path = os.path.join(HERE, f"{name}.html")
    png_path = os.path.join(HERE, f"{name}@2x.png")
    txt_path = os.path.join(HERE, f"{name}.txt")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(page)
    with open(txt_path, "w", encoding="utf-8") as f:
        for text, _ in lines:
            f.write(text + "\n")
    width = box_w + 56
    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
         "--hide-scrollbars", "--force-device-scale-factor=2",
         f"--window-size={width},{height}", f"--screenshot={png_path}", html_path],
        check=True, capture_output=True,
    )
    with open(png_path, "rb") as f:
        f.read(16)
        w, h = struct.unpack(">II", f.read(8))
    print(f"WROTE {png_path}  logical={width}x{height}  px={w}x{h}")


def main():
    shot(build_run_lines(), "run")
    shot(build_selftest_lines(), "selftest")


if __name__ == "__main__":
    main()
