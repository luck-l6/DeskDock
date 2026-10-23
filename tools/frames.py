import subprocess
import time

from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QApplication

APP = QApplication([])
scr = QGuiApplication.primaryScreen()

PYW = r"C:\Users\15549\AppData\Local\Programs\Python\Python312\pythonw.exe"
MAIN = r"C:\Users\15549\WorkBuddy\desk-space\main.py"
OUT = r"C:\Users\15549\WorkBuddy\desk-space"

lines = []
saved = False
proc = subprocess.Popen([PYW, MAIN])
t0 = time.time()
while time.time() - t0 < 1.6:
    img = scr.grabWindow(0).toImage()
    small = img.scaled(64, 40)
    tot = 0.0
    for y in range(40):
        for x in range(64):
            c = small.pixelColor(x, y)
            tot += (c.red() + c.green() + c.blue()) / 3.0
    mean = tot / (64 * 40)
    t = time.time() - t0
    lines.append((t, mean))
    if not saved and mean > 150:
        img.scaled(320, 200).save(OUT + "/bright.png")
        # 数值判断是不是纯白：统计像素方差与极值
        vals = []
        for y in range(0, 200, 5):
            for x in range(0, 320, 5):
                c = small.pixelColor(x % 64, y % 40)
                vals.append(c.red())
        vmin, vmax = min(vals), max(vals)
        vavg = sum(vals) / len(vals)
        var = sum((v - vavg) ** 2 for v in vals) / len(vals)
        lines.append((t, -1))  # 标记
        with open(OUT + "/bright_stats.txt", "w", encoding="utf-8") as fh:
            fh.write(f"mean={vavg:.1f} min={vmin} max={vmax} var={var:.1f}\n")
        saved = True
    time.sleep(0.015)

try:
    proc.wait(timeout=15)
except Exception:
    pass

with open(OUT + "/frames.log", "w", encoding="utf-8") as fh:
    for t, m in lines:
        fh.write(f"t={t:5.3f} mean={m:6.1f}\n" if m >= 0 else f"t={t:5.3f} <<<已保存亮帧\n")
