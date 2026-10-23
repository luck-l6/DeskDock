"""抓一张全屏截图，用来肉眼验收界面效果。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PyQt5.QtGui import QGuiApplication

out = Path(sys.argv[1] if len(sys.argv) > 1 else "shot.png").resolve()
delay = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0

app = QGuiApplication(sys.argv)
if delay:
    time.sleep(delay)
scr = QGuiApplication.primaryScreen()
shot = scr.grabWindow(0)
shot.save(str(out), "PNG")
print("saved", out, shot.width(), "x", shot.height())
