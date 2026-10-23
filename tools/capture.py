"""逐帧抓屏：触发面板显示，把 1.4 秒内的画面存成 PNG，用来定位"闪"的来源。

用法: python tools/capture.py [帧数]
产物: tools/frames/f00.png ... 以及 tools/frames/index.txt（每帧的分辨率）
"""

import os
import sys
import time

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtNetwork import QLocalSocket

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 28
STEP = 0.05


def send(cmd: bytes) -> None:
    s = QLocalSocket()
    s.connectToServer("DeskDock.SingleInstance")
    if s.waitForConnected(300):
        s.write(cmd)
        s.flush()
        s.waitForBytesWritten(300)
        s.disconnectFromServer()


def trigger_show() -> None:
    send(b"show")


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        try:
            os.remove(os.path.join(OUT, f))
        except OSError:
            pass

    app = QGuiApplication(sys.argv)
    scr = QGuiApplication.primaryScreen()

    # 可选预热：先完整走一遍 show/hide，再抓"第二次唤出"——
    # 用来验证预热之后首帧是否还会闪
    if len(sys.argv) > 2 and sys.argv[2] == "warm":
        send(b"show")
        time.sleep(2.5)
        send(b"hide")
        time.sleep(0.8)

    # 先抓一帧"唤出前"的桌面当基准
    shots = []
    base = scr.grabWindow(0).toImage()
    shots.append(("base", base))

    trigger_show()
    t0 = time.monotonic()
    for i in range(N):
        img = scr.grabWindow(0).toImage()
        shots.append(("f%02d" % i, img))
        # 抓帧本身要耗时，扣掉它才能保持固定间隔
        spent = time.monotonic() - t0 - i * STEP
        if spent < STEP:
            time.sleep(STEP - spent)

    lines = []
    for name, img in shots:
        p = os.path.join(OUT, name + ".png")
        img.save(p, "PNG")
        lines.append("%s %dx%d" % (name, img.width(), img.height()))

    with open(os.path.join(OUT, "index.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("saved %d frames -> %s" % (len(shots), OUT))
    for ln in lines:
        print(" ", ln)


if __name__ == "__main__":
    main()
