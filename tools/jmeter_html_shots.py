#!/usr/bin/env python3
"""给 results/jmeter-html/ 下每份 JMeter HTML 报告截图，供实验报告引用。

用 Google Chrome 无界面模式打开每份报告的首页（Dashboard），截取页面标题和 Statistics 表格两部分拼成一张图，
存为 results/统计与图表/charts/jmeter-<组>-<测试名>.png。需要 Google Chrome 和 Pillow。

用法：python3 tools/jmeter_html_shots.py
"""
import os
import subprocess
import tempfile

from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(REPO, "results", "jmeter-html")
OUT = os.path.join(REPO, "results", "统计与图表", "charts")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# 窗口 1300×1000、缩放 2 倍时 JMeter 5.6 Dashboard 的版面位置（像素）
TITLE_BOX = (0, 0, 2050, 100)          # 页面标题（报告名）
STATS_BOX = (520, 1340, 2570, 1875)    # Statistics 面板


def shot(index_html, dst):
    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "page.png")
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                        "--virtual-time-budget=8000", "--window-size=1300,1000", "--screenshot=" + raw,
                        "file://" + index_html], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        page = Image.open(raw).convert("RGB")
        title, stats = page.crop(TITLE_BOX), page.crop(STATS_BOX)
        out = Image.new("RGB", (stats.width, title.height + stats.height), "white")
        out.paste(title, (0, 0))
        out.paste(stats, (0, title.height))
        out.save(dst, optimize=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    for group in sorted(os.listdir(HTML)):
        gdir = os.path.join(HTML, group)
        if not os.path.isdir(gdir):
            continue
        for name in sorted(os.listdir(gdir)):
            index = os.path.join(gdir, name, "index.html")
            if os.path.exists(index):
                dst = os.path.join(OUT, "jmeter-%s-%s.png" % (group, name))
                shot(index, dst)
                print("wrote", os.path.relpath(dst, REPO))


if __name__ == "__main__":
    main()
