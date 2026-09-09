#!/usr/bin/env python3
# Render diagram/memory/*.svg -> *@2x.png (1360x900) via Chrome headless.
import subprocess, os, glob, struct

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SVG_DIR = "/Users/liboyang/WorkBuddy/2026-08-14-17-18-24/diagram/memory"

HTML_TPL = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
  html,body {{ margin:0; padding:0; background:#0f172a; width:680px; height:450px; overflow:hidden; }}
  svg {{ display:block; width:680px; height:450px; }}
</style></head><body>
{svg}
</body></html>"""


def png_size(path):
    with open(path, 'rb') as f:
        data = f.read(33)
    w, h = struct.unpack('>II', data[16:24])
    return w, h


def main():
    svgs = sorted(glob.glob(os.path.join(SVG_DIR, '*.svg')))
    for svg in svgs:
        name = os.path.basename(svg)[:-4]
        with open(svg, encoding='utf-8') as f:
            content = f.read()
        html_path = svg[:-4] + '_render.html'
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(HTML_TPL.format(svg=content))
        out = svg[:-4] + '@2x.png'
        subprocess.run([CHROME, '--headless=new', '--disable-gpu', '--no-sandbox',
                        '--hide-scrollbars', '--force-device-scale-factor=2',
                        '--window-size=680,450', '--screenshot=' + out, html_path],
                       capture_output=True)
        if os.path.exists(out):
            w, h = png_size(out)
            flag = 'OK' if (w, h) == (1360, 900) else 'SIZE-WRONG'
            print(f"{name}: {w}x{h} {flag}")
        else:
            print(f"{name}: FAILED - no output")
        os.remove(html_path)


if __name__ == '__main__':
    main()
