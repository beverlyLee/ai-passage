#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render diagram/ai-kefu-fan-che/*.svg -> *.@2x.png (1360x900).

Chrome headless --force-device-scale-factor=2 --window-size=680,450 渲染。
"""
import subprocess, os, glob, struct

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SVG_DIR = "/Users/liboyang/WorkBuddy/2026-08-14-17-18-24/ai-passage/2026-09-14-AI客服为什么翻车/diagram/ai-kefu-fan-che"


def png_size(path):
    with open(path, 'rb') as f:
        data = f.read(33)
    w, h = struct.unpack('>II', data[16:24])
    return w, h


def main():
    svgs = sorted(glob.glob(os.path.join(SVG_DIR, '*.svg')))
    for svg in svgs:
        name = os.path.basename(svg)[:-4]
        with open(svg) as f:
            content = f.read()
        html = ('<!doctype html><html><head><meta charset="utf-8">'
                '<style>html,body{margin:0;padding:0;background:#0f172a}'
                'svg{display:block}</style></head><body>' + content + '</body></html>')
        html_path = svg[:-4] + '_render.html'
        with open(html_path, 'w') as f:
            f.write(html)
        out = svg[:-4] + '@2x.png'
        subprocess.run([CHROME, '--headless=new', '--disable-gpu', '--no-sandbox',
                        '--hide-scrollbars', '--force-device-scale-factor=2',
                        '--window-size=680,450', '--screenshot=' + out, html_path],
                       capture_output=True)
        if os.path.exists(out):
            w, h = png_size(out)
            print(f"{name}: {w}x{h} {'OK' if (w, h) == (1360, 900) else 'SIZE-WRONG'}")
        else:
            print(f"{name}: FAILED")


if __name__ == "__main__":
    main()
