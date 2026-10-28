"""把"已经在跑、但看不见"的应用叫回前台。

为什么需要这个（2026-10-27 实测）
--------------------------------
WorkBuddy / 豆包 / Obsidian 这类 Electron 应用都是**单实例**的：第二次
启动时新进程只是把命令行丢给旧实例、自己立刻退出（退出码 0）。窗口弹不
弹回来完全看旧实例自己的脸色 —— 实测它们的窗口停在**最小化**或
**完全隐藏**的状态，ShellExecute 却报成功，用户看到的就是"点了打不开"。

所以启动前先看一眼：目标 exe 是不是已经在跑、窗口是不是缩起来了。
是的话直接 ShowWindow + SetForegroundWindow 把它叫回来，别再走一遍
"启动新进程"的弯路。

只有**窗口确实看不见**时才接管：窗口好端端显示在别处时仍走正常启动，
免得多开型应用（记事本、终端）点一次只能唤旧窗口、开不出新的。
"""

from __future__ import annotations

import ctypes
import logging
import os
from ctypes import wintypes

log = logging.getLogger(__name__)

_u32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

# --- 常量 ---
_TH32CS_SNAPPROCESS = 0x00000002
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080
_SW_RESTORE = 9
_SW_SHOW = 5
_ASFW_ANY = 0xFFFFFFFF

_u32.GetForegroundWindow.restype = wintypes.HWND
_u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_u32.GetWindowThreadProcessId.restype = wintypes.DWORD
_u32.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_u32.EnumWindows.restype = wintypes.BOOL
_u32.IsWindowVisible.argtypes = [wintypes.HWND]
_u32.IsIconic.argtypes = [wintypes.HWND]
_u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_u32.ShowWindow.restype = wintypes.BOOL
_u32.SetForegroundWindow.argtypes = [wintypes.HWND]
_u32.SetForegroundWindow.restype = wintypes.BOOL
_u32.BringWindowToTop.argtypes = [wintypes.HWND]
_u32.BringWindowToTop.restype = wintypes.BOOL
_u32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
_u32.AllowSetForegroundWindow.restype = wintypes.BOOL
_u32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
_u32.AttachThreadInput.restype = wintypes.BOOL
_u32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_u32.GetWindowTextW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
_u32.GetClassNameW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
_u32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_u32.GetWindowLongPtrW.restype = ctypes.c_longlong
_k32.GetCurrentThreadId.restype = wintypes.DWORD
_k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
_k32.Process32FirstW.restype = wintypes.BOOL
_k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
_k32.Process32NextW.restype = wintypes.BOOL

# 这些类名是应用的"杂物间"窗口，不是用户看到的主窗口：
# IME/输入法、Electron 的托盘与通知宿主、crashpad 的哨兵、Qt 的托盘消息窗。
_SKIP_CLASS_EXACT = {
    "IME", "Default IME", "MSCTFIME UI", "WorkerW",
    "Base_PowerMessageWindow", "Qt5152TrayIconMessageWindowClass",
    "QTrayIconMessageWindow",
}
_SKIP_CLASS_PREFIX = ("crashpad_", "Electron_Notify", "Electron_System", "MSCTF")


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_ulonglong),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def _candidate_exe_names(entry) -> list[str]:
    """候选 exe 文件名（小写）。

    快捷方式的目标不一定就是真身（Obsidian 的 target 是 update.exe，
    真身才叫 Obsidian.exe），所以 target 和快捷方式名各推一个候选，
    谁先在进程表里命中算谁。
    """
    names: list[str] = []
    for raw in (entry.target, entry.path):
        if not raw:
            continue
        s = str(raw).strip().strip('"')
        low = s.lower()
        if low.startswith("shell:") or "://" in low:
            continue
        stem = os.path.splitext(os.path.basename(s))[0].strip().lower()
        if not stem:
            continue
        name = stem + ".exe"
        if name not in names:
            names.append(name)
    return names


def _pids_by_exe(names: list[str]) -> list[int]:
    if not names:
        return []
    want = set(names)
    snap = _k32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snap in (None, 0, _INVALID_HANDLE_VALUE):
        return []
    pids: list[int] = []
    try:
        pe = _PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(pe)
        ok = _k32.Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            if pe.szExeFile.lower() in want:
                pids.append(pe.th32ProcessID)
            ok = _k32.Process32NextW(snap, ctypes.byref(pe))
    finally:
        _k32.CloseHandle(snap)
    return pids


