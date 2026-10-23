"""唤出面板 → 点某个分类 chip → 截图。用于肉眼验证过滤结果。"""

import ctypes
import sys
import time
from ctypes import wintypes

from PyQt5.QtGui import QGuiApplication
from PyQt5.QtNetwork import QLocalSocket

u = ctypes.windll.user32

x = int(sys.argv[1])
y = int(sys.argv[2])
out = sys.argv[3] if len(sys.argv) > 3 else "tools/frames/chip.png"

s = QLocalSocket()
s.connectToServer("DeskDock.SingleInstance")
s.waitForConnected(600)
s.write(b"show")
s.flush()
s.waitForBytesWritten(600)
s.disconnectFromServer()
time.sleep(1.3)

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
time.sleep(0.4)

u.SetCursorPos(x, y)
time.sleep(0.15)
u.mouse_event(0x0002, 0, 0, 0, 0)
time.sleep(0.06)
u.mouse_event(0x0004, 0, 0, 0, 0)
time.sleep(0.7)

app = QGuiApplication(sys.argv)
img = QGuiApplication.primaryScreen().grabWindow(0).toImage()
img.save(out, "PNG")
print("saved", out)
