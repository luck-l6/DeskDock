import QtQuick 2.15
import QtQuick.Window 2.15
import QtGraphicalEffects 1.15

// 桌面入口胶囊。纯图形，不放文字：文字会让胶囊显得笨重，而且"应用"两个字
// 在桌面上读起来像是系统图标的标签。四个小方块就是"应用收纳"的意思。
Window {
    id: cap

    property int offsetX: 0
    property int offsetY: 0
    property bool dragging: false
    property bool hot: ma.containsMouse

    width: 132
    height: 78
    flags: Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnBottomHint
    color: "transparent"
    visible: controller.capsuleVisible

    function place() {
        var px = controller.capsuleX;
        var py = controller.capsuleY;
        var scr = cap.screen;
        var sw = scr ? scr.width : Screen.width;
        var sh = scr ? scr.height : Screen.height;
        if (px < 0 || py < 0) {
            px = sw - cap.width - 28;
            py = sh - cap.height - 56;
        }
        cap.x = px - cap.offsetX;
        cap.y = py - cap.offsetY;
    }

    function snapToEdge() {
        var scr = cap.screen;
        var sw = scr ? scr.width : Screen.width;
        var sh = scr ? scr.height : Screen.height;
        var gx = cap.x + cap.offsetX;
        var gy = cap.y + cap.offsetY;
        var left = gx;
        var right = sw - (gx + cap.width);
        var top = gy;
        var bottom = sh - (gy + cap.height);
        var m = Math.min(left, right, top, bottom);
        var tx = gx;
        var ty = gy;
        if (m === left)
            tx = 8;
        else if (m === right)
            tx = sw - cap.width - 8;
        else if (m === top)
            ty = 8;
        else
            ty = sh - cap.height - 8;
        snapX.to = tx - cap.offsetX;
        snapY.to = ty - cap.offsetY;
        snapX.start();
        snapY.start();
    }

    Component.onCompleted: {
        controller.registerCapsule(cap);
        place();
        controller.pinToBottom(cap);
        controller.applyEffects(cap, 3);
    }

    NumberAnimation on x { id: snapX; duration: 260; easing.type: Easing.OutCubic; running: false }
    NumberAnimation on y { id: snapY; duration: 260; easing.type: Easing.OutCubic; running: false }

    Item {
        id: stage
        anchors.centerIn: parent
        width: 86
        height: 46
        scale: cap.hot ? 1.06 : 1.0
        opacity: controller.autoHide ? (cap.hot ? 1.0 : 0.5) : 1.0

        Behavior on scale { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 220 } }

        // 玻璃主体
        Rectangle {
            id: pill
            anchors.fill: parent
            radius: 23

            gradient: Gradient {
                GradientStop { position: 0.0; color: cap.hot ? "#F2384350" : "#D92C3540" }
                GradientStop { position: 1.0; color: cap.hot ? "#F21D242E" : "#D9181F27" }
            }
            Behavior on color { ColorAnimation { duration: 200 } }
        }

        // 投影：从背景里"浮起来"
        DropShadow {
            anchors.fill: pill
            source: pill
            radius: 18
            samples: 24
            spread: 0.12
            color: "#8A000000"
            verticalOffset: 5
            transparentBorder: true
        }

        // 上缘高光
        Rectangle {
            anchors.left: pill.left
            anchors.right: pill.right
            anchors.top: pill.top
            anchors.margins: 1
            height: 1
            radius: 0.5
            color: cap.hot ? "#59FFFFFF" : "#33FFFFFF"
            Behavior on color { ColorAnimation { duration: 200 } }
        }

        // 描边
        Rectangle {
            anchors.fill: pill
            radius: 23
            color: "transparent"
            border.width: 1
            border.color: cap.hot ? "#57FFFFFF" : "#2EFFFFFF"
            Behavior on border.color { ColorAnimation { duration: 200 } }
        }

        // 四格：像被收起来的应用网格
        Grid {
            columns: 2
            rows: 2
            spacing: 5
            anchors.centerIn: parent

            Repeater {
                model: 4
                Rectangle {
                    width: 10
                    height: 10
                    radius: 3.6
                    gradient: Gradient {
                        GradientStop {
                            position: 0.0
                            color: cap.hot
                                   ? (index === 0 ? "#CFE6FA" : "#9DBDD8")
                                   : (index === 0 ? "#93B4D0" : "#5A738C")
                        }
                        GradientStop {
                            position: 1.0
                            color: cap.hot
                                   ? (index === 0 ? "#A8CDE9" : "#7798B4")
                                   : (index === 0 ? "#6E8CA8" : "#42566B")
                        }
                    }
                    Behavior on color { ColorAnimation { duration: 200 } }
                }
            }
        }
    }

    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        property real startMX: 0
        property real startMY: 0
        property bool moved: false

        onPressed: function(mouse) {
            snapX.stop();
            snapY.stop();
            startMX = mouseX;
            startMY = mouseY;
            moved = false;
        }

        onPositionChanged: function(mouse) {
            if (!pressed)
                return;
            cap.x += mouseX - startMX;
            cap.y += mouseY - startMY;
            if (Math.abs(mouseX - startMX) + Math.abs(mouseY - startMY) > 4)
                moved = true;
        }

        onReleased: function(mouse) {
            if (!moved) {
                console.log("capsule onReleased -> toggle_panel");
                controller.toggle_panel();
            } else {
                console.log("capsule onReleased 忽略(拖动)");
                controller.saveCapsulePos(cap.x + cap.offsetX, cap.y + cap.offsetY);
                if (controller.autoHide)
                    snapToEdge();
            }
        }
    }
}
