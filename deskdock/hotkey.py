"""全局热键。

RegisterHotKey(hwnd=NULL) 会把 WM_HOTKEY 投递到**调用线程**的消息队列。
所以这里专门开一条后台线程：在那条线程里注册，也在那条线程里 GetMessage
收取，收到就通过 Qt 信号通知主线程。

早先走的是 Qt 的 QAbstractNativeEventFilter，但 PyQt5 传进来的 message 是
sip.voidptr，转地址时一旦抛异常就会被事件过滤器静默吞掉 —— 表现就是热键
怎么按都没反应、日志里还干干净净。专用线程不依赖 Qt 的原生事件分发，稳得多。
"""

from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes

from PyQt5.QtCore import QObject, pyqtSignal

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

HOTKEY_ID = 0xD5C0

user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                               wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]
user32.PostThreadMessageW.restype = wintypes.BOOL


def vk_from_name(name: str) -> int:
    n = name.strip().lower()
    special = {
        "space": 0x20, "enter": 0x0D, "return": 0x0D, "esc": 0x1B,
        "escape": 0x1B, "tab": 0x09, "backspace": 0x08, "delete": 0x2E,
        "insert": 0x2D, "home": 0x24, "end": 0x23, "pageup": 0x21,
        "pagedown": 0x22, "up": 0x26, "down": 0x28, "left": 0x25,
        "right": 0x27, "`": 0xC0, "grave": 0xC0,
    }
    if n in special:
        return special[n]
    if len(n) == 2 and n[0] == "f" and n[1:].isdigit():
        num = int(n[1:])
        if 1 <= num <= 24:
            return 0x6F + num
    if len(n) == 1:
        res = user32.VkKeyScanW(ctypes.c_wchar(n))
        if res != -1:
            return res & 0xFF
    return 0


def parse_hotkey(text: str) -> tuple[int, int]:
    """把 "Ctrl+Space" 解析成 (modifiers, vk)。解析失败返回 (0, 0)。"""
    mods = 0
    vk = 0
    for part in text.split("+"):
        p = part.strip().lower()
        if not p:
            continue
        if p in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif p in ("alt", "menu"):
            mods |= MOD_ALT
        elif p == "shift":
            mods |= MOD_SHIFT
        elif p in ("win", "meta", "super"):
            mods |= MOD_WIN
        else:
            vk = vk_from_name(p)
    return mods, vk


class _HotkeyThread(threading.Thread):
    """一条只用来收 WM_HOTKEY 的消息循环。"""

    def __init__(self, mods: int, vk: int, on_trigger) -> None:
        super().__init__(daemon=True)
        self._mods = mods
        self._vk = vk
        self._cb = on_trigger
        self._tid = 0
        self._ready = threading.Event()
        self._ok = False

    @property
    def ok(self) -> bool:
        return self._ok

    def wait_ready(self, timeout: float = 3.0) -> bool:
        self._ready.wait(timeout)
        return self._ok

    def stop(self) -> None:
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)

    def run(self) -> None:
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
        self._ok = bool(user32.RegisterHotKey(
            None, HOTKEY_ID, self._mods | MOD_NOREPEAT, self._vk))
        if not self._ok:
            log.warning("注册热键失败：组合可能已被其它程序占用 "
                        "(mods=0x%X vk=0x%X)", self._mods, self._vk)
        self._ready.set()
        if not self._ok:
            return

        msg = wintypes.MSG()
        while True:
            res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if res <= 0:            # 0 = WM_QUIT，-1 = 出错
                break
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                log.info("收到全局热键")
                self._cb()
        user32.UnregisterHotKey(None, HOTKEY_ID)
        log.info("热键线程已退出")


class HotkeyManager(QObject):
    triggered = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._registered = False
        self._thread: _HotkeyThread | None = None

    def register(self, combination: str) -> bool:
        self.unregister()
        if not combination:
            return False
        mods, vk = parse_hotkey(combination)
        if not vk:
            log.warning("热键无法识别: %s", combination)
            return False
        thread = _HotkeyThread(mods, vk, self._on_hotkey)
        thread.start()
        self._thread = thread
        ok = thread.wait_ready(3.0)
        self._registered = ok
        if ok:
            log.info("热键已注册: %s", combination)
        return ok

    def unregister(self) -> None:
        thread = self._thread
        self._thread = None
        self._registered = False
        if thread is None:
            return
        thread.stop()
        thread.join(timeout=2.0)

    @property
    def active(self) -> bool:
        return self._registered

    def _on_hotkey(self) -> None:
        # 从后台线程 emit：Qt 会自动排到主线程，信号槽那边照常执行
        self.triggered.emit()
