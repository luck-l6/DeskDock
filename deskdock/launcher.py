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
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import threading
from pathlib import Path

from .scanner import AppEntry

log = logging.getLogger(__name__)


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


def launch_sync(entry: AppEntry) -> bool:
    """在**当前线程**里启动，会阻塞，成功返回 True。"""
    target = _pick_target(entry)
    if not target:
        log.warning("目标不存在: %s (%r / %r)",
                    entry.name, entry.path, entry.target)
        return False

    try:
        # 后台线程里用 Shell API，先把这个线程初始化成 MTA，避免
        # 某些 Shell 扩展在无 COM 套间的线程上抛异常。
        try:
            ctypes.windll.ole32.CoInitializeEx(None, 0x0)
        except Exception:
            pass

        log.info("启动: %s", target)
        os.startfile(target)  # noqa: S606
        log.info("启动调用已返回: %s", target)
        return True
    except Exception as exc:
        log.warning("启动失败 %s: %s", entry.name, exc)
        return False


def launch(entry: AppEntry) -> bool:
    """异步启动，立即返回。

    返回 True 表示"已投递"，不代表应用一定起来了——真正的成败在后台
    线程里判定并写日志。UI 不能为了一个可能卡 4 秒的调用停下来等。
    """
    threading.Thread(
        target=launch_sync,
        args=(entry,),
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
