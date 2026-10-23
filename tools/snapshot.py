"""唤出面板并保持打开，截一张图存到 tools/frames/snap.png。

用法: python tools/snapshot.py [等待毫秒]
"""

import sys
import time

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtNetwork import QLocalSocket

app = QGuiApplication(sys.argv)

s = QLocalSocket()
s.connectToServer("DeskDock.SingleInstance")
if not s.waitForConnected(500):
    print("DeskDock 没在运行")
    sys.exit(1)
s.write(b"show")
s.flush()
s.waitForBytesWritten(500)
s.disconnectFromServer()

wait = int(sys.argv[1]) if len(sys.argv) > 1 else 1200
for _ in range(wait // 50):
    app.processEvents()
    time.sleep(0.05)

scr = QGuiApplication.primaryScreen()
img = scr.grabWindow(0).toImage()
img.save("tools/frames/snap.png", "PNG")
print("saved", img.width(), "x", img.height())
