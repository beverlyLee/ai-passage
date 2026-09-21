#!/usr/bin/env python3
# 真实运行截图生成器：把 code/ 下脚本的真实终端输出渲染成 @2x png。
#
# 流程：subprocess 真跑命令 -> 抓 stdout -> 终端样式 HTML -> Chrome headless @2x
#      -> PIL 按内容包围盒精确裁切（保证不切字、不留大片空白）。
#
# 运行（需 PIL，用受管 venv）：
#   /Users/liboyang/.workbuddy/binaries/python/envs/default/bin/python gen_shot.py
#
# 注意：本机 Read 图片被系统拦截，故渲染后只能校验尺寸与内容包围盒，
#      不能肉眼看图。这里用"内容包围盒 + 底边留白"来自证没切字。
import html
import os
import re
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DIAGRAM = os.path.dirname(HERE)
ROOT = os.path.dirname(DIAGRAM)

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PY = sys.executable

BG_OUTER = (15, 23, 42)      # #0f172a 与其它配图同底色
FS = 15
LH = 23
BODY_PAD = 18
BAR_H = 34
PRE_PAD = 16
PANEL_W = 644
IMG_W = PANEL_W + BODY_PAD * 2


def run(cmd, cwd):
    """真跑一条命令，返回 (完整显示行文本, 退出码)。"""
    p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    return out.rstrip("\n"), p.returncode


def esc(s):
    return html.escape(s, quote=False)


CJK = r"\u4e00-\u9fff"


def highlight(line):
    """逐行上色：shell 提示符 / PASS / 放行-拦截-判定词。内容保持逐字原样。"""
    if line.startswith("$ "):
        return f'<span class="p">$</span> {esc(line[2:])}'
    if line.startswith("self-test PASS"):
        return f'<span class="ok">{esc(line)}</span>'
    if set(line.strip()) == {"-"} and line.strip():
        return f'<span class="dim">{esc(line)}</span>'
    s = esc(line)
    # 只给独立成词的判定词上色，避免把"误拦截率"表头也染色
    for word, cls in (("误拦截", "warn"), ("误放行", "bad"), ("正确", "ok"),
                      ("放行", "info"), ("拦截", "warn")):
        s = re.sub(rf"(?<![{CJK}]){word}(?![{CJK}])", f'<span class="{cls}">{word}</span>', s)
    return s


