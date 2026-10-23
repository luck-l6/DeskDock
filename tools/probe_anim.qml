import QtQuick 2.15
import QtQuick.Window 2.15
Window {
    id: w
    visible: true
    width: 300; height: 200
    property real p: 0
    Behavior on p { NumberAnimation { duration: 260; easing.type: Easing.OutQuart } }
    Component.onCompleted: {
        w.p = 1;
        console.log("set ->", w.p)
    }
    Timer {
        interval: 600; running: true
        onTriggered: console.log("after600 ->", w.p)
    }
    Rectangle {
        anchors.fill: parent
        anchors.margins: 20
        color: "red"
        opacity: w.p
    }
}
