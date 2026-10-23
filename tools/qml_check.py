"""离线加载全部 QML，把警告打出来。不抢单实例、不动桌面图标。

    python tools/qml_check.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt5.QtCore import QUrl  # noqa: E402
from PyQt5.QtQml import QQmlApplicationEngine  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from deskdock import app as dk  # noqa: E402
from deskdock.app import QML_MESSAGES, Controller, _install_message_handler  # noqa: E402


def main() -> int:
    _install_message_handler()
    app = QApplication(sys.argv)
    engine = QQmlApplicationEngine()
    ctrl = Controller(engine)
    engine.rootContext().setContextProperty("controller", ctrl)
    engine.rootContext().setContextProperty("appModel", ctrl.filter)
    engine.rootContext().setContextProperty("rawModel", ctrl.model)

    for name in ("Panel.qml", "Capsule.qml", "Settings.qml"):
        before = len(engine.rootObjects())
        engine.load(QUrl.fromLocalFile(str(dk.QML_DIR / name)))
        print(f"{name}: {before} -> {len(engine.rootObjects())}")

    print("ROOT_OBJECTS:", len(engine.rootObjects()))
    print("QML_MESSAGES:", len(QML_MESSAGES))
    for m in QML_MESSAGES[:40]:
        print("  -", m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