def build_html(seq):
    """seq: [(命令标题, [(行, 是否命令), ...]), ...]"""
    lines_html = []
    for title, lines in seq:
        for text, is_cmd in lines:
            if is_cmd:
                lines_html.append(f'<span class="p">$</span> {esc(text)}')
            else:
                lines_html.append(highlight(text))
    n = len(lines_html)
    body = "\n".join(lines_html)
    h = BODY_PAD + BAR_H + (1 + PRE_PAD * 2 + n * LH) + BODY_PAD
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
  @font-face {{ font-family:'JBM'; src:local('JetBrains Mono'),local('Menlo'),local('Courier New'); }}
  html,body {{ margin:0; padding:0; background:#0f172a; }}
  .win {{ width:{IMG_W}px; padding:{BODY_PAD}px; box-sizing:border-box; }}
  .bar {{ height:{BAR_H}px; background:#1e293b; border-radius:10px 10px 0 0;
          display:flex; align-items:center; padding:0 14px; }}
  .dot {{ width:11px; height:11px; border-radius:50%; margin-right:8px; }}
  .title {{ margin-left:8px; font-family:'JBM','Noto Sans SC',monospace;
            font-size:12px; color:#94a3b8; }}
  pre {{ margin:0; background:#111c33; border:1px solid #1e293b; border-top:0;
         border-radius:0 0 10px 10px; padding:{PRE_PAD}px 18px;
         font-family:'JBM','Noto Sans Mono CJK SC','Noto Sans SC',monospace;
         font-size:{FS}px; line-height:{LH}px; color:#cbd5e1; white-space:pre; }}
  .p {{ color:#22d3ee; font-weight:700; }}
  .ok {{ color:#34d399; }}
  .dim {{ color:#475569; }}
  .warn {{ color:#fbbf24; }}
  .bad {{ color:#fb7185; }}
  .info {{ color:#22d3ee; }}
</style></head><body><div class="win">
  <div class="bar">
    <span class="dot" style="background:#fb7185"></span>
    <span class="dot" style="background:#fbbf24"></span>
    <span class="dot" style="background:#22d3ee"></span>
    <span class="title">{esc(seq[0][0])}</span>
  </div>
  <pre>{body}</pre>
</div></body></html>
"""


def png_wh(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def render(name, seq):
    doc = os.path.join(HERE, f"_{name}.html")
    raw = os.path.join(HERE, f"_{name}_raw.png")
    out = os.path.join(DIAGRAM, f"{name}@2x.png")
    with open(doc, "w", encoding="utf-8") as f:
        f.write(build_html(seq))
    subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-sandbox",
                    "--hide-scrollbars", "--force-device-scale-factor=2",
                    f"--window-size={IMG_W},{900}", f"--screenshot={raw}", doc],
                   capture_output=True)
    from PIL import Image
    im = Image.open(raw).convert("RGB")
    px = im.load()
    W, H = im.size
    bg = BG_OUTER
    # 找非底色像素的包围盒（即终端面板范围）
    minx, miny, maxx, maxy = W, H, -1, -1
    for y in range(H):
        row_hit = False
        for x in range(0, W, 2):
            if px[x, y] != bg:
                minx = min(minx, x); maxx = max(maxx, x); row_hit = True
        if row_hit:
            miny = min(miny, y); maxy = max(maxy, y)
    pad = BODY_PAD * 2
    minx = max(0, minx - pad); miny = max(0, miny - pad)
    maxx = min(W - 1, maxx + pad); maxy = min(H - 1, maxy + pad)
    # 面板是矩形且从 y=0 起，宽度应等于整幅宽
    minx, maxx = 0, W - 1
    im2 = im.crop((minx, miny, maxx + 1, maxy + 1))
    im2.save(out)
    os.remove(raw); os.remove(doc)
    w, h = png_wh(out)
    print(f"[ok] {os.path.basename(out)}  {w}x{h}  "
          f"(内容底边 y={maxy} / 原始 {H}, 底部余量 {H - 1 - maxy}px)")
    return out


def main():
    demo, rc1 = run(f"{PY} code/gate.py --self-test", ROOT)
    demo2, rc2 = run(f"{PY} code/gate.py --demo", ROOT)
    sweep, rc3 = run(f"{PY} code/threshold_sweep.py", ROOT)
    assert rc1 == rc2 == rc3 == 0, (rc1, rc2, rc3)
    assert "PASS" in demo and "PASS" in sweep

    seq1 = [("gate.py  真实运行输出",
             [("python3 code/gate.py --self-test", True)] +
             [(l, False) for l in demo.split("\n")] +
             [("python3 code/gate.py --demo", True)] +
             [(l, False) for l in demo2.split("\n")])]
    seq2 = [("threshold_sweep.py  真实运行输出",
             [("python3 code/threshold_sweep.py", True)] +
             [(l, False) for l in sweep.split("\n")])]

    render("05_gate_demo", seq1)
    render("06_threshold_sweep_run", seq2)

    ev = os.path.join(HERE, "run_output.txt")
    with open(ev, "w", encoding="utf-8") as f:
        f.write("== python3 code/gate.py --self-test ==\n" + demo + "\n\n")
        f.write("== python3 code/gate.py --demo ==\n" + demo2 + "\n\n")
        f.write("== python3 code/threshold_sweep.py ==\n" + sweep + "\n")
    print(f"[ok] 文本证据 {os.path.relpath(ev, ROOT)}")


if __name__ == "__main__":
    main()
