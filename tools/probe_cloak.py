"""检查面板窗口是否被 DWM cloak（被 cloak 的窗口 Win32 可见但不参与合成）。"""

import ctypes
import sys
import time
from ctypes import wintypes

from PyQt5.QtCore import QCoreApplication
from PyQt5.QtNetwork import QLocalSocket

app = QCoreApplication(sys.argv)
user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi


def send(cmd: bytes) -> None:
    s = QLocalSocket()
    s.connectToServer("DeskDock.SingleInstance")
    if s.waitForConnected(300):
        s.write(cmd)
        s.flush()
        s.waitForBytesWritten(300)
        s.disconnectFromServer()


send(b"show")
time.sleep(2.2)

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
found = []


def cb(hwnd, _):
    if not user32.IsWindowVisible(hwnd):
        return True
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    if rect.right - rect.left < 2000:
        return True
    cloaked = ctypes.c_int(0)
    # DWMWA_CLOAKED = 14
    hr = dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), 4)
    # DWMWA_HAS_ICONIC_BITMAP = 10 / 也顺便看扩展样式
    ex = user32.GetWindowLongW(hwnd, -20)
    found.append("hwnd=%d cloaked=%d(hr=0x%08X) ex=0x%08X"
                 % (hwnd, cloaked.value, hr & 0xFFFFFFFF, ex))
    return True


user32.EnumWindows(EnumWindowsProc(cb), 0)
print("全屏窗口 DWM 状态:")
for f in found:
    print(" ", f)
send(b"hide")