def _class_of(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _u32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _title_of(hwnd) -> str:
    n = _u32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    _u32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _is_main_window(hwnd) -> bool:
    """顶层窗口里挑"用户真正看到的那一个"。"""
    cls = _class_of(hwnd)
    if cls in _SKIP_CLASS_EXACT or cls.startswith(_SKIP_CLASS_PREFIX):
        return False
    if not _title_of(hwnd):
        # Electron 那批隐藏的 Chrome_WidgetWin_0 全是空标题
        return False
    try:
        ex = int(_u32.GetWindowLongPtrW(hwnd, _GWL_EXSTYLE))
    except Exception:
        return False
    if ex & _WS_EX_TOOLWINDOW:
        return False
    return True


def find_main_window(entry, pids=None):
    """找出该条目对应的主窗口句柄，找不到返回 None。"""
    if pids is None:
        pids = _pids_by_exe(_candidate_exe_names(entry))
    if not pids:
        return None
    pidset = set(pids)
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, ctypes.c_void_p)
    def _cb(hwnd, _lparam):
        pid = wintypes.DWORD()
        _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pidset and _is_main_window(hwnd):
            found.append(hwnd)
        return True

    _u32.EnumWindows(_cb, 0)
    # EnumWindows 按 Z 序给，第一个就是最靠上的那个
    return found[0] if found else None


def is_visible(hwnd) -> bool:
    """窗口是不是"看得见"——可见且没缩成图标。"""
    return bool(_u32.IsWindowVisible(hwnd)) and not bool(_u32.IsIconic(hwnd))


def activate_window(hwnd) -> bool:
    """把窗口叫到前台。成功返回 True。

    前台激活受 Windows 的焦点规则管着：不是前台进程、又没人放行的话
    SetForegroundWindow 会被默默拒绝。所以先 AllowSetForegroundWindow，
    再按"最小化→恢复 / 隐藏→显示"的顺序摆好，最后置前；还不行就
    AttachThreadInput 绑住目标线程强推一次。
    """
    try:
        _u32.AllowSetForegroundWindow(_ASFW_ANY)
        if _u32.IsIconic(hwnd):
            _u32.ShowWindow(hwnd, _SW_RESTORE)
        elif not _u32.IsWindowVisible(hwnd):
            _u32.ShowWindow(hwnd, _SW_SHOW)
        _u32.SetForegroundWindow(hwnd)
        if _u32.GetForegroundWindow() == hwnd:
            return True

        # 兜底：把输入队列绑到目标窗口所在线程，再推一次
        tid = _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(wintypes.DWORD()))
        cur = _k32.GetCurrentThreadId()
        if tid and tid != cur and _u32.AttachThreadInput(cur, tid, True):
            try:
                _u32.BringWindowToTop(hwnd)
                _u32.SetForegroundWindow(hwnd)
            finally:
                _u32.AttachThreadInput(cur, tid, False)
        return _u32.GetForegroundWindow() == hwnd
    except Exception as exc:
        log.debug("激活窗口失败: %s", exc)
        return False


def activate_if_hidden(entry) -> bool:
    """已经在跑、但窗口缩起来了 → 直接唤回来。

    返回 True 表示"已经处理好了，别再启动新进程"。
    """
    hwnd = find_main_window(entry)
    if not hwnd or is_visible(hwnd):
        return False
    if activate_window(hwnd):
        log.info("已在运行，直接唤起窗口: %s", entry.name)
        return True
    return False


def activate_after_launch(entry, timeout_ms: int = 2000,
                          step_ms: int = 100) -> bool:
    """刚启动完补一次：新窗口可能被别的窗口压在后面。

    进程建窗口要时间，所以轮询着等；一找到就置前。
    """
    import time

    waited = 0
    while waited <= timeout_ms:
        hwnd = find_main_window(entry)
        if hwnd:
            if activate_window(hwnd):
                log.debug("启动后已置前: %s", entry.name)
                return True
            return False
        time.sleep(step_ms / 1000.0)
        waited += step_ms
    return False
