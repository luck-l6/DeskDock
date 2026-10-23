"""排查毛玻璃底图：单独验证 image provider 能否被 QML 消费。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt5.QtCore import QObject, QTimer, QUrl, pyqtProperty, pyqtSignal, qInstallMessageHandler
from PyQt5.QtQml import QQmlApplicationEngine
from PyQt5.QtWidgets import QApplication

from deskdock.backdrop import BackdropProvider

QML = """
import QtQuick 2.15
import QtQuick.Window 2.15
import QtGraphicalEffects 1.15

Window {
    visible: true
    width: 500; height: 320
    color: "#111"
    Image {
        id: shot
        anchors.fill: parent
        source: ctrl.src
        fillMode: Image.Stretch
        smooth: true
    }
    RadialGradient {
        anchors.fill: parent
        horizontalRadius: 400
        verticalRadius: 300
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#00000000" }
            GradientStop { position: 1.0; color: "#7A000000" }
        }
    }
    Image {
        anchors.fill: parent
        source: "%s"
        fillMode: Image.Tile
        opacity: 0.5
    }
    Component.onCompleted: console.log("LOADED", Source.status)
}
""" % (ROOT / "deskdock" / "qml" / "assets" / "noise.png").as_posix()


class Ctrl(QObject):
    def __init__(self, provider: BackdropProvider) -> None:
        super().__init__()
        self.p = provider
        self.ok = provider.capture()

    def getSrc(self) -> str:
        return "image://backdrop/shot?1"

    src = pyqtProperty(str, getSrc)


def main() -> int:
    app = QApplication(sys.argv)
    qInstallMessageHandler(lambda m, c, msg: print("QML:", msg))

    engine = QQmlApplicationEngine()
    provider = BackdropProvider()
    engine.addImageProvider("backdrop", provider)
    ctrl = Ctrl(provider)
    print("capture ok:", ctrl.ok, "ready:", provider.ready)

    engine.rootContext().setContextProperty("ctrl", ctrl)

    tmp = ROOT / "tools" / "_probe_backdrop.qml"
    tmp.write_text(QML, encoding="utf-8")
    engine.load(QUrl.fromLocalFile(str(tmp)))
    print("roots:", len(engine.rootObjects()))

    QTimer.singleShot(1200, app.quit)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
