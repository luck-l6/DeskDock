"""启动条目：应用、文件、文件夹、网址。

两个关键点，都是踩过坑的：

1. **必须异步**。`os.startfile` 底层是 ShellExecute，它会同步等待 Shell
   的 DDE 会话。实测一次能阻塞 4 秒以上（Defender 扫描、冷启动都算在
   这时间里）。在主线程调用，Qt 事件循环就会整个停摆——面板收起了，
   桌面上却什么都没发生，用户看到的就是"点了打不开"。
   所以启动一律丢到后台线程，UI 立即返回。

2. **.lnk 交给 Shell 自己解析**。以前是解析出 target/args 再用 Popen
   直接跑 exe，这会丢掉快捷方式里的「以管理员身份运行」「起始位置」
   等设置，UWP 应用的 shell:AppsFolder 目标也会失败。直接 startfile
   那个 .lnk，Shell 会按快捷方式原本的行为启动。

3. **必须回头看一眼进程活没活下来**。ShellExecute 返回 >32 只代表
   "Shell 接受了请求"，不代表程序真的起来了。实测有条目点了没反应，
   日志里却只有"启动调用已返回"——进程其实起来几秒就死了（Electron
   应用的 GPU 子进程起不来时会自杀）。所以启动后拿进程句柄等几秒，
   退出码不对就记下来并通知 UI，别再闷声不响。
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import threading
from ctypes import wintypes
from pathlib import Path

from .scanner import AppEntry

log = logging.getLogger(__name__)

# --- ShellExecuteEx ---
_SEE_MASK_NOCLOSEPROCESS = 0x00000040
_SW_SHOWNORMAL = 1
_STILL_ACTIVE = 259
_WAIT_TIMEOUT_MS = 4000
_WAIT_STEP_MS = 400


class _SHELLEXECUTEINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", ctypes.c_ulong),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hKeyClass", ctypes.c_void_p),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


def _pick_target(entry: AppEntry) -> str:
    """挑一个真正该交给 Shell 的路径。

    优先用磁盘上的原始条目（.lnk / 文件 / 文件夹本身），让 Shell 按它
    原本的含义打开；只有原始条目不存在时才退回快捷方式指向的 target。
    """
    # Shell 命名空间（此电脑、回收站）：磁盘上没有对应文件，
    # os.path.exists 必然 False，得跳过下面那层存在性筛选
    if entry.kind == "special":
        return entry.path or entry.target
    for candidate in (entry.path, entry.target):
        if candidate and os.path.exists(candidate):
            return candidate
    if entry.kind == "url":
        return entry.target or entry.path
    return ""


def _shell_execute(target: str):
    """用 ShellExecuteEx 启动，顺手把进程句柄要回来（用于事后验尸）。

    返回 (是否投递成功, 进程句柄)。句柄可能为 None：UWP / 协议类目标
    拿不到进程句柄，那种就没法校验，只能信 Shell。
    """
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_SHELLEXECUTEINFO)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL

    # 让接下来这个进程能把窗口带到最前面。Windows 的前台激活规则是：
    # 只有前台进程（或经它许可的进程）才能 SetForegroundWindow。
    # 点 Dock 时 Dock 故意不吃焦点，前台还是用户原来那个窗口，
    # 新应用即便起来了也可能被压在后面 —— 用户看到的就是"点了没反应"。
    # 提前放行一次，能弹到前面的几率就高得多；失败了也无妨。
    try:
        _asfw = ctypes.WinDLL("user32", use_last_error=True)
        _asfw.AllowSetForegroundWindow(ctypes.c_ulong(0xFFFFFFFF))
    except Exception:
        pass

    info = _SHELLEXECUTEINFO()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = _SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "open"
    info.lpFile = target
    info.nShow = _SW_SHOWNORMAL

    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        return False, None
    # <= 32 是错误码，且不会给出进程句柄
    if int(info.hInstApp or 0) <= 32:
        return False, None
    return True, (info.hProcess or None)


def _wait_exit_code(handle: int, timeout_ms: int = _WAIT_TIMEOUT_MS):
    """等进程退出，返回退出码；超时（还在跑）返回 None。"""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    waited = 0
    while waited < timeout_ms:
        code = wintypes.DWORD()
        if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return None
        if code.value != _STILL_ACTIVE:
            return code.value
        k32.WaitForSingleObject(handle, _WAIT_STEP_MS)
        waited += _WAIT_STEP_MS
    return None


def launch_sync(entry: AppEntry, on_fail=None) -> bool:
    """在**当前线程**里启动，会阻塞，成功返回 True。

    on_fail(entry, exit_code)：进程起来又很快退出时回调。调用方要自己
    负责切回主线程（这里是后台线程，不能直接碰 UI）。
    """
    target = _pick_target(entry)
    if not target:
        log.warning("目标不存在: %s (%r / %r)",
                    entry.name, entry.path, entry.target)
        return False

    handle = None
    try:
        # 后台线程里用 Shell API，先把这个线程初始化成 MTA，避免
        # 某些 Shell 扩展在无 COM 套间的线程上抛异常。
        try:
            ctypes.windll.ole32.CoInitializeEx(None, 0x0)
        except Exception:
            pass

        log.info("启动: %s", target)
        ok, handle = _shell_execute(target)
        log.info("启动调用已返回: %s (ok=%s)", target, ok)
        if not ok:
            log.warning("Shell 拒绝启动 %s（%s）", entry.name, target)
            return False
    except Exception as exc:
        log.warning("启动失败 %s: %s", entry.name, exc)
        return False

    try:
        if handle is None:
            # 拿不到句柄（UWP、协议等），没法验，就信 Shell 的判断
            return True
        code = _wait_exit_code(handle)
        if code is None:
            return True
        if code == 0:
            # 启动器型应用（xxxLauncher.exe）拉起主程序后自己就退了，
            # 退出码 0 是它的正常行为，只是主程序有没有起来这里看不到
            log.debug("启动器已退出: %s", entry.name)
            return True
        log.warning(
            "启动后很快退出: %s（%s）退出码=0x%X —— Shell 报的是成功，"
            "但进程没能活下来", entry.name, target, code & 0xFFFFFFFF)
        if on_fail is not None:
            try:
                on_fail(entry, code & 0xFFFFFFFF)
            except Exception as exc:
                log.debug("on_fail 回调异常: %s", exc)
        return False
    finally:
        if handle:
            ctypes.WinDLL("kernel32").CloseHandle(handle)


def launch(entry: AppEntry, on_fail=None) -> bool:
    """异步启动，立即返回。

    返回 True 表示"已投递"，不代表应用一定起来了——真正的成败在后台
    线程里判定并写日志。UI 不能为了一个可能卡 4 秒的调用停下来等。
    """
    threading.Thread(
        target=launch_sync,
        args=(entry,),
        kwargs={"on_fail": on_fail},
        name="DeskDock-launch",
        daemon=True,
    ).start()
    return True


def open_in_explorer(path: str) -> bool:
    """在资源管理器中定位到该条目（Popen 不阻塞，可以直接调）。"""
    try:
        p = Path(path)
        if p.is_dir():
            # 用 explorer 打开目录，而不是 startfile——后者同样会阻塞
            subprocess.Popen(  # noqa: S603
                ["explorer", str(p)], shell=False, close_fds=True
            )
        else:
            subprocess.Popen(  # noqa: S603
                ["explorer", "/select,", str(p)], shell=False, close_fds=True
            )
        return True
    except Exception as exc:
        log.warning("定位失败 %s: %s", path, exc)
        return False
