"""验证「桌面图标一定能还回来」这条生命线。

隐藏桌面图标是写进注册表的（HideIcons=1），进程一旦崩溃或被强杀，
没有任何代码会去把它改回来。设计上有三层兜底：
  1. 崩溃钩子（SetUnhandledExceptionFilter）——真崩溃时当场恢复
  2. RunOnce 兜底  ——下次登录由它恢复
  3. 下次启动自检  ——发现上次没正常退出，先恢复一次

本脚本实测 2 和 3。1 只对真正的未处理异常有效，taskkill /F 不会触发它。

测完一定把桌面图标恢复成可见。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import winreg

ADVANCED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
RUNONCE = r"Software\Microsoft\Windows\CurrentVersion\RunOnce"

EXE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "dist", "DeskDock.exe")
LOG = os.path.join(os.environ.get("LOCALAPPDATA", ""), "DeskDock",
                   "deskdock.log")


def dword(key_path: str, name: str):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            v, t = winreg.QueryValueEx(k, name)
            return v
    except FileNotFoundError:
        return None
    except OSError:
        return None


def runonce_values() -> dict:
    out = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUNONCE) as k:
            i = 0
            while True:
                try:
                    n, v, _ = winreg.EnumValue(k, i)
                    out[n] = v
                    i += 1
                except OSError:
                    break
    except OSError:
        pass
    return out


def desktop_icons_visible() -> bool:
    """HideIcons=1 表示隐藏。"""
    return dword(ADVANCED, "HideIcons") in (0, None)


def logsize() -> int:
    try:
        return os.path.getsize(LOG)
    except OSError:
        return 0


def wait_log(offset: int, needle: str, timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with open(LOG, "rb") as f:
                f.seek(offset)
                chunk = f.read().decode("utf-8", "replace")
        except OSError:
            chunk = ""
        if needle in chunk:
            return True
        time.sleep(0.1)
    return False


def kill() -> None:
    subprocess.run(["taskkill", "/F", "/IM", "DeskDock.exe"],
                   capture_output=True)
    time.sleep(1.0)


def main() -> int:
    print("=" * 62)
    print("桌面图标恢复 —— 崩溃/强杀场景实测")
    print("=" * 62)

    subprocess.run(["taskkill", "/F", "/IM", "DeskDock.exe"],
                   capture_output=True)
    time.sleep(0.5)

    print(f"\n起始状态：桌面图标可见 = {desktop_icons_visible()}")
    print(f"           RunOnce = {runonce_values()}")

    # ---- 第 1 步：正常启动，让它把图标藏起来 ----
    off = logsize()
    print("\n[1] 启动 DeskDock（正常路径）…")
    subprocess.Popen([EXE], creationflags=0x00000008)
    if not wait_log(off, "目录监听", 40):
        print("    !! 启动超时")
        return 1
    time.sleep(1.0)
    hidden_ok = not desktop_icons_visible()
    ro = runonce_values()
    print(f"    桌面已隐藏 = {hidden_ok}")
    print(f"    RunOnce 兜底已埋 = {bool(ro)}")
    for k, v in ro.items():
        print(f"      {k} = {v[:110]}")

    # ---- 第 2 步：强杀，模拟崩溃 ----
    print("\n[2] taskkill /F 强杀（模拟崩溃）…")
    kill()
    still_hidden = not desktop_icons_visible()
    print(f"    强杀后图标仍隐藏 = {still_hidden}   "
          f"（预期 True：进程死了没法自救）")
    if still_hidden:
        print("    -> 此刻到下次恢复之间，桌面图标是消失的")
        print("    -> 用户可见的自救手段：重启 DeskDock，或下次登录由 RunOnce 兜底")

    # ---- 第 3 步：重新启动，看自检有没有把图标还回来 ----
    print("\n[3] 再次启动 DeskDock（走自检恢复路径）…")
    off = logsize()
    subprocess.Popen([EXE], creationflags=0x00000008)
    recovered = wait_log(off, "检测到上次非正常退出", 40)
    time.sleep(2.0)
    print(f"    日志出现「上次非正常退出」 = {recovered}")
    # 这里图标**还是隐藏的**，属预期：隐藏是靠给 DefView 发 toggle 命令实现的，
    # 程序启动时会先把状态归位到「显示」再 toggle 回「隐藏」，保证方向不会反。
    # DeskDock 既然又在运行，图标本就该是隐藏的。
    print(f"    图标状态 = {'可见' if desktop_icons_visible() else '隐藏'}"
          f"（DeskDock 在运行，隐藏才对）")

    # ---- 第 4 步：正常退出 ----
    print("\n[4] 发 quit 正常退出…")
    from PyQt5.QtCore import QCoreApplication  # noqa: E402
    from PyQt5.QtNetwork import QLocalSocket  # noqa: E402

    app = QCoreApplication(sys.argv)
    s = QLocalSocket()
    s.connectToServer("DeskDock.SingleInstance")
    if s.waitForConnected(3000):
        s.write(b"quit")
        s.flush()
        s.waitForBytesWritten(1000)
    time.sleep(2.5)
    kill()
    print(f"    退出后桌面图标可见 = {desktop_icons_visible()}")

    print("\n" + "=" * 62)
    vis = desktop_icons_visible()
    print("结论：", "桌面图标已恢复可见 ✓" if vis else
          "!! 桌面图标仍处于隐藏状态，需要手动恢复")
    return 0 if vis else 1


if __name__ == "__main__":
    sys.exit(main())
