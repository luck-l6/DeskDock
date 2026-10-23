"""唤出面板并截图（同一进程内完成，避免进程退出抢焦点把面板关掉）。"""

import ctypes
import sys
import time
from ctypes import wintypes

from PyQt5.QtGui import QGuiApplication
from PyQt5.QtNetwork import QLocalSocket

u = ctypes.windll.user32

s = QLocalSocket()
s.connectToServer("DeskDock.SingleInstance")
if not s.waitForConnected(600):
    print("连不上 DeskDock（没在运行？）")
    sys.exit(1)
s.write(b"show")
s.flush()
s.waitForBytesWritten(600)
s.disconnectFromServer()

time.sleep(1.3)

# 找到面板窗口（最大那个 Qt 窗口），提到前台
EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
best = {"hwnd": 0, "area": 0}


def _cb(hwnd, _lp):
    if not u.IsWindowVisible(hwnd):
        return True
    cls = ctypes.create_unicode_buffer(64)
    u.GetClassNameW(hwnd, cls, 64)
    if not cls.value.startswith("Qt5"):
        return True
    r = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    area = (r.right - r.left) * (r.bottom - r.top)
    if area > best["area"]:
        best.update(hwnd=hwnd, area=area)
    return True


u.EnumWindows(EnumProc(_cb), 0)
if best["hwnd"]:
    u.SetForegroundWindow(best["hwnd"])
time.sleep(0.45)

app = QGuiApplication(sys.argv)
img = QGuiApplication.primaryScreen().grabWindow(0).toImage()
out = sys.argv[1] if len(sys.argv) > 1 else "tools/frames/panel.png"
img.save(out, "PNG")
print("saved", out, img.width(), img.height(), "hwnd", best["hwnd"])
