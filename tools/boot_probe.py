"""最小复现：QML Window 在 Component.onCompleted 里回调 Python 操作原生句柄。"""

from __future__ import annotations

import ctypes
import sys

from PyQt5.QtCore import QObject, QTimer, pyqtSlot  # noqa: E402
from PyQt5.QtQml import QQmlApplicationEngine  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

QML = """
import QtQuick 2.15
import QtQuick.Window 2.15
Window {
    visible: true
    width: 200
    height: 100
    flags: Qt.FramelessWindowHint | Qt.Tool
    color: "transparent"
    Component.onCompleted: controller.applyEffects(this)
}
"""


class Stub(QObject):
    @pyqtSlot(QObject)
    def applyEffects(self, win) -> None:
        print("applyEffects: called", flush=True)
        hwnd = int(win.winId())
        print("applyEffects: hwnd =", hwnd, flush=True)
        dwm = ctypes.WinDLL("dwmapi")
        val = ctypes.c_int(3)
        r = dwm.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(val),
                                      ctypes.sizeof(val))
        print("applyEffects: dwm =", r, flush=True)


def main() -> int:
    app = QApplication(sys.argv)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("controller", Stub())
    print("loading qml", flush=True)
    engine.loadData(QML.encode("utf-8"))
    print("loaded, roots =", len(engine.rootObjects()), flush=True)
    QTimer.singleShot(1500, app.quit)
    rc = app.exec_()
    print("event loop exit", rc, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
