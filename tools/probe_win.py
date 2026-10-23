"""触发面板显示，截图 + 枚举全部 Qt 顶层窗口，看面板是否真的上了屏。

用法: python tools/probe_win.py
"""

import ctypes
import sys
import time
from ctypes import wintypes

from PyQt5.QtCore import QCoreApplication
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtNetwork import QLocalSocket

user32 = ctypes.windll.user32

app = QGuiApplication(sys.argv)


def send(cmd: bytes) -> None:
    s = QLocalSocket()
    s.connectToServer("DeskDock.SingleInstance")
    if s.waitForConnected(300):
        s.write(cmd)
        s.flush()
        s.waitForBytesWritten(300)
        s.disconnectFromServer()


send(b"show")
time.sleep(1.2)

# 截屏
img = QGuiApplication.primaryScreen().grabWindow(0).toImage()
img.save("tools/frames/probe.png", "PNG")

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
hits = []


def cb(hwnd, _):
    if not user32.IsWindowVisible(hwnd):
        return True
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    if not cls.value.startswith("Qt"):
        return True
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    ex = user32.GetWindowLongW(hwnd, -20)
    st = user32.GetWindowLongW(hwnd, -16)
    hits.append("hwnd=%d cls=%s rect=(%d,%d)-(%d,%d) style=0x%08X ex=0x%08X"
                % (hwnd, cls.value, rect.left, rect.top, rect.right,
                   rect.bottom, st, ex))
    return True


user32.EnumWindows(EnumWindowsProc(cb), 0)
print("Qt 可见顶层窗口（唤出后 1.2s）:")
for h in hits:
    print(" ", h)
print("截图 -> tools/frames/probe.png")

send(b"hide")
