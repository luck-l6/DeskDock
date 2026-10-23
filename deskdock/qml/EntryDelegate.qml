import QtQuick 2.15
import QtQuick.Controls 2.15
import QtGraphicalEffects 1.15

Item {
    id: root

    property string entryId: ""
    property string name: ""
    property string iconPath: ""
    property bool focused: false
    property int iconSize: 64
    property bool dragging: false   // 正在被拖走：原位留个淡淡的空位
    property bool dragEnabled: true

    // 悬停时整体上浮
    property real lift: ma.containsMouse ? 4 : 0
    property real hoverT: ma.containsMouse ? 1 : 0

    signal activated()
    signal contextRequested(real mx, real my)
    signal dragRequested(real gx, real gy)
    signal dragMoved(real gx, real gy)
    signal dragReleased()

    Behavior on lift { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    Behavior on hoverT { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

    // ------------------------------------------------ 卡片背景
    Rectangle {
        id: card
        anchors.fill: parent
        anchors.margins: 3
        radius: 17
        border.width: 1
        border.color: root.focused ? "#4D5AA9FF" : "#1FFFFFFF"
        opacity: ma.containsMouse ? 1 : (root.focused ? 0.85 : 0)

        gradient: Gradient {
            GradientStop { position: 0.0; color: "#26FFFFFF" }
            GradientStop { position: 1.0; color: "#0AFFFFFF" }
        }

        Behavior on opacity { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
        Behavior on border.color { ColorAnimation { duration: 160 } }
    }

    // 键盘聚焦的柔光，只在选中项上渲染
    RectangularGlow {
        anchors.fill: card
        visible: root.focused
        glowRadius: 14
        spread: 0.06
        cornerRadius: 17
        color: "#4A5AA9FF"
    }

    // ------------------------------------------------ 主体
    Item {
        id: content
        anchors.centerIn: parent
        opacity: root.dragging ? 0.28 : 1
        Behavior on opacity { NumberAnimation { duration: 120 } }
        anchors.verticalCenterOffset: -root.lift
        width: root.width - 18
        height: root.iconSize + 10 + 34

        // 图标
        Item {
            id: iconBox
            width: root.iconSize
            height: root.iconSize
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            scale: 1 + 0.06 * root.hoverT

            // 接地阴影：让图标"坐"在桌面上，而不是飘着
            Image {
                source: "assets/shadow.png"
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: -root.iconSize * 0.13
                width: root.iconSize * 1.02
                height: root.iconSize * 0.44
                opacity: (0.5 + 0.35 * root.hoverT) * (root.iconPath ? 1 : 0)
                smooth: true
            }

            // 图标未就绪时的占位：首字 + 按名字生成的柔和底色
            Rectangle {
                id: placeholder
                anchors.fill: parent
                radius: root.iconSize * 0.24
                visible: icon.status !== Image.Ready

                readonly property int seed: {
                    var s = 0;
                    for (var i = 0; i < root.name.length; i++)
                        s += root.name.charCodeAt(i) * (i + 3);
                    return s;
                }

                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.hsla((placeholder.seed % 60) / 360 + 0.52, 0.42, 0.46, 1.0) }
                    GradientStop { position: 1.0; color: Qt.hsla((placeholder.seed % 60) / 360 + 0.56, 0.46, 0.30, 1.0) }
                }

                Text {
                    anchors.centerIn: parent
                    text: root.name.length > 0 ? root.name.charAt(0) : "?"
                    color: "#E6F0F8"
                    font.family: "Microsoft YaHei UI"
                    font.pixelSize: root.iconSize * 0.42
                    font.weight: Font.Medium
                }
            }

            Image {
                id: icon
                anchors.fill: parent
                // sourceSize 必须写死。绑到 iconSize 的话，拖一次图标大小滑杆
                // 每个格子都要按新尺寸重新解码一遍 PNG，几十个格子一起重解码，
                // 拖动就一卡一卡；切分类重建网格时同理。固定解码一次，之后
                // 只是 GPU 缩放，完全不掉帧。
                sourceSize.width: 160
                sourceSize.height: 160
                fillMode: Image.PreserveAspectFit
                asynchronous: false
                cache: true
                smooth: true
                source: root.iconPath ? "file:///" + root.iconPath : ""
                visible: status === Image.Ready
            }
        }

        // 名称
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: iconBox.bottom
            anchors.topMargin: 9
            width: parent.width
            text: root.name
            color: root.focused ? "#FFFFFF"
                 : (ma.containsMouse ? "#F8FBFD" : "#DCE6EF")
            font.family: "Microsoft YaHei UI"
            // 150% 缩放下 12px 太吃力，和 74px 的图标比例也不平衡
            font.pixelSize: 13
            font.weight: root.focused ? Font.Medium : Font.Normal
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WrapAtWordBoundaryOrAnywhere
            maximumLineCount: 2
            elide: Text.ElideRight
            lineHeightMode: Text.FixedHeight
            lineHeight: 17
            clip: true

            // 玻璃透亮之后，靠一层极淡的深色描边保住可读性
            style: Text.Outline
            styleColor: "#6B222830"

            Behavior on color { ColorAnimation { duration: 140 } }
        }
    }

    // 长按计时自己算。MouseArea 的 onPressAndHold 在 Windows + pythonw 下
    // 实测根本不触发（挂上日志一条都没有），不敢指望它。
    property real pressX: 0
    property real pressY: 0
    property bool suppressClick: false

    Timer {
        id: holdTimer
        interval: 330
        repeat: false
        onTriggered: {
            if (!ma.pressed || root.dragging)
                return;
            var p = ma.mapToGlobal(root.pressX, root.pressY);
            root.dragRequested(p.x, p.y);   // 左键按住不动 = 拖走它
        }
    }

    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        cursorShape: Qt.PointingHandCursor
        // 拖拽期间手势归我，别让上层的 Flickable 把它当滚动
        preventStealing: root.dragging

        onPressed: {
            root.pressX = ma.mouseX;
            root.pressY = ma.mouseY;
            // 右键只走单击菜单，不参与长按拖拽
            if ((ma.pressedButtons & Qt.LeftButton) && root.dragEnabled && !root.dragging)
                holdTimer.restart();
        }

        onClicked: {
            if (root.suppressClick) {
                root.suppressClick = false;
                return;
            }
            if (ma.pressedButtons & Qt.RightButton || mouse.button === Qt.RightButton) {
                var p = mapToGlobal(ma.mouseX, ma.mouseY);
                root.contextRequested(p.x, p.y);
            } else {
                root.activated();
            }
        }

        onPositionChanged: {
            if (root.dragging) {
                var q = mapToGlobal(ma.mouseX, ma.mouseY);
                root.dragMoved(q.x, q.y);
                return;
            }
            // 一按就滑走的是滚动/误触，不是长按
            if (holdTimer.running
                    && (Math.abs(ma.mouseX - root.pressX) + Math.abs(ma.mouseY - root.pressY)) > 8)
                holdTimer.stop();
        }

        onReleased: {
            holdTimer.stop();
            if (root.dragging) {
                root.dragReleased();
                root.suppressClick = true;   // 松手别顺手把应用启动了
            }
        }

        onCanceled: {
            holdTimer.stop();
            if (root.dragging)
                root.dragReleased();
        }
    }
}
