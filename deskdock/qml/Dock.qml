import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Layouts 1.15
import QtGraphicalEffects 1.15

// 屏幕底部的常驻 Dock。和胶囊的分工：
//   胶囊 = 桌面上的入口，点开是全部应用（收纳语义）
//   Dock = 最高频的那几个应用直接躺在手边，点一下就走，连面板都不用开
//
// 视觉上刻意压得比面板重：一条深色玻璃，没有文字，图标大小一致。
// 用 RowLayout 而不是 Row：Row 的 implicitWidth 不会算上 Repeater 动态生成的
// 那批图标（实测只算出网格和齿轮的 82px，Dock 缩成一条小方片）。
Window {
    id: dock

    // 放大时图标会溢出格子，窗口要留出这一圈余量，否则超出的部分被裁掉
    readonly property int pad: 18
    readonly property int iconSize: controller.dockIconSize
    readonly property int barH: iconSize + 22
    readonly property var items: controller.dockItems
    // 固定系统项（此电脑、回收站）：不混在应用里，单独一组放最左
    readonly property var specials: controller.dockSpecial

    property var scr: null
    property bool reported: false

    function refreshScreen() {
        scr = controller.dockScreenInfo();
    }

    // 尺寸不用绑定推导。RowLayout 的 implicitWidth 是延迟更新的，绑定只在
    // 它还是初值时求过一次就再也不重算了 —— 结果是窗口缩成 134px 的小方片，
    // 而内容其实是 538px。改成布局稳定后显式量一次。
    // 位置也不能用绑定：窗口显示时平台层会把实际几何写回 x/y，
    // 一写就把绑定打断了，之后 width 怎么变它都停在旧位置（实测卡在 1200,1434）。
    // 初值必须非零：Qt 对 0 尺寸的窗口不建原生句柄，之后 visible 已经是 true
    // 就不会再建一次，表现为"日志说有窗口，枚举却找不到"
    width: 240
    height: barH + pad * 2
    x: 0
    y: 0

    function fit() {
        var w = Math.round(bar.implicitWidth + 24);
        if (w <= 0 || !scr)
            return;
        stage.width = w;
        stage.height = dock.barH;
        var fullW = w + dock.pad * 2;
        var fullH = dock.barH + dock.pad * 2;
        if (dock.width !== fullW)
            dock.width = fullW;
        if (dock.height !== fullH)
            dock.height = fullH;
        var tx = Math.round(scr.x + (scr.w - fullW) / 2);
        var ty = Math.round(scr.bottom - fullH - 6);
        if (dock.x !== tx)
            dock.x = tx;
        if (dock.y !== ty)
            dock.y = ty;
        // 这个窗口不接收焦点，改完几何后 Qt 不一定会自己重绘一次
        dock.requestUpdate();
        reportGeo();
    }

    visible: controller.dockVisible && items.length > 0
    title: "DeskDockDock"
    color: "transparent"
    // Tool = 不进任务栏、不占 Alt+Tab；DoesNotAcceptFocus = 点 Dock 不会把
    // 当前正在用的窗口踢到后台，启动完应用前台还是它
    flags: Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
           | Qt.WindowDoesNotAcceptFocus

    // 列表变了（装了新软件、刚启动过某个应用）就重新量一次
    onItemsChanged: Qt.callLater(fit)
    onVisibleChanged: {
        if (visible) {
            refreshScreen();
            Qt.callLater(fit);
        }
    }

    function reportGeo() {
        if (reported || width <= 0 || !scr)
            return;
        reported = true;
        controller.debugLog("DOCK x=" + Math.round(dock.x)
                            + " y=" + Math.round(dock.y)
                            + " w=" + Math.round(dock.width)
                            + " h=" + Math.round(dock.height)
                            + " icon=" + dock.iconSize
                            + " n=" + dock.items.length
                            + " scrW=" + (dock.scr ? dock.scr.w : -1)
                            + " scrBottom=" + (dock.scr ? dock.scr.bottom : -1)
                            + " barW=" + Math.round(bar.implicitWidth)
                            + " vis=" + dock.visible
                            + " cfgVis=" + controller.dockVisible
                            + " dpr=" + Screen.devicePixelRatio);
    }

    Component.onCompleted: {
        refreshScreen();
        controller.registerDock(dock);
        // 1 = DWMWA_SYSTEMBACKDROP_TYPE 关掉系统背景：玻璃由 QML 自己画，
        // 系统那层亚克力会和透明底色打架
        controller.applyEffects(dock, 1);
        // 布局要等 RowLayout 算完才有 implicitWidth，callLater 排到下一次事件循环
        Qt.callLater(fit);
        Qt.callLater(fit);
    }

    // 光标在不在 Dock 上。用 HoverHandler 而不是盖一层 MouseArea：
    // 后者会把图标的点击事件全吃掉
    HoverHandler { id: hover }

    // 一个图标格子。固定系统项和普通应用长得一样，共用这一份定义
    Component {
        id: dockIcon

        Item {
            id: cell
            Layout.preferredWidth: dock.iconSize
            Layout.preferredHeight: dock.iconSize
            z: cellMa.containsMouse ? 3 : 1

            scale: cellMa.containsMouse ? 1.2 : 1.0
            transform: Translate { y: cellMa.containsMouse ? -4 : 0 }
            Behavior on scale {
                NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
            }

            Image {
                id: icon
                anchors.fill: parent
                source: modelData.iconPath ? "file:///" + modelData.iconPath : ""
                // 按 2x 取图再缩到 iconSize，边缘才不发毛
                sourceSize: Qt.size(dock.iconSize * 2, dock.iconSize * 2)
                fillMode: Image.PreserveAspectFit
                smooth: true
                visible: status === Image.Ready
            }

            // 图标还没提取出来：先放首字母，别留个空洞
            Rectangle {
                anchors.fill: parent
                radius: 12
                visible: !icon.visible
                color: "#2BFFFFFF"
                border.width: 1
                border.color: "#1AFFFFFF"
                Text {
                    anchors.centerIn: parent
                    text: modelData.name ? modelData.name.charAt(0) : "?"
                    color: "#D9FFFFFF"
                    font.pixelSize: Math.round(dock.iconSize * 0.42)
                    font.weight: Font.DemiBold
                }
            }

            MouseArea {
                id: cellMa
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: controller.launchDockItem(modelData.entryId)
            }
        }
    }

    Item {
        id: stage
        anchors.centerIn: parent
        width: bar.implicitWidth + 24
        height: dock.barH

        Rectangle {
            id: glass
            anchors.fill: parent
            radius: 22

            gradient: Gradient {
                GradientStop {
                    position: 0.0
                    color: hover.hovered ? "#F23A3D43" : "#E62D3036"
                }
                GradientStop {
                    position: 1.0
                    color: hover.hovered ? "#F222252B" : "#E61B1E23"
                }
            }
            Behavior on color { ColorAnimation { duration: 180 } }
        }

        DropShadow {
            anchors.fill: glass
            source: glass
            radius: 22
            samples: 26
            spread: 0.14
            color: "#8F000000"
            verticalOffset: 7
            transparentBorder: true
        }

        // 上缘一条高光，玻璃才有厚度
        Rectangle {
            anchors.left: glass.left
            anchors.right: glass.right
            anchors.top: glass.top
            anchors.margins: 1
            height: 1
            radius: 0.5
            color: hover.hovered ? "#4DFFFFFF" : "#2BFFFFFF"
            Behavior on color { ColorAnimation { duration: 180 } }
        }

        Rectangle {
            anchors.fill: glass
            radius: 22
            color: "transparent"
            border.width: 1
            border.color: hover.hovered ? "#4AFFFFFF" : "#24FFFFFF"
            Behavior on border.color { ColorAnimation { duration: 180 } }
        }

        RowLayout {
            id: bar
            anchors.centerIn: parent
            spacing: 5

            // ---- 左：全部应用（和胶囊同一个入口）----
            Item {
                Layout.preferredWidth: dock.iconSize
                Layout.preferredHeight: dock.iconSize

                Rectangle {
                    anchors.fill: parent
                    radius: 12
                    color: launcher.containsMouse ? "#2EFFFFFF" : "transparent"
                    Behavior on color { ColorAnimation { duration: 140 } }
                }

                Grid {
                    columns: 2
                    rows: 2
                    spacing: 4.5
                    anchors.centerIn: parent
                    Repeater {
                        model: 4
                        Rectangle {
                            width: 8
                            height: 8
                            radius: 2.4
                            color: launcher.containsMouse ? "#F2FFFFFF" : "#B3FFFFFF"
                            Behavior on color { ColorAnimation { duration: 140 } }
                        }
                    }
                }

                MouseArea {
                    id: launcher
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: controller.toggle_panel()
                }
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 26
                color: "#26FFFFFF"
            }

            // ---- 固定系统项：此电脑、回收站 ----
            // 钉在应用前面，中间隔一条线：它们不是"装的程序"，
            // 混在按使用频率排的应用里会显得毫无章法
            Repeater {
                model: dock.specials
                delegate: dockIcon
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 26
                color: "#26FFFFFF"
                visible: dock.specials.length > 0
            }

            // ---- 最高频的应用 ----
            Repeater {
                model: dock.items
                delegate: dockIcon
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 26
                color: "#26FFFFFF"
            }

            // ---- 右：设置 ----
            Item {
                Layout.preferredWidth: dock.iconSize
                Layout.preferredHeight: dock.iconSize

                Rectangle {
                    anchors.fill: parent
                    radius: 12
                    color: gearMa.containsMouse ? "#2EFFFFFF" : "transparent"
                    Behavior on color { ColorAnimation { duration: 140 } }
                }

                Canvas {
                    anchors.centerIn: parent
                    width: 24
                    height: 24
                    opacity: gearMa.containsMouse ? 1.0 : 0.82
                    Behavior on opacity { NumberAnimation { duration: 140 } }
                    onPaint: {
                        var ctx = getContext("2d");
                        ctx.reset();
                        ctx.translate(12, 12);
                        ctx.fillStyle = "#E6FFFFFF";
                        var teeth = 8;
                        for (var i = 0; i < teeth; i++) {
                            ctx.save();
                            ctx.rotate(i * Math.PI * 2 / teeth);
                            ctx.fillRect(-2.0, -10.9, 4.0, 4.8);
                            ctx.restore();
                        }
                        ctx.beginPath();
                        ctx.arc(0, 0, 8.0, 0, Math.PI * 2);
                        ctx.fill();
                        // 挖掉中心做出轴孔
                        ctx.globalCompositeOperation = "destination-out";
                        ctx.beginPath();
                        ctx.arc(0, 0, 3.3, 0, Math.PI * 2);
                        ctx.fill();
                    }
                }

                MouseArea {
                    id: gearMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: controller.openSettings()
                }
            }
        }
    }
}
