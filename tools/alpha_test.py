"""验证 Qt 透明窗口在本机是否真的透明。

做法：开一个 400x400 的透明无边框窗口，中间放一块红方块，
四角什么都不画。抓屏后看窗口左上角那一点：
  - 还是桌面原来的颜色 -> 透明生效
  - 纯黑 (0,0,0)        -> 透明失效，Qt 填了黑底
"""

import os
import sys
import time

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QGuiApplication, QColor
from PyQt5.QtQml import QQmlApplicationEngine
from PyQt5.QtWidgets import QApplication

QML = """
import QtQuick 2.15
import QtQuick.Window 2.15
Window {
    width: 400
    height: 400
    x: 700
    y: 300
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
    color: "transparent"
    visible: true
    Rectangle { anchors.centerIn: parent; width: 200; height: 200; color: "red" }
}
"""

here = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(here, "_alpha.qml")
with open(path, "w", encoding="utf-8") as f:
    f.write(QML)

app = QApplication(sys.argv)
scr = QGuiApplication.primaryScreen()
dpr = scr.devicePixelRatio() or 1.0

before = scr.grabWindow(0).toImage()

eng = QQmlApplicationEngine()
eng.load(QUrl.fromLocalFile(path))
win = eng.rootObjects()[0]

import ctypes
try:
    hwnd = int(win.winId())
    dwm = ctypes.WinDLL("dwmapi")
    val = ctypes.c_int(1)  # DWMSBT_NONE
    dwm.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(val), ctypes.sizeof(val))
except Exception as e:
    print("dwm:", e)

win.requestActivate()
for _ in range(60):
    app.processEvents()
    time.sleep(0.02)
time.sleep(0.8)
app.processEvents()

after = scr.grabWindow(0).toImage()

# 窗口左上角内部的点（红方块之外），以及正中间的红色方块
pts = {
    "角内(705,305)": (705, 305),
    "角内(710,310)": (710, 310),
    "边内(900,305)": (900, 305),
    "中心红块(900,500)": (900, 500),
}
for name, (x, y) in pts.items():
    px = int(x * dpr)
    py = int(y * dpr)
    b = QColor(before.pixel(px, py))
    a = QColor(after.pixel(px, py))
    print("%-18s 前=(%3d,%3d,%3d)  后=(%3d,%3d,%3d)  %s"
          % (name, b.red(), b.green(), b.blue(),
             a.red(), a.green(), a.blue(),
             "透明生效" if not (a.red() == 0 and a.green() == 0 and a.blue() == 0)
             else "纯黑=不透明"))

try:
    os.remove(path)
except OSError:
    pass
