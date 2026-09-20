#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_svgs.py — 生成 5 张深色 SVG 配图并渲染为 @2x PNG（1360x900）。

渲染走 Chrome headless：
  --headless --disable-gpu --no-sandbox --hide-scrollbars
  --force-device-scale-factor=2 --window-size=680,450 --screenshot

本机 Read 图片被拦截，故只逐行审 SVG 源码，并用 sips 校验 PNG 尺寸。
SVG 约束：viewBox 0 0 680 450，bg #0f172a，grid #1e293b，
          cyan #22d3ee / rose #fb7185 / amber #fbbf24，最右元素 x+width < 680。
"""
import os
import subprocess
import html

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FONT = "Noto Sans SC, PingFang SC, Microsoft YaHei, sans-serif"

SVGS = {}

# 1) 故障树全景
SVGS["01_fault_tree"] = f'''<svg xmlns="http://www.w3.org/2000/svg" width="680" height="450" viewBox="0 0 680 450">
  <rect width="680" height="450" fill="#0f172a"/>
  <g stroke="#1e293b" stroke-width="1">
    <line x1="0" y1="150" x2="680" y2="150"/>
    <line x1="0" y1="330" x2="680" y2="330"/>
    <line x1="227" y1="0" x2="227" y2="450"/>
    <line x1="453" y1="0" x2="453" y2="450"/>
  </g>
  <text x="24" y="30" fill="#e2e8f0" font-family="{FONT}" font-size="18">故障树全景：Agent 静默失败</text>
  <rect x="225" y="48" width="230" height="46" rx="8" fill="#1e293b" stroke="#22d3ee" stroke-width="2"/>
  <text x="340" y="67" text-anchor="middle" fill="#22d3ee" font-family="{FONT}" font-size="14">大症状</text>
  <text x="340" y="86" text-anchor="middle" fill="#e2e8f0" font-family="{FONT}" font-size="14">声明即验收</text>
  <rect x="20" y="177" width="195" height="100" rx="8" fill="#1e293b" stroke="#fb7185" stroke-width="1.5"/>
  <text x="117" y="200" text-anchor="middle" fill="#fb7185" font-family="{FONT}" font-size="13">失败模式一</text>
  <text x="117" y="222" text-anchor="middle" fill="#cbd5e1" font-family="{FONT}" font-size="12">工具返回空/含糊</text>
  <text x="117" y="240" text-anchor="middle" fill="#cbd5e1" font-family="{FONT}" font-size="12">就脑补成功</text>
  <text x="117" y="260" text-anchor="middle" fill="#94a3b8" font-family="{FONT}" font-size="11">单控制失败 44-52%</text>
  <rect x="242" y="177" width="195" height="100" rx="8" fill="#1e293b" stroke="#fb7185" stroke-width="1.5"/>
  <text x="340" y="200" text-anchor="middle" fill="#fb7185" font-family="{FONT}" font-size="13">失败模式二</text>
  <text x="340" y="222" text-anchor="middle" fill="#cbd5e1" font-family="{FONT}" font-size="12">改了一部分没全改</text>
  <text x="340" y="240" text-anchor="middle" fill="#cbd5e1" font-family="{FONT}" font-size="12">调用图盲区</text>
  <text x="340" y="260" text-anchor="middle" fill="#94a3b8" font-family="{FONT}" font-size="11">Fake Done 重灾区</text>
  <rect x="464" y="177" width="195" height="100" rx="8" fill="#1e293b" stroke="#fb7185" stroke-width="1.5"/>
  <text x="562" y="200" text-anchor="middle" fill="#fb7185" font-family="{FONT}" font-size="13">失败模式三</text>
  <text x="562" y="222" text-anchor="middle" fill="#cbd5e1" font-family="{FONT}" font-size="12">reviewer 也是 Agent</text>
  <text x="562" y="240" text-anchor="middle" fill="#cbd5e1" font-family="{FONT}" font-size="12">谎言被二次包装</text>
  <text x="562" y="260" text-anchor="middle" fill="#94a3b8" font-family="{FONT}" font-size="11">裁判 AUROC 0.54-0.65</text>
  <g stroke="#475569" stroke-width="1.5" fill="none">
    <path d="M340,94 L117,175"/>
    <path d="M340,94 L340,175"/>
    <path d="M340,94 L562,175"/>
  </g>
  <rect x="170" y="352" width="340" height="64" rx="8" fill="#312e81" stroke="#fbbf24" stroke-width="2"/>
  <text x="340" y="375" text-anchor="middle" fill="#fbbf24" font-family="{FONT}" font-size="14">共享总根</text>
  <text x="340" y="395" text-anchor="middle" fill="#e2e8f0" font-family="{FONT}" font-size="12">行动与检查是同一拍</text>
  <text x="340" y="412" text-anchor="middle" fill="#cbd5e1" font-family="{FONT}" font-size="11">模型把最可能的续写当成已发生的状态</text>
  <g stroke="#475569" stroke-width="1.5" fill="none">
    <path d="M117,279 L340,350"/>
    <path d="M340,279 L340,350"/>
    <path d="M562,279 L340,350"/>
  </g>
</svg>'''

# 2) 声明即验收 vs 完成契约
SVGS["02_contract"] = f'''<svg xmlns="http://www.w3.org/2000/svg" width="680" height="450" viewBox="0 0 680 450">
  <rect width="680" height="450" fill="#0f172a"/>
  <text x="24" y="30" fill="#e2e8f0" font-family="{FONT}" font-size="18">声明即验收 对比 完成契约</text>
  <rect x="20" y="55" width="305" height="320" rx="10" fill="#1e293b" stroke="#fb7185" stroke-width="1.5"/>
  <text x="172" y="84" text-anchor="middle" fill="#fb7185" font-family="{FONT}" font-size="16">声明即验收（裸奔）</text>
  <g fill="#cbd5e1" font-family="{FONT}" font-size="13">
    <text x="40" y="120">· 工具返回即收工</text>
    <text x="40" y="150">· 改了就当成达成了</text>
    <text x="40" y="180">· LLM reviewer 读报告判定</text>
    <text x="40" y="210">· 谎报被盖了章</text>
    <text x="40" y="240">· 验收权威 = 模型的嘴</text>
  </g>
  <text x="40" y="290" fill="#94a3b8" font-family="{FONT}" font-size="12">结局：hidden 处 0 落地却报 done</text>
  <text x="40" y="320" fill="#94a3b8" font-family="{FONT}" font-size="12">论文：单控制失败 44-52%</text>
  <text x="40" y="350" fill="#94a3b8" font-family="{FONT}" font-size="12">双控制 3%，被压一个数量级</text>
  <rect x="355" y="55" width="305" height="320" rx="10" fill="#1e293b" stroke="#22d3ee" stroke-width="1.5"/>
  <text x="507" y="84" text-anchor="middle" fill="#22d3ee" font-family="{FONT}" font-size="16">完成契约（加固）</text>
  <g fill="#cbd5e1" font-family="{FONT}" font-size="13">
    <text x="375" y="120">· 重新读取真实状态复核</text>
    <text x="375" y="150">· 完成 = 算出来的状态</text>
    <text x="375" y="180">· 独立验证层校验</text>
    <text x="375" y="210">· 有缺口就交出来</text>
    <text x="375" y="240">· 验收权威 = 系统的账本</text>
  </g>
  <text x="375" y="290" fill="#94a3b8" font-family="{FONT}" font-size="12">结局：拦截假完成，列出缺口</text>
  <text x="375" y="320" fill="#94a3b8" font-family="{FONT}" font-size="12">轻量 TF-IDF 监控 AUROC 0.83/0.95</text>
  <text x="375" y="350" fill="#94a3b8" font-family="{FONT}" font-size="12">同标记率多找回 4-8 倍假完成</text>
  <g stroke="#fbbf24" stroke-width="2" fill="none">
    <path d="M325,215 C340,215 340,225 355,225"/>
    <polygon points="355,225 347,220 347,230" fill="#fbbf24" stroke="none"/>
  </g>
  <text x="340" y="430" text-anchor="middle" fill="#fbbf24" font-family="{FONT}" font-size="13">把验收权威从声明挪回状态</text>
</svg>'''

# 3) 论文数字证据
SVGS["03_evidence"] = f'''<svg xmlns="http://www.w3.org/2000/svg" width="680" height="450" viewBox="0 0 680 450">
  <rect width="680" height="450" fill="#0f172a"/>
  <text x="24" y="30" fill="#e2e8f0" font-family="{FONT}" font-size="18">论文数字证据（arXiv 2606.09863）</text>
  <text x="24" y="58" fill="#94a3b8" font-family="{FONT}" font-size="12">虚假成功占失败的比例（左）  监控区分能力 AUROC（右，越高越好）</text>
  <g font-family="{FONT}" font-size="12" fill="#cbd5e1">
    <text x="40" y="92">单控制 tau2-bench</text>
    <text x="40" y="150">双控制 电信域</text>
    <text x="40" y="208">AppWorld 编码 Agent</text>
  </g>
  <!-- bars left: max scale 80% -> 200px per 80 => 2.5px per percent -->
  <g>
    <rect x="180" y="78" width="115" height="22" fill="#fb7185"/>
    <text x="305" y="94" fill="#e2e8f0" font-family="{FONT}" font-size="12">45-48%</text>
    <rect x="180" y="136" width="7.5" height="22" fill="#22d3ee"/>
    <text x="195" y="152" fill="#e2e8f0" font-family="{FONT}" font-size="12">3%</text>
    <rect x="180" y="194" width="190" height="22" fill="#fb7185"/>
    <text x="380" y="210" fill="#e2e8f0" font-family="{FONT}" font-size="12">75.8%</text>
  </g>
  <!-- right: AUROC bars, scale 1.0 -> 100px -->
  <text x="420" y="92" fill="#cbd5e1" font-family="{FONT}" font-size="12">LLM 裁判 tau2</text>
  <rect x="550" y="78" width="65" height="22" fill="#fb7185"/>
  <text x="621" y="94" fill="#e2e8f0" font-family="{FONT}" font-size="12">0.65</text>
  <text x="420" y="150" fill="#cbd5e1" font-family="{FONT}" font-size="12">LLM 裁判 AppWorld</text>
  <rect x="550" y="136" width="54" height="22" fill="#fb7185"/>
  <text x="610" y="152" fill="#e2e8f0" font-family="{FONT}" font-size="12">0.54</text>
  <text x="420" y="208" fill="#cbd5e1" font-family="{FONT}" font-size="12">TF-IDF tau2</text>
  <rect x="550" y="194" width="83" height="22" fill="#22d3ee"/>
  <text x="639" y="210" fill="#e2e8f0" font-family="{FONT}" font-size="12">0.83</text>
  <text x="420" y="266" fill="#cbd5e1" font-family="{FONT}" font-size="12">TF-IDF AppWorld</text>
  <rect x="550" y="252" width="95" height="22" fill="#22d3ee"/>
  <text x="651" y="268" fill="#e2e8f0" font-family="{FONT}" font-size="12">0.95</text>
  <text x="430" y="320" fill="#94a3b8" font-family="{FONT}" font-size="11">同标记率下 TF-IDF 多找回 4-8x 假完成</text>
  <text x="430" y="342" fill="#94a3b8" font-family="{FONT}" font-size="11">延迟低 3300x；推理模型无保护</text>
  <text x="430" y="364" fill="#94a3b8" font-family="{FONT}" font-size="11">Qwen3-Max-Thinking 虚假率最高 79%</text>
  <text x="430" y="392" fill="#fbbf24" font-family="{FONT}" font-size="12">per-model 跨度 13%-89%</text>
</svg>'''

# 4) 调用图盲区
SVGS["04_blindspot"] = f'''<svg xmlns="http://www.w3.org/2000/svg" width="680" height="450" viewBox="0 0 680 450">
  <rect width="680" height="450" fill="#0f172a"/>
  <text x="24" y="30" fill="#e2e8f0" font-family="{FONT}" font-size="18">编码 Agent 调用图盲区</text>
  <text x="24" y="54" fill="#94a3b8" font-family="{FONT}" font-size="12">grep 找字符串而非调用图：Agent 只看到探索过的目录</text>
  <!-- Agent view -->
  <rect x="20" y="70" width="300" height="200" rx="10" fill="#1e293b" stroke="#22d3ee" stroke-width="1.5"/>
  <text x="170" y="95" text-anchor="middle" fill="#22d3ee" font-family="{FONT}" font-size="14">Agent 视野（grep 命中）</text>
  <g font-family="{FONT}" font-size="12" fill="#cbd5e1">
    <text x="40" y="125">src/api/auth.ts</text>
    <text x="40" y="150">src/middleware/token.ts</text>
    <text x="40" y="175">src/services/login.ts</text>
    <text x="40" y="200">src/api/payment.ts</text>
    <text x="40" y="225">src/services/order.ts</text>
    <text x="40" y="250">src/services/session.ts</text>
  </g>
  <!-- real call graph -->
  <rect x="360" y="70" width="300" height="320" rx="10" fill="#1e293b" stroke="#fb7185" stroke-width="1.5"/>
  <text x="510" y="95" text-anchor="middle" fill="#fb7185" font-family="{FONT}" font-size="14">真实调用图（全量）</text>
  <g font-family="{FONT}" font-size="12" fill="#cbd5e1">
    <text x="380" y="125">src/api/auth.ts</text>
    <text x="380" y="150">src/middleware/token.ts</text>
    <text x="380" y="175">src/services/login.ts</text>
    <text x="380" y="200">src/api/payment.ts</text>
    <text x="380" y="225">src/services/order.ts</text>
    <text x="380" y="250">src/services/session.ts</text>
  </g>
  <g font-family="{FONT}" font-size="12" fill="#fbbf24">
    <text x="380" y="285">src/cron/cleanup.ts  ← 从未 grep</text>
    <text x="380" y="310">src/cron/refresh.ts  ← 从未 grep</text>
    <text x="380" y="335">src/jobs/admin.ts     ← 从未 grep</text>
    <text x="380" y="360">src/jobs/rate_limit.ts ← 从未 grep</text>
  </g>
  <g stroke="#fb7185" stroke-width="1.5" stroke-dasharray="5,4" fill="none">
    <path d="M320,170 C345,170 345,210 360,210"/>
  </g>
  <text x="340" y="430" text-anchor="middle" fill="#fbbf24" font-family="{FONT}" font-size="13">4 处缺口藏在 Agent 没打开过的目录里</text>
</svg>'''

# 5) LLM 裁判失效 vs 轻量检测器
SVGS["05_judge"] = f'''<svg xmlns="http://www.w3.org/2000/svg" width="680" height="450" viewBox="0 0 680 450">
  <rect width="680" height="450" fill="#0f172a"/>
  <text x="24" y="30" fill="#e2e8f0" font-family="{FONT}" font-size="18">LLM 裁判失效 对比 轻量检测器</text>
  <rect x="20" y="55" width="305" height="320" rx="10" fill="#1e293b" stroke="#fb7185" stroke-width="1.5"/>
  <text x="172" y="84" text-anchor="middle" fill="#fb7185" font-family="{FONT}" font-size="16">LLM 裁判（AUROC 0.54-0.65）</text>
  <g fill="#cbd5e1" font-family="{FONT}" font-size="13">
    <text x="40" y="120">· 锚定自信收尾语言</text>
    <text x="40" y="150">· tau2: 带断言词 +0.27~0.36 完成</text>
    <text x="40" y="180">· AppWorld: 锚定动作序列量</text>
    <text x="40" y="210">· 数的是姿势不是状态</text>
    <text x="40" y="240">· 推理模型也中招</text>
  </g>
  <text x="40" y="290" fill="#94a3b8" font-family="{FONT}" font-size="12">结局：谎言被判为通过</text>
  <text x="40" y="320" fill="#94a3b8" font-family="{FONT}" font-size="12">等于没兜，甚至盖章</text>
  <rect x="355" y="55" width="305" height="320" rx="10" fill="#1e293b" stroke="#22d3ee" stroke-width="1.5"/>
  <text x="507" y="84" text-anchor="middle" fill="#22d3ee" font-family="{FONT}" font-size="16">轻量 TF-IDF（AUROC 0.83/0.95）</text>
  <g fill="#cbd5e1" font-family="{FONT}" font-size="13">
    <text x="375" y="120">· 读真实状态变化</text>
    <text x="375" y="150">· 领域校准的触发器</text>
    <text x="375" y="180">· 同标记率多找回 4-8x</text>
    <text x="375" y="210">· 延迟低 3300x</text>
    <text x="375" y="240">· 零 LLM 在检索</text>
  </g>
  <text x="375" y="290" fill="#94a3b8" font-family="{FONT}" font-size="12">结局：当作 triage 信号</text>
  <text x="375" y="320" fill="#94a3b8" font-family="{FONT}" font-size="12">不替代主力监控</text>
  <g stroke="#fbbf24" stroke-width="2" fill="none">
    <path d="M325,215 C340,215 340,225 355,225"/>
    <polygon points="355,225 347,220 347,230" fill="#fbbf24" stroke="none"/>
  </g>
  <text x="340" y="430" text-anchor="middle" fill="#fbbf24" font-family="{FONT}" font-size="13">监控该用轻量检测器做初筛，而非 LLM 裁判</text>
</svg>'''


def write_and_render():
    for name, svg in SVGS.items():
        svg_path = os.path.join(HERE, name + ".svg")
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg)
        # 包成 HTML，固定 680x450 + 深色底，避免白边
        html_path = os.path.join(HERE, name + ".html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(
                f'<html><head><meta charset="utf-8"></head>'
                f'<body style="margin:0;background:#0f172a;width:680px;height:450px;">'
                f'{svg}</body></html>'
            )
        png_path = os.path.join(HERE, name + "@2x.png")
        cmd = [
            CHROME, "--headless", "--disable-gpu", "--no-sandbox",
            "--hide-scrollbars", "--force-device-scale-factor=2",
            "--window-size=680,450", f"--screenshot={png_path}", html_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        # 校验尺寸
        out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", png_path],
                             capture_output=True, text=True)
        print(name, "->", " ".join(out.stdout.split()))
        # 清理临时 html
        os.remove(html_path)
    print("done")


if __name__ == "__main__":
    write_and_render()
