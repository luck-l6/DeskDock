"""把两帧（唤出前 / 唤出后）转成 24x12 的亮度数字矩阵，肉眼无法看图时靠它判断。"""

import subprocess
import time

from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QApplication

APP = QApplication([])
scr = QGuiApplication.primaryScreen()
PYW = r"C:\Users\15549\AppData\Local\Programs\Python\Python312\pythonw.exe"
MAIN = r"C:\Users\15549\WorkBuddy\desk-space\main.py"
OUT = r"C:\Users\15549\WorkBuddy\desk-space"

W, H = 48, 20


def grid():
    img = scr.grabWindow(0).toImage().scaled(W, H)
    rows = []
    for y in range(H):
        line = []
        for x in range(W):
            c = img.pixelColor(x, y)
            v = int((c.red() + c.green() + c.blue()) / 3)
            line.append(v)
        rows.append(line)
    return rows


def dump(rows):
    # 0-255 映射到 0-9
    return ["".join(str(min(9, v // 26)) for v in row) for row in rows]


out = []
out.append("=== 唤出前（桌面）===")
out += dump(grid())

proc = subprocess.Popen([PYW, MAIN])
time.sleep(0.9)
out.append("")
out.append("=== 唤出后（面板显示中）===")
out += dump(grid())
time.sleep(0.4)
out.append("")
out.append("=== 0.4 秒后 ===")
out += dump(grid())

try:
    proc.wait(timeout=15)
except Exception:
    pass

with open(OUT + "/grid.log", "w", encoding="utf-8") as fh:
    fh.write("\n".join(out) + "\n")
