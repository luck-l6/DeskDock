"""DeskDock 端到端健康度实测。

启动真实 exe（不是自检模式），测：
  1. 冷启动到可交互的耗时
  2. 面板唤出延迟（发 show 命令 -> QML 网格完成布局打点）
  3. 常驻内存 / 句柄
  4. 正常退出有没有把桌面图标还回去

测完会走正规 quit 路径，桌面图标自动恢复。
用法：python tools/assess.py
"""

from __future__ import annotations

import datetime
import os
import subprocess
import sys
import time

from PyQt5.QtCore import QCoreApplication, QTimer  # noqa: E402
from PyQt5.QtNetwork import QLocalSocket  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 默认测单文件版；传参可测目录版：python tools/assess.py dist/DeskDock/DeskDock.exe
EXE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    ROOT, "dist", "DeskDock.exe")
LOG = os.path.join(os.environ.get("LOCALAPPDATA", ""), "DeskDock",
                   "deskdock.log")
SERVER = "DeskDock.SingleInstance"

_state: dict = {}


def tail(offset: int) -> tuple[str, int]:
    """读日志新增部分，返回 (新内容, 新 offset)。"""
    try:
        with open(LOG, "rb") as f:
            f.seek(offset)
            data = f.read()
            return data.decode("utf-8", "replace"), offset + len(data)
    except FileNotFoundError:
        return "", offset


def log_ts(line: str) -> float | None:
    """从日志行取时间戳（"2026-10-23 20:57:19,721"）。"""
    try:
        d, tm = line.split(" ")[0], line.split(" ")[1]
        y, mo, dd = [int(x) for x in d.split("-")]
        hms, ms = tm.split(",")
        h, m, s = [int(x) for x in hms.split(":")]
        return datetime.datetime(y, mo, dd, h, m, s,
                                 int(ms) * 1000).timestamp()
    except Exception:
        return None


def send(cmd: bytes) -> bool:
    s = QLocalSocket()
    s.connectToServer(SERVER)
    if not s.waitForConnected(1500):
        print("  !! 连不上单实例服务（程序没起来？）")
        return False
    s.write(cmd)
    s.flush()
    s.waitForBytesWritten(1000)
    s.disconnectFromServer()
    return True


def mem_kb() -> dict:
    """用 PowerShell 拿真实内存：工作集 + 私有提交。"""
    ps = ("Get-Process DeskDock -ErrorAction SilentlyContinue | "
          "Select-Object -First 1 WorkingSet64,PrivateMemorySize64,"
          "HandleCount | ConvertTo-Json")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stdout.strip()
    if not out:
        return {}
    try:
        import json
        d = json.loads(out)
        if isinstance(d, list):
            d = d[0]
        return {
            "ws": d.get("WorkingSet64", 0) // 1024,
            "priv": d.get("PrivateMemorySize64", 0) // 1024,
            "handles": d.get("HandleCount", 0),
        }
    except Exception:
        return {}


def wait_for(offset: int, needle: str, timeout_ms: int) -> tuple[float | None, int]:
    """轮询日志等某个关键字出现，返回它出现时的 epoch 时间。"""
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        chunk, offset = tail(offset)
        for line in chunk.splitlines():
            if needle in line:
                ts = log_ts(line)
                if ts:
                    return ts, offset
        time.sleep(0.02)
    return None, offset


def main() -> int:
    if not os.path.exists(EXE):
        print("找不到 exe：", EXE)
        return 1

    # 先把可能残留的实例清掉
    subprocess.run(["taskkill", "/F", "/IM", "DeskDock.exe"],
                   capture_output=True)
    time.sleep(0.6)

    offset = os.path.getsize(LOG) if os.path.exists(LOG) else 0

    print("=" * 60)
    print("DeskDock 健康度实测")
    print("=" * 60)

    t_launch = time.time()
    subprocess.Popen([EXE], cwd=os.path.dirname(EXE),
                     creationflags=0x00000008)  # DETACHED_PROCESS

    app = QCoreApplication(sys.argv)

    # 1) 启动耗时：拆成「onefile 自解压」和「程序自己初始化」两段
    ts_first, offset = wait_for(offset, "---- DeskDock 启动", 30000)
    if ts_first is not None:
        print(f"\n[启动] onefile 自解压+引导      "
              f"{(ts_first - t_launch) * 1000:7.0f} ms")

    ts, offset = wait_for(offset, "扫描完成：", 30000)
    if ts is None:
        print("启动超时：30s 内没看到扫描完成")
        return 1
    boot_scan = (ts - t_launch) * 1000
    if ts_first is not None:
        print(f"[启动] 程序初始化 -> 扫描完成    "
              f"{(ts - ts_first) * 1000:7.0f} ms")
    print(f"[启动] 合计 进程拉起 -> 可唤出   {boot_scan:7.0f} ms")

    ts, offset = wait_for(offset, "预热完成", 15000)
    if ts is not None:
        print(f"[启动] 进程拉起 -> 首帧预热完成  {(ts - t_launch) * 1000:7.0f} ms")

    # 2) 唤出延迟：发 show，等 QML 网格完成布局的打点。
    #
    # GRID 打点是 Panel.qml 里一个 80ms 的单次定时器（面板变可见时 restart），
    # 所以这里读到的时间天然含这 80ms。真实「窗口可见」时刻要减掉它——
    # 用 0 延迟打点实测过：60–83ms，中位约 65ms，和减完的结果吻合。
    GRID_TIMER_MS = 80
    print("\n[唤出] 连续测 5 次（发 show -> 面板可见）")
    lat = []
    for i in range(5):
        time.sleep(0.8)
        t0 = time.time()
        if not send(b"show"):
            break
        ts, offset = wait_for(offset, "GRID ", 5000)
        if ts is None:
            print(f"  第 {i + 1} 次：超时")
            continue
        d = (ts - t0) * 1000 - GRID_TIMER_MS
        lat.append(d)
        print(f"  第 {i + 1} 次：{d:6.0f} ms")
        time.sleep(0.3)
        send(b"hide")
    if lat:
        lat.sort()
        print(f"  中位数 {lat[len(lat) // 2]:.0f} ms    "
              f"最快 {lat[0]:.0f} ms   最慢 {lat[-1]:.0f} ms")

    # 3) 常驻内存
    time.sleep(0.5)
    m = mem_kb()
    if m:
        print(f"\n[资源] 物理内存 {m['ws'] / 1024:.0f} MB   "
              f"私有提交 {m['priv'] / 1024:.0f} MB   句柄 {m['handles']}")
    else:
        print("\n[资源] 取不到内存信息")

    # 4) 正常退出 -> 桌面图标必须还回去
    print("\n[退出] 发 quit，检查图标恢复…")
    send(b"quit")
    ts, _ = wait_for(offset, "退出：恢复系统桌面图标", 8000)
    print("  桌面图标恢复：", "OK" if ts else "!! 没看到恢复记录")
    time.sleep(1.0)
    subprocess.run(["taskkill", "/F", "/IM", "DeskDock.exe"],
                   capture_output=True)

    print("\n" + "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
