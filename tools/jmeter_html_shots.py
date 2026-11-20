#!/usr/bin/env python3
"""给 results/jmeter-html/ 下每份 JMeter HTML 报告截图，供实验报告引用。

用 Google Chrome 无界面模式截两页：首页 Dashboard（测试信息、APDEX、请求成功率、Statistics 表）存为
results/统计与图表/charts/jmeter-<组>-<测试名>.png；Response Times 页的 Response Time Percentiles 图存为
jmeter-<组>-<测试名>-percentiles.png。需要 Google Chrome 和 Pillow。

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
DASHBOARD_BOX = (0, 0, 2600, 1880)     # 首页：标题、左侧菜单、测试信息、APDEX、请求成功率、Statistics
PERCENTILES_BOX = (0, 0, 2600, 1745)   # Response Times 页：标题、测试信息、Response Time Percentiles 图


def shot(page_html, box, dst):
    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "page.png")
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                        "--virtual-time-budget=10000", "--window-size=1300,1000", "--screenshot=" + raw,
                        "file://" + page_html], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        Image.open(raw).convert("RGB").crop(box).save(dst, optimize=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    for group in sorted(os.listdir(HTML)):
        gdir = os.path.join(HTML, group)
        if not os.path.isdir(gdir):
            continue
        for name in sorted(os.listdir(gdir)):
            index = os.path.join(gdir, name, "index.html")
            if not os.path.exists(index):
                continue
            base = os.path.join(OUT, "jmeter-%s-%s" % (group, name))
            shot(index, DASHBOARD_BOX, base + ".png")
            shot(os.path.join(gdir, name, "content", "pages", "ResponseTimes.html"), PERCENTILES_BOX, base + "-percentiles.png")
            print("wrote", os.path.relpath(base, REPO) + ".png / -percentiles.png")


if __name__ == "__main__":
    main()
