"""模拟按下全局热键，看 DeskDock 是否真的收到。

用法: python tools/hotkey_test.py [组合, 默认 Ctrl+Alt+A]
"""

import ctypes
import sys
import time

from PyQt5.QtNetwork import QLocalSocket

VK = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B}
user32 = ctypes.WinDLL("user32", use_last_error=True)


def vk_of(token: str) -> int:
    t = token.strip().lower()
    if t in VK:
        return VK[t]
    if len(t) == 1:
        return ord(t.upper())
    raise ValueError("不认识的按键: " + token)


def press(tokens) -> None:
    keys = [vk_of(t) for t in tokens]
    for k in keys:
        user32.keybd_event(k, 0, 0, 0)          # down
    time.sleep(0.06)
    for k in reversed(keys):
        user32.keybd_event(k, 0, 2, 0)          # up


def send(cmd: bytes) -> None:
    s = QLocalSocket()
    s.connectToServer("DeskDock.SingleInstance")
    if s.waitForConnected(500):
        s.write(cmd)
        s.flush()
        s.waitForBytesWritten(500)
        s.disconnectFromServer()


combo = (sys.argv[1] if len(sys.argv) > 1 else "Ctrl+Alt+A").split("+")

print("先收起面板…")
send(b"hide")
time.sleep(1.0)

print("模拟按下:", "+".join(combo))
press(combo)
time.sleep(1.2)

print("再按一次（应收回）…")
press(combo)
time.sleep(1.0)
print("完成，去看 %LOCALAPPDATA%\\DeskDock\\deskdock.log 里有没有『收到全局热键』")
