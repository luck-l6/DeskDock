"""右键菜单回归测试：唤出面板 → 右键点条目 → 截图 → 点投影区 → 再截图。

    python tools/context_menu_test.py [条目x 条目y]   # 物理坐标

屏幕上必须已经有一个 DeskDock 实例在跑（脚本通过 socket 让它显示面板）。
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

from PyQt5.QtGui import QGuiApplication
from PyQt5.QtNetwork import QLocalSocket

u = ctypes.windll.user32

# 面板逻辑几何见日志（x=656 y=214 w=1248 h=1048），150% 缩放 → ×1.5
EX, EY = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (1184, 620)
# 日志里的 panel 几何就是物理像素：x=656 y=214 w=1248 h=1048
PANEL = (656, 214)
PAD = 18  # CARD_PAD=34 逻辑 ≈ 51 物理，取 18 稳稳落在投影区里
OUT1 = "tools/frames/menu_open.png"
OUT2 = "tools/frames/menu_closed.png"
OUT3 = "tools/frames/menu_desktop.png"

RIGHTDOWN, RIGHTUP = 0x0008, 0x0010
LEFTDOWN, LEFTUP = 0x0002, 0x0004


def cmd(data: bytes) -> None:
    s = QLocalSocket()
    s.connectToServer("DeskDock.SingleInstance")
    s.waitForConnected(600)
    s.write(data)
    s.flush()
    s.waitForBytesWritten(600)
    s.disconnectFromServer()


def focus_panel() -> None:
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


def click(x: int, y: int, down: int, up: int) -> None:
    u.SetCursorPos(x, y)
    time.sleep(0.15)
    u.mouse_event(down, 0, 0, 0, 0)
    time.sleep(0.06)
    u.mouse_event(up, 0, 0, 0, 0)


def shot(path: str) -> None:
    img = QGuiApplication.primaryScreen().grabWindow(0).toImage()
    img.save(path, "PNG")
    print("saved", path)


app = QGuiApplication(sys.argv)

cmd(b"show")
time.sleep(1.3)
focus_panel()
time.sleep(0.4)

click(EX, EY, RIGHTDOWN, RIGHTUP)   # 右键点条目 → 菜单弹出
time.sleep(0.9)
shot(OUT1)

# 点投影区：面板应当收起，菜单必须一起消失
click(PANEL[0] + PAD, PANEL[1] + PAD, LEFTDOWN, LEFTUP)
time.sleep(0.9)
shot(OUT2)

# 场景二：右键之后直接点桌面（面板外的远处），看面板和菜单是不是一起收
cmd(b"show")
time.sleep(1.3)
focus_panel()
time.sleep(0.3)
click(EX, EY, RIGHTDOWN, RIGHTUP)
time.sleep(0.9)
click(2400, 1500, LEFTDOWN, LEFTUP)
time.sleep(0.9)
shot(OUT3)
