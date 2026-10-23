"""给打包好的 exe 截图：socket 唤出面板 -> 把面板拉回前台 -> 截屏。

为什么要拉前台：这个脚本本身是另一个进程，唤出瞬间抢一下焦点，面板会按
"失焦关闭"逻辑自己收起来，截到的就是壁纸。tools/shot_panel.py 是同一进程
所以没这个问题，但它只能测源码版。
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

from PyQt5.QtGui import QGuiApplication
from PyQt5.QtNetwork import QLocalSocket
from PyQt5.QtWidgets import QApplication

u = ctypes.WinDLL("user32", use_last_error=True)
u.SetForegroundWindow.argtypes = [wintypes.HWND]
u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]

OUT = sys.argv[1] if len(sys.argv) > 1 else "tools/frames/exe_panel.png"


def send(cmd: str) -> None:
    s = QLocalSocket()
    s.connectToServer("DeskDock.SingleInstance")
    if not s.waitForConnected(800):
        raise SystemExit("连不上 DeskDock 实例")
    s.write(cmd.encode())
    s.flush()
    s.waitForBytesWritten(600)
    s.disconnectFromServer()


def panel_rect() -> tuple[int, int, int, int]:
    """找最大的可见 Qt5* 窗口（面板），顺便把它拉到前台。"""
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    best = {"hwnd": 0, "area": 0, "rect": (0, 0, 0, 0)}

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
            best.update(hwnd=hwnd, area=area,
                        rect=(r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    u.EnumWindows(EnumProc(_cb), 0)
    if best["hwnd"]:
        u.SetForegroundWindow(best["hwnd"])
    return best["rect"]


def main() -> None:
    app = QApplication(sys.argv[:1])  # noqa: F841 需要 QApplication 才能抓屏
    send("show")
    time.sleep(0.35)
    x, y, w, h = panel_rect()
    time.sleep(0.9)
    x, y, w, h = panel_rect()  # 拉前台后几何可能已更新
    scr = QGuiApplication.primaryScreen()
    img = scr.grabWindow(0, x, y, w, h)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img.save(OUT)
    print(f"面板几何 x={x} y={y} w={w} h={h}")
    print(f"已截图 {OUT}（{os.path.getsize(OUT) // 1024} KB）")
    send("hide")


if __name__ == "__main__":
    main()
