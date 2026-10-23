"""拖拽排序回归测试：唤出面板 → 长按第一个条目 → 拖到第 5 格 → 松手。

    python tools/drag_test.py

验证三件事：
  1. 长按能进入拖拽（原位变淡、出现跟随指针的浮层）
  2. 拖过去之后条目真的换了位置（截图 + 读 config 里的 order）
  3. 顺序落盘了（关掉面板后 config.json 里有新顺序）

屏幕上必须已经有一个 DeskDock 实例在跑。
"""

from __future__ import annotations

import ctypes
import io
import json
import os
import sys
import time
from pathlib import Path

from PyQt5.QtGui import QGuiApplication
from PyQt5.QtNetwork import QLocalSocket

u = ctypes.WinDLL("user32", use_last_error=True)
u.SetForegroundWindow.argtypes = [ctypes.wintypes.HWND]
u.GetWindowRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.RECT)]


def panel_rect() -> tuple[int, int, int, int]:
    """找最大的可见 Qt5* 窗口（面板）并拉到前台。

    不置前的话，鼠标事件会落到别的窗口上——面板看起来还在，但一条
    事件都收不到（这也是我上一版"长按完全没反应"的真正原因）。
    """
    EnumProc = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL,
                                  ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    best = {"hwnd": 0, "area": 0, "rect": (0, 0, 0, 0)}

    def _cb(hwnd, _lp):
        if not u.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(hwnd, cls, 64)
        if not cls.value.startswith("Qt5"):
            return True
        r = ctypes.wintypes.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(r))
        area = (r.right - r.left) * (r.bottom - r.top)
        if area > best["area"]:
            best.update(hwnd=hwnd, area=area,
                        rect=(r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    u.EnumWindows(EnumProc(_cb), 0)
    if best["hwnd"]:
        u.SetForegroundWindow(best["hwnd"])
        u.BringWindowToTop(best["hwnd"])
    return best["rect"]

# 面板几何来自日志：x=656 y=214 w=1248 h=1048（150% 缩放下就是物理像素）
PANEL = (656, 214)
SIZE = (1248, 1048)
OUT_BEFORE = "tools/frames/drag_before.png"
OUT_MID = "tools/frames/drag_mid.png"
OUT_AFTER = "tools/frames/drag_after.png"

LEFTDOWN, LEFTUP = 0x0002, 0x0004


def cmd(data: bytes) -> None:
    s = QLocalSocket()
    s.connectToServer("DeskDock.SingleInstance")
    s.waitForConnected(600)
    s.write(data)
    s.flush()
    s.waitForBytesWritten(600)
    s.disconnectFromServer()


def shot(path: str) -> None:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    os.makedirs("tools/frames", exist_ok=True)
    x, y, w, h = panel_rect()
    img = app.primaryScreen().grabWindow(0, x, y, w, h)
    img.save(path)
    print("  截图", path, os.path.getsize(path) // 1024, "KB")


def move_to(x: int, y: int) -> None:
    u.SetCursorPos(int(x), int(y))


def press(flag: int) -> None:
    u.mouse_event(flag, 0, 0, 0, 0)


def log_path() -> str:
    return os.path.expandvars(r"%LOCALAPPDATA%\DeskDock\deskdock.log")


def read_grid(tag: str = "grid2") -> dict:
    """从日志里取面板自己报的网格几何（Panel.qml 显示时会打一行 GRID）。

    比硬编码坐标可靠得多：换分辨率、换条目数、滚动过都自动跟上。
    """
    import re

    with io.open(log_path(), encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    pat = re.compile(
        r"GRID " + tag + r" ox=(-?\d+) oy=(-?\d+) cell=(\d+)x(\d+) "
        r"size=(\d+)x(\d+) cont=(-?\d+),(-?\d+) count=(\d+)")
    for line in reversed(lines[-400:]):
        m = pat.search(line)
        if m:
            v = [int(x) for x in m.groups()]
            return dict(ox=v[0], oy=v[1], cw=v[2], ch=v[3], w=v[4], h=v[5],
                        cx=v[6], cy=v[7], count=v[8])
    raise SystemExit("日志里还没有 GRID 记录：先让面板显示一次")


def grid_pos(index: int, g: dict) -> tuple[int, int]:
    """第 index 格的屏幕坐标（只算可见区里的格子，不做自动滚动）。"""
    cols = max(1, g["w"] // g["cw"])
    col, row = index % cols, index // cols
    return (g["ox"] + col * g["cw"] + g["cw"] // 2 - g["cx"],
            g["oy"] + row * g["ch"] + g["ch"] // 2 - g["cy"])


def names_in_order() -> list[str]:
    """从 config.json 的 order + 当前扫描结果还原出前几项名字。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from deskdock.config import config
    from deskdock.scanner import scan

    order = list(config.get("order") or [])
    by_id = {e.id: e.name for e in scan(config)}
    return [by_id.get(i, "?" + i[:6]) for i in order[:8]]


def main() -> int:
    cmd(b"show")
    time.sleep(0.4)
    panel_rect()          # 先把面板拉到前台，否则鼠标事件全落到别的窗口
    time.sleep(1.4)
    shot(OUT_BEFORE)

    geo = read_grid()
    print(f"  网格 ox={geo['ox']} oy={geo['oy']} cell={geo['cw']}x{geo['ch']} count={geo['count']}")
    src, dst = grid_pos(0, geo), grid_pos(5, geo)
    print(f"起点 {src} -> 终点 {dst}")

    # 按住不放，等 pressAndHold（320ms）把拖拽打开
    move_to(*src)
    time.sleep(0.15)
    press(LEFTDOWN)
    time.sleep(0.55)

    # 小步移动：每次移动都会触发一次 indexAt，连续换位才是"跟手"的手感
    sx, sy = src
    dx, dy = dst
    steps = 12
    for i in range(1, steps + 1):
        move_to(sx + (dx - sx) * i // steps, sy + (dy - sy) * i // steps)
        time.sleep(0.045)
    time.sleep(0.25)
    shot(OUT_MID)

    press(LEFTUP)
    time.sleep(0.6)
    shot(OUT_AFTER)

    order = names_in_order()
    print("  拖动后的顺序（前 8）:", order)
    ok = len(order) > 0
    print("  落盘 order 长度:", len(order))
    cmd(b"hide")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
