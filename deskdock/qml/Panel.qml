import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import QtGraphicalEffects 1.15

ApplicationWindow {
    id: win

    property bool isLaunchpad: controller.viewMode === "launchpad"

    // ---- 自适应栅格：按条目数量反推列数、单元格与图标尺寸 ----
    // 条目多的时候自动收紧，条目少（如搜索结果）自动放大
    property int gCount: Math.max(1, controller.resultCount)
    property real areaW: Math.max(320, width - 180)
    property real areaH: Math.max(240, height - 262)
    property int cols: {
        var c = Math.ceil(Math.sqrt(gCount * areaW / areaH));
        var cap = Math.max(1, Math.floor(areaW / 152));
        return Math.max(1, Math.min(c, cap));
    }
    property int rows: Math.ceil(gCount / cols)
    property int cellW: Math.floor(Math.min(isLaunchpad ? 208 : 168, areaW / cols))
    property int cellH: Math.floor(Math.min(isLaunchpad ? 212 : 172, areaH / rows))
    property int iconSize: Math.round(Math.max(52, Math.min(cellW * 0.56, cellH - 52)))

    // ---- 居中卡片模式：图标缩放由底栏滑杆控制 ----
    property real cardScale: 1.0
    property int cardIcon: Math.round(74 * cardScale)
    property int cardCellW: cardIcon + 56
    property int cardCellH: cardIcon + 60

    // 展开动画进度 0→1
    property real progress: 0

    Behavior on progress {
        id: progressBehavior
        enabled: true
        NumberAnimation { duration: 260; easing.type: Easing.OutQuart }
    }

    // 以胶囊为原点的展开缩放
    readonly property real expandScale: 0.94 + 0.06 * win.progress

    visible: false
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
    color: "transparent"
    width: 1280
    height: 800

    Component.onCompleted: {
        controller.registerPanel(win);
        controller.applyEffects(win, win.isLaunchpad ? 3 : 1);
    }

    // ======================================================= 背景层
    // 兜底底色：抓屏失败时界面依然有层次。
    // 只在全屏模式铺满；卡片模式下窗口四周必须保持透明，否则整块变成方块
    Rectangle {
        anchors.fill: parent
        visible: win.isLaunchpad
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#1E252D" }
            GradientStop { position: 0.5; color: "#141A20" }
            GradientStop { position: 1.0; color: "#0C1014" }
        }
    }

    // 真·毛玻璃：抓屏降采样后铺满，双线性拉伸天然柔化
    Image {
        id: glass
        anchors.fill: parent
        source: controller.backdropReady ? "image://backdrop/shot?" + controller.backdropToken : ""
        fillMode: Image.Stretch
        smooth: true
        asynchronous: false
        visible: win.isLaunchpad && controller.backdropReady
        opacity: 0.62
    }

    // 冷色压暗：让底图退到后面去，图标才是主角
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#7A090D13" }
            GradientStop { position: 0.45; color: "#940A0E14" }
            GradientStop { position: 1.0; color: "#AB080B10" }
        }
        visible: win.isLaunchpad
    }

    // 顶部极淡的冷光，制造光源方向
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#1FA6C6E4" }
            GradientStop { position: 0.3; color: "#00000000" }
            GradientStop { position: 1.0; color: "#00000000" }
        }
        visible: win.isLaunchpad
    }

    // 暗角：视线收进中央
    RadialGradient {
        anchors.fill: parent
        horizontalRadius: Math.max(win.width, win.height) * 0.82
        verticalRadius: Math.max(win.width, win.height) * 0.76
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#00000000" }
            GradientStop { position: 0.62; color: "#1F000000" }
            GradientStop { position: 1.0; color: "#6E000000" }
        }
        visible: win.isLaunchpad
    }

    // 颗粒：消掉渐变色带，给出印刷般的材质
    Image {
        anchors.fill: parent
        source: "assets/noise.png"
        fillMode: Image.Tile
        opacity: 0.55
        visible: win.isLaunchpad
    }

    // ======================================================= 全屏 Launchpad
    Item {
        id: launchpadBody
        anchors.fill: parent
        visible: win.isLaunchpad
        opacity: win.isLaunchpad ? 1 : 0
        scale: win.expandScale
        transformOrigin: Item.Center

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 44
            spacing: 22

            // ---------------- 搜索框 ----------------
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 52

                Item {
                    id: searchShell
                    anchors.centerIn: parent
                    width: Math.min(parent.width * 0.42, 660)
                    height: 54
                    scale: search.activeFocus ? 1.0 : 0.995

                    Behavior on scale { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

                    // 聚焦发光
                    RectangularGlow {
                        anchors.fill: parent
                        glowRadius: 18
                        spread: 0.1
                        cornerRadius: 25
                        color: "#555AA9FF"
                        opacity: search.activeFocus ? 1.0 : 0.0
                        Behavior on opacity { NumberAnimation { duration: 220 } }
                    }

                    // 玻璃底：上亮下暗，制造弧度感
                    Rectangle {
                        anchors.fill: parent
                        radius: 27
                        gradient: Gradient {
                            GradientStop {
                                position: 0.0
                                color: search.activeFocus ? "#46FFFFFF" : "#2EFFFFFF"
                            }
                            GradientStop {
                                position: 0.5
                                color: search.activeFocus ? "#22FFFFFF" : "#16FFFFFF"
                            }
                            GradientStop {
                                position: 1.0
                                color: search.activeFocus ? "#1A0A1220" : "#120A1220"
                            }
                        }
                        Behavior on color { ColorAnimation { duration: 200 } }
                    }

                    Rectangle {
                        anchors.fill: parent
                        radius: 27
                        color: "transparent"
                        border.width: 1
                        border.color: search.activeFocus ? "#8C7CC3FF" : "#4DFFFFFF"
                        Behavior on border.color { ColorAnimation { duration: 200 } }
                    }

                    TextField {
                        id: search
                        anchors.fill: parent
                        anchors.leftMargin: 46
                        anchors.rightMargin: 20
                        placeholderText: "搜索应用、文件…（wx → 微信）"
                        placeholderTextColor: "#B4C2CE"
                        color: "#F0F5F9"
                        font.family: "Microsoft YaHei UI"
                        font.pixelSize: 15
                        verticalAlignment: TextInput.AlignVCenter
                        leftPadding: 0
                        background: Item {}
                        focus: true
                        selectByMouse: true
                        selectionColor: "#4D5AA9FF"
                        selectedTextColor: "#FFFFFF"

                        onTextChanged: controller.setQuery(text)
                        Keys.onReturnPressed: controller.launchById("")
                        Keys.onEscapePressed: controller.hide_panel()
                        Keys.onDownPressed: { grid.moveCurrentIndexDown(); event.accepted = true; }
                        Keys.onUpPressed: { grid.moveCurrentIndexUp(); event.accepted = true; }
                        Keys.onRightPressed: { grid.moveCurrentIndexRight(); event.accepted = true; }
                        Keys.onLeftPressed: { grid.moveCurrentIndexLeft(); event.accepted = true; }
                    }

                    // 放大镜
                    Item {
                        anchors.left: parent.left
                        anchors.leftMargin: 18
                        anchors.verticalCenter: parent.verticalCenter
                        width: 18
                        height: 18

                        Rectangle {
                            width: 12
                            height: 12
                            radius: 6
                            color: "transparent"
                            border.width: 1.6
                            border.color: search.activeFocus ? "#B8D4F0" : "#8C9AA6"
                            Behavior on border.color { ColorAnimation { duration: 200 } }
                        }
                        Rectangle {
                            width: 6
                            height: 1.6
                            radius: 1
                            color: search.activeFocus ? "#B8D4F0" : "#8C9AA6"
                            x: 10
                            y: 12
                            rotation: 45
                            transformOrigin: Item.Left
                            Behavior on color { ColorAnimation { duration: 200 } }
                        }
                    }
                }
            }

            // ---------------- 分类 ----------------
            CategoryChips {
                Layout.fillWidth: true
                Layout.preferredHeight: 44
            }

            // ---------------- 图标网格 ----------------
            Item {
                id: gridBox
                Layout.fillWidth: true
                Layout.fillHeight: true

                GridView {
                    id: grid
                    anchors.centerIn: parent
                    // 拖动条目时别让 flick 抢走手势，否则格子会跟着滚
                    interactive: win.dragId === ""
                    width: Math.min(parent.width, win.cols * win.cellW)
                    height: Math.min(parent.height, win.rows * win.cellH)
                    cellWidth: win.cellW
                    cellHeight: win.cellH
                    clip: true
                    model: appModel
                    currentIndex: count > 0 ? 0 : -1
                    keyNavigationEnabled: false
                    boundsBehavior: Flickable.StopAtBounds
                    flickDeceleration: 2400

                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                    // 入场时错峰浮现
                    add: Transition {
                        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 220; easing.type: Easing.OutCubic }
                    }

                    delegate: EntryDelegate {
                        width: grid.cellWidth
                        height: grid.cellHeight
                        iconSize: win.iconSize
                        entryId: model.entryId
                        name: model.name
                        iconPath: model.iconPath
                        focused: GridView.isCurrentItem
                        dragging: win.dragId === model.entryId
                        onActivated: controller.launchById(model.entryId)
                        onContextRequested: (mx, my) => entryMenu.showFor(model.entryId, mx, my)
                        onDragRequested: (gx, gy) => win.beginDrag(model.entryId, index, gx, gy, grid)
                        onDragMoved: (gx, gy) => win.dragTo(gx, gy)
                        onDragReleased: win.endDrag(true)
                    }
                }

                Column {
                    anchors.centerIn: parent
                    spacing: 10
                    visible: grid.count === 0
                    opacity: visible ? 1 : 0

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: controller.query ? "没有匹配的项目" : "正在扫描…"
                        color: "#7B8894"
                        font.family: "Microsoft YaHei UI"
                        font.pixelSize: 14
                    }
                }
            }

            // ---------------- 底部状态 ----------------
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 26

                Row {
                    anchors.centerIn: parent
                    spacing: 8

                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: 5
                        height: 5
                        radius: 2.5
                        color: "#4E5AA9FF"
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: controller.query
                              ? "匹配 " + controller.resultCount + " 项"
                              : "共 " + controller.resultCount + " 项"
                        color: "#9AA8B4"
                        font.family: "Microsoft YaHei UI"
                        font.pixelSize: 12
                    }

                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: 1
                        height: 10
                        color: "#33FFFFFF"
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "回车打开"
                        color: "#7C8A96"
                        font.family: "Microsoft YaHei UI"
                        font.pixelSize: 12
                    }
                }
            }
        }
    }

    // ======================================================= 居中悬浮面板
    // 这一层就是窗口本身的大小：卡片 + 一圈投影边距。边距是**真透明**的，
    // 屏幕的其它部分完全不受影响，唤出时只有卡片这一小块在动。
    Item {
        id: gridBody
        anchors.fill: parent
        visible: !win.isLaunchpad
        opacity: win.isLaunchpad ? 0 : 1

        // 投影区（卡片外的透明边距）：点这里等同于点卡片外面，收起面板
        MouseArea {
            anchors.fill: parent
            onClicked: {
                // 刚唤出那几十毫秒里的点击多半是上一次点击的尾巴，不算收起
                if (win.awaitingReveal || Date.now() - win.shownAt < 400) {
                    console.log("点外部被忽略(展开保护期内)")
                    return
                }
                console.log("panel 点外部 -> hide_panel")
                controller.hide_panel()
            }
        }

        Item {
            id: cardShell
            x: controller.cardPad
            y: controller.cardPad
            width: Math.max(320, parent.width - controller.cardPad * 2)
            height: Math.max(240, parent.height - controller.cardPad * 2)

            // 从胶囊所在点放大弹出：原点取胶囊坐标相对卡片左上角的位置
            opacity: win.progress
            transform: Scale {
                origin.x: controller.originX - cardShell.x
                origin.y: controller.originY - cardShell.y
                xScale: 0.88 + 0.12 * win.progress
                yScale: 0.88 + 0.12 * win.progress
            }

            // 吃掉点击，避免点卡片内部被当成「点外面」关闭
            MouseArea { anchors.fill: parent }

            // 柔和投影：半径要小于窗口的透明边距，否则会被窗口边缘切出硬边
            RectangularGlow {
                anchors.fill: card
                glowRadius: 28
                spread: 0.04
                cornerRadius: 26
                color: "#70000000"
            }

            // ---------- 亚克力磨砂层：卡片正后方那块壁纸的高斯模糊 ----------
            Item {
                id: frost
                anchors.fill: parent
                visible: controller.backdropReady
                layer.enabled: true
                layer.smooth: true
                layer.effect: OpacityMask {
                    maskSource: Rectangle {
                        width: cardShell.width
                        height: cardShell.height
                        radius: 24
                        color: "#FFFFFF"
                    }
                }

                Image {
                    id: frostImg
                    anchors.fill: parent
                    // 卡片正后方那块屏幕区域：窗口坐标 + 透明边距 = 屏幕坐标
                    source: controller.backdropReady
                            ? "image://backdrop/card?"
                              + Math.round(win.x + controller.cardPad) + ","
                              + Math.round(win.y + controller.cardPad) + ","
                              + Math.round(cardShell.width) + ","
                              + Math.round(cardShell.height) + ","
                              + controller.backdropToken
                            : ""
                    fillMode: Image.Stretch
                    smooth: true
                    asynchronous: false
                    cache: false
                }

                // 低饱和度：把壁纸的艳色压成柔和的灰蓝
                Desaturate {
                    anchors.fill: parent
                    source: frostImg
                    desaturation: 0.28
                }

                // 磨砂颗粒：打散渐变色带，摸上去有砂面感
                Image {
                    anchors.fill: parent
                    source: "assets/noise.png"
                    fillMode: Image.Tile
                    opacity: 0.07
                }

                // 提亮 + 白色雾化，让玻璃有「通透」感而不是一块黑
                Rectangle {
                    anchors.fill: parent
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: "#1CFBFDFF" }
                        GradientStop { position: 0.55; color: "#12F2F6FC" }
                        GradientStop { position: 1.0; color: "#0CECF0F8" }
                    }
                }

                // 压暗一层，保证白色文字和图标读得清
                Rectangle {
                    anchors.fill: parent
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: "#440A1016" }
                        GradientStop { position: 0.6; color: "#4C0A1016" }
                        GradientStop { position: 1.0; color: "#540A1016" }
                    }
                }
            }

            // 兜底：抓不到壁纸时也要有玻璃质感
            Rectangle {
                anchors.fill: parent
                radius: 24
                visible: !controller.backdropReady
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "#A8222C38" }
                    GradientStop { position: 1.0; color: "#AE141C28" }
                }
            }

            // 淡淡的白色细边框
            Rectangle {
                id: card
                anchors.fill: parent
                radius: 24
                color: "transparent"
                border.width: 1
                border.color: "#5CFFFFFF"
            }

            // 微弱内发光：贴着边框再描一圈更淡的白
            Rectangle {
                anchors.fill: parent
                anchors.margins: 1
                radius: 23
                color: "transparent"
                border.width: 1
                border.color: "#2BFFFFFF"
            }

            // 顶部柔和反光
            Rectangle {
                anchors.fill: parent
                anchors.margins: 1
                radius: 23
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "#22FFFFFF" }
                    GradientStop { position: 0.42; color: "#08FFFFFF" }
                    GradientStop { position: 1.0; color: "#00FFFFFF" }
                }
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: 18
                anchors.rightMargin: 18
                anchors.topMargin: 16
                anchors.bottomMargin: 12
                spacing: 12

                // ---------------- 顶栏：搜索 + 操作 ----------------
                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    spacing: 8

                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40

                        Rectangle {
                            anchors.fill: parent
                            radius: 20
                            // 原来 #14FFFFFF 在深色玻璃上几乎看不见，只有一个
                            // 放大镜浮在那儿。加深底色和边框，让框本身有存在感。
                            color: search2.activeFocus ? "#3AFFFFFF" : "#20FFFFFF"
                            border.width: 1
                            border.color: search2.activeFocus ? "#8C5AA9FF" : "#3DFFFFFF"
                            Behavior on color { ColorAnimation { duration: 180 } }
                            Behavior on border.color { ColorAnimation { duration: 180 } }
                        }

                        TextField {
                            id: search2
                            anchors.fill: parent
                            anchors.leftMargin: 38
                            anchors.rightMargin: 14
                            placeholderText: "搜索应用、文件…（wx → 微信）"
                            placeholderTextColor: "#C2CFDA"
                            color: "#F2F7FB"
                            font.family: "Microsoft YaHei UI"
                            font.pixelSize: 14
                            verticalAlignment: TextInput.AlignVCenter
                            leftPadding: 0
                            background: Item {}
                            focus: true
                            selectByMouse: true
                            selectionColor: "#4D5AA9FF"
                            selectedTextColor: "#FFFFFF"

                            onTextChanged: controller.setQuery(text)
                            Keys.onReturnPressed: controller.launchById("")
                            Keys.onEscapePressed: controller.hide_panel()
                            Keys.onDownPressed: { grid2.moveCurrentIndexDown(); event.accepted = true; }
                            Keys.onUpPressed: { grid2.moveCurrentIndexUp(); event.accepted = true; }
                            Keys.onRightPressed: { grid2.moveCurrentIndexRight(); event.accepted = true; }
                            Keys.onLeftPressed: { grid2.moveCurrentIndexLeft(); event.accepted = true; }
                        }

                        // 放大镜
                        Item {
                            anchors.left: parent.left
                            anchors.leftMargin: 15
                            anchors.verticalCenter: parent.verticalCenter
                            width: 16
                            height: 16

                            Rectangle {
                                width: 10
                                height: 10
                                radius: 5
                                color: "transparent"
                                border.width: 1.5
                                border.color: search2.activeFocus ? "#B8D4F0" : "#8896A3"
                            }
                            Rectangle {
                                width: 5
                                height: 1.5
                                radius: 1
                                color: search2.activeFocus ? "#B8D4F0" : "#8896A3"
                                x: 8
                                y: 10
                                rotation: 45
                                transformOrigin: Item.Left
                            }
                        }
                    }

                    // 刷新
                    Item {
                        Layout.preferredWidth: 38
                        Layout.preferredHeight: 38
                        Rectangle {
                            anchors.fill: parent
                            radius: 19
                            color: refreshMa.containsMouse ? "#26FFFFFF" : "#12FFFFFF"
                            border.width: 1
                            border.color: "#2BFFFFFF"
                            Behavior on color { ColorAnimation { duration: 140 } }
                        }
                        Text {
                            anchors.centerIn: parent
                            text: "\u27F3"
                            color: "#D6E2EC"
                            font.family: "Segoe UI Symbol"
                            font.pixelSize: 16
                        }
                        MouseArea {
                            id: refreshMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: controller.refresh()
                        }
                    }

                    // 设置
                    Item {
                        Layout.preferredWidth: 38
                        Layout.preferredHeight: 38
                        Rectangle {
                            anchors.fill: parent
                            radius: 19
                            color: gearMa.containsMouse ? "#26FFFFFF" : "#12FFFFFF"
                            border.width: 1
                            border.color: "#2BFFFFFF"
                            Behavior on color { ColorAnimation { duration: 140 } }
                        }
                        Text {
                            anchors.centerIn: parent
                            text: "\u2699"
                            color: "#D6E2EC"
                            font.family: "Segoe UI Symbol"
                            font.pixelSize: 15
                        }
                        MouseArea {
                            id: gearMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: controller.openSettings()
                        }
                    }

                    // 收起
                    Item {
                        Layout.preferredWidth: 38
                        Layout.preferredHeight: 38
                        Rectangle {
                            anchors.fill: parent
                            radius: 19
                            color: closeMa.containsMouse ? "#33FF6B6B" : "#12FFFFFF"
                            border.width: 1
                            border.color: closeMa.containsMouse ? "#55FF8080" : "#1FFFFFFF"
                            Behavior on color { ColorAnimation { duration: 140 } }
                        }
                        Item {
                            anchors.centerIn: parent
                            width: 12
                            height: 12
                            Rectangle {
                                width: 12
                                height: 1.5
                                radius: 1
                                anchors.centerIn: parent
                                color: "#D6E2EC"
                                rotation: 45
                            }
                            Rectangle {
                                width: 12
                                height: 1.5
                                radius: 1
                                anchors.centerIn: parent
                                color: "#D6E2EC"
                                rotation: -45
                            }
                        }
                        MouseArea {
                            id: closeMa
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                console.log("panel 关闭按钮 -> hide_panel")
                                controller.hide_panel()
                            }
                        }
                    }
                }

                // ---------------- 分类 ----------------
                CategoryChips {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 38
                    compact: true
                }

                // ---------------- 图标网格 ----------------
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    GridView {
                        id: grid2
                        anchors.fill: parent
                        cellWidth: win.cardCellW
                        cellHeight: win.cardCellH
                        clip: true
                        model: appModel
                        currentIndex: count > 0 ? 0 : -1
                        keyNavigationEnabled: false
                        boundsBehavior: Flickable.StopAtBounds
                        flickDeceleration: 2400

                        ScrollBar.vertical: ScrollBar {
                            policy: ScrollBar.AsNeeded
                            width: 6
                            contentItem: Rectangle {
                                radius: 3
                                color: "#44FFFFFF"
                                implicitWidth: 6
                            }
                        }

                        delegate: EntryDelegate {
                            width: grid2.cellWidth
                            height: grid2.cellHeight
                            iconSize: win.cardIcon
                            entryId: model.entryId
                            name: model.name
                            iconPath: model.iconPath
                            focused: GridView.isCurrentItem
                            dragging: win.dragId === model.entryId
                            onActivated: controller.launchById(model.entryId)
                            onContextRequested: (mx, my) => entryMenu.showFor(model.entryId, mx, my)
                            onDragRequested: (gx, gy) => win.beginDrag(model.entryId, index, gx, gy, grid2)
                            onDragMoved: (gx, gy) => win.dragTo(gx, gy)
                            onDragReleased: win.endDrag(true)
                        }
                    }

                    Text {
                        anchors.centerIn: parent
                        visible: grid2.count === 0
                        text: controller.query ? "没有匹配的项目" : "正在扫描…"
                        color: "#8A98A5"
                        font.family: "Microsoft YaHei UI"
                        font.pixelSize: 14
                    }
                }

                // ---------------- 底栏：数量 + 图标大小 ----------------
                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 24

                    Text {
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        text: controller.query
                              ? "匹配 " + controller.resultCount + " 项"
                              : "共 " + controller.resultCount + " 项"
                        color: "#8C9AA7"
                        font.family: "Microsoft YaHei UI"
                        font.pixelSize: 12
                    }

                    Row {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 10

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "图标"
                            color: "#8C9AA7"
                            font.family: "Microsoft YaHei UI"
                            font.pixelSize: 12
                        }

                        Item {
                            id: cardSlider
                            anchors.verticalCenter: parent.verticalCenter
                            width: 124
                            height: 20

                            // 滑块位置自己维护，拖动时始终跟手；真正去改图标尺寸
                            // 走 55ms 节流 —— 每帧都改会让整个网格重排一次，
                            // 拖动起来就是一卡一卡的。
                            property real v: 0.273   // cardScale = 1.0 时的位置

                            Timer {
                                id: applyTimer
                                interval: 55
                                onTriggered: win.cardScale = 0.85 + cardSlider.v * 0.55
                            }

                            Rectangle {
                                id: track
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width
                                height: 4
                                radius: 2
                                color: "#22FFFFFF"
                            }

                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: Math.max(4, cardSlider.v * track.width)
                                height: 4
                                radius: 2
                                color: "#B4CEE2"
                            }

                            Rectangle {
                                width: 13
                                height: 13
                                radius: 6.5
                                color: "#F2F8FC"
                                anchors.verticalCenter: parent.verticalCenter
                                x: Math.max(0, Math.min(track.width - width,
                                                         cardSlider.v * track.width - width / 2))
                            }

                            MouseArea {
                                anchors.fill: parent
                                anchors.topMargin: -8
                                anchors.bottomMargin: -8
                                cursorShape: Qt.PointingHandCursor
                                function apply(mx) {
                                    cardSlider.v = Math.max(0, Math.min(1, mx / cardSlider.width));
                                    applyTimer.restart();
                                }
                                onPressed: function(m) { apply(m.x); }
                                onPositionChanged: function(m) { if (pressed) apply(m.x); }
                                onReleased: function(m) {
                                    applyTimer.stop();
                                    win.cardScale = 0.85 + cardSlider.v * 0.55;
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // ======================================================= 右键菜单
    EntryMenu {
        id: entryMenu
    }

    // 兜底：整个应用失活（用户点桌面、切到别的程序、点任务栏）时，
    // 菜单必须跟着消失。菜单是独立窗口，主窗口 hide() 带不走它，
    // 而 panelDeactivated 又因为"焦点还在本进程"被忽略 —— 就是这个组合
    // 让菜单挂在那儿关不掉。这里用应用级 active 判断，点菜单本身不会误关
    // （那时应用仍处于激活状态）。
    Connections {
        target: Qt.application
        function onActiveChanged() {
            if (!Qt.application.active)
                entryMenu.close();
        }
    }

    // ======================================================= 显隐
    // 卡片模式不再铺满屏幕，也就没有"点卡片外面"这块区域了。
    // 改由焦点判断：焦点跑到别的进程（点了桌面或别的应用）就自动收起。
    // 焦点还在本进程（打开设置、点胶囊）时不收，否则刚点开设置面板就没了。
    onActiveChanged: {
        console.log("panel onActiveChanged", active)
        if (!active && controller.panelVisible && !win.awaitingReveal
                && Date.now() - win.shownAt > 800) {
            controller.panelDeactivated()
        }
    }

    // ---- 首帧防护 ----
    // show 之后第一帧可能很慢（图标解码、着色器编译），这期间窗口是未就绪的。
    // 弹出动画不立即播，而是等第二帧交换完成（内容真的画出来了）再从胶囊弹出；
    // 未就绪窗口的底色已在 Python 侧设成黑色，在深色壁纸上看着像一次淡入。
    property bool awaitingReveal: false
    property double shownAt: 0
    property int revealFrames: 0

    onFrameSwapped: {
        if (!awaitingReveal)
            return;
        revealFrames += 1;
        if (revealFrames >= 2) {
            console.log("内容就绪，播弹出动画");
            awaitingReveal = false;
            win.progress = 1;
        }
    }

    // frameSwapped 万一不来，1.2s 后兜底，动画不至于永远不播
    Timer {
        id: revealFallback
        interval: 1200
        onTriggered: {
            if (win.awaitingReveal) {
                console.log("frameSwapped 超时，兜底播放动画");
                win.awaitingReveal = false;
                win.progress = 1;
            }
        }
    }

    Connections {
        target: controller
        function onCategoryChanged() {
            grid.currentIndex = grid.count > 0 ? 0 : -1;
        }
        function onViewModeChanged() {
            // 卡片模式要露出真实壁纸，关掉 DWM 亚克力；全屏模式再打开
            controller.applyEffects(win, win.isLaunchpad ? 3 : 1);
        }
        // Python 侧清查询（唤出面板、切分类）时把输入框也清掉。
        // 不用 text: controller.query 绑定 —— 用户一敲键盘那个绑定就断了，
        // 之后再也同步不回来。
        function onQueryChanged() {
            if (search.text !== controller.query)
                search.text = controller.query;
            if (search2.text !== controller.query)
                search2.text = controller.query;
        }
        function onPanelVisibleChanged() {
            console.log("onPanelVisibleChanged", controller.panelVisible)
            if (controller.panelVisible) {
                // 先把进度归零（不打动画），等窗口真正显示后再启动入场
                progressBehavior.enabled = false;
                win.progress = 0;
                progressBehavior.enabled = true;
                win.revealFrames = 0;
                win.awaitingReveal = true;
                win.shownAt = Date.now();
                win.show();
                win.requestActivate();
                revealFallback.restart();
                if (win.isLaunchpad)
                    search.forceActiveFocus();
                else
                    search2.forceActiveFocus();
            } else {
                win.awaitingReveal = false;
                // 菜单是独立窗口，主窗口 hide 不带走它：先关菜单再收面板，
                // 否则面板没了、右键菜单还挂在屏幕上
                entryMenu.close();
                win.hide();
            }
        }
    }

    // 面板一显示就把网格几何报出来（写日志），自动化测试/排查时不用再猜坐标。
    Timer {
        id: geoReport
        interval: 80
        repeat: false
        onTriggered: {
            function report(tag, g) {
                if (!g || g.count <= 0)
                    return;
                var o = g.mapToGlobal(0, 0);
                controller.debugLog("GRID " + tag
                    + " ox=" + Math.round(o.x) + " oy=" + Math.round(o.y)
                    + " cell=" + Math.round(g.cellWidth) + "x" + Math.round(g.cellHeight)
                    + " size=" + Math.round(g.width) + "x" + Math.round(g.height)
                    + " cont=" + Math.round(g.contentX) + "," + Math.round(g.contentY)
                    + " count=" + g.count);
            }
            report("grid1", grid);
            report("grid2", grid2);
        }
    }

    onVisibleChanged: {
        console.log("panel onVisibleChanged", visible)
        if (visible)
            geoReport.restart()
        // 预热时窗口会被静默 show 一次（panelVisible 仍为 false），
        // 那种情况不许抢焦点、不许重置界面
        if (visible && controller.panelVisible) {
            if (win.isLaunchpad)
                search.forceActiveFocus();
            else
                search2.forceActiveFocus();
            controller.setQuery("");
        }
        if (!visible)
            win.endDrag(false);
    }

    // ======================================================= 拖拽排序
    // 左键长按条目进入拖拽，指针底下是第几格就插到第几格。
    // 顺序交给 controller 落盘（config.order），下次打开还在原处。
    // 拖动过程中**不动模型**，只把"要放到第几格"记在 dragIndex 里，松手
    // 才真正落位。早先是边拖边 moveEntry，结果一移动 model 行，Qt 就把
    // 那个 delegate 重排了，正在抓鼠标的 MouseArea 随之销毁 —— 后面的
    // 移动事件全丢，拖到天边也只挪一格。落点改用虚线框提示。
    property string dragId: ""
    property int dragFrom: -1
    property int dragIndex: -1
    property var dragGrid: null
    readonly property bool dragging: dragId !== ""

    function beginDrag(id, index, gx, gy, g) {
        // 搜索结果是临时视图，拖出来的顺序没有意义
        if (controller.query)
            return;
        dragId = id;
        dragFrom = index;
        dragIndex = index;
        dragGrid = g;
        dragTo(gx, gy);
    }

    function dragTo(gx, gy) {
        if (dragGrid === null || dragId === "")
            return;

        // 浮层跟着指针，略微上抬，别被手指/光标压住
        var gp = win.contentItem.mapFromGlobal(gx, gy);
        dragGhost.x = gp.x - dragGhost.width / 2;
        dragGhost.y = gp.y - dragGhost.height / 2 - 8;

        // 用 contentItem 换算：它的坐标系就是"内容坐标"，滚动量已经算在里面。
        // 早先拿 grid.mapFromGlobal 再自己加 contentX/contentY，滚动过之后
        // 会多算一次偏移，落点整个错行。
        var cw = dragGrid.cellWidth;
        var ch = dragGrid.cellHeight;
        var cols = Math.max(1, Math.floor(dragGrid.width / cw));
        var p = dragGrid.contentItem.mapFromGlobal(gx, gy);
        var col = Math.floor(p.x / cw);
        var row = Math.floor(p.y / ch);
        var idx = row * cols + col;
        if (col >= 0 && col < cols && idx >= 0 && idx < dragGrid.count)
            dragIndex = idx;
        else if (idx >= dragGrid.count && dragGrid.count > 0)
            dragIndex = dragGrid.count - 1;   // 拖到末尾空白：插到最后
    }

    function endDrag(applyMove) {
        var id = dragId;
        var to = dragIndex;
        var from = dragFrom;
        dragId = "";
        dragFrom = -1;
        dragIndex = -1;
        dragGrid = null;
        // 面板被动收起、Esc 之类不该改顺序，只有正常松手才落位
        if (applyMove !== false && id !== "" && to >= 0 && to !== from)
            controller.moveEntry(id, to);
    }

    // 落点提示框：告诉用户"松手会插到这儿"
    Rectangle {
        id: dropMark
        readonly property real cw: win.dragGrid ? win.dragGrid.cellWidth : 0
        readonly property real ch: win.dragGrid ? win.dragGrid.cellHeight : 0
        readonly property int cols: cw > 0 ? Math.max(1, Math.round(win.dragGrid.width / cw)) : 1
        // 映射到窗口根坐标系，和 dragGhost 用的是同一套坐标
        readonly property real gx0: win.dragGrid ? (win.dragGrid.mapToItem(null, 0, 0).x) : 0
        readonly property real gy0: win.dragGrid ? (win.dragGrid.mapToItem(null, 0, 0).y) : 0

        visible: win.dragging && win.dragIndex >= 0 && win.dragIndex !== win.dragFrom
        z: 8
        width: Math.max(0, cw - 8)
        height: Math.max(0, ch - 8)
        radius: 17
        color: "#1AFFFFFF"
        border.width: 2
        border.color: "#8C5AA9FF"

        x: {
            if (!win.dragGrid || cols <= 0)
                return 0;
            var col = win.dragIndex % cols;
            return win.dragGrid.contentItem.mapToItem(null, col * cw, 0).x + 4;
        }
        y: {
            if (!win.dragGrid || cols <= 0)
                return 0;
            var row = Math.floor(win.dragIndex / cols);
            return win.dragGrid.contentItem.mapToItem(null, 0, row * ch).y + 4;
        }

        Behavior on x { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
        Behavior on y { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
    }

    // 拖着走的那一格：和被拖的原位（半透明）呼应，抬起来 + 放大的手感
    Item {
        id: dragGhost
        width: 96
        height: 96 + 26
        visible: win.dragging
        opacity: visible ? 1 : 0
        z: 999
        scale: win.dragging ? 1.12 : 0.9
        transformOrigin: Item.Center

        Behavior on opacity { NumberAnimation { duration: 90 } }
        Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }

        // 直接按 id 问模型要，比在 delegate 之间传引用可靠
        property string name: win.dragging ? rawModel.nameOf(win.dragId) : ""
        property string iconPath: win.dragging ? rawModel.iconOf(win.dragId) : ""

        Rectangle {
            anchors.fill: parent
            anchors.margins: 2
            radius: 16
            color: "#2EFFFFFF"
            border.width: 1
            border.color: "#57FFFFFF"
        }

        Item {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.topMargin: 10
            width: 72
            height: 72

            Rectangle {
                anchors.fill: parent
                radius: 17
                visible: ghostIcon.status !== Image.Ready
                color: "#33465A"
                Text {
                    anchors.centerIn: parent
                    text: dragGhost.name.length > 0 ? dragGhost.name.charAt(0) : "?"
                    color: "#E6F0F8"
                    font.family: "Microsoft YaHei UI"
                    font.pixelSize: 30
                }
            }

            Image {
                id: ghostIcon
                anchors.fill: parent
                sourceSize.width: 160
                sourceSize.height: 160
                fillMode: Image.PreserveAspectFit
                asynchronous: false
                cache: true
                smooth: true
                source: dragGhost.iconPath ? "file:///" + dragGhost.iconPath : ""
                visible: status === Image.Ready
            }
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 6
            width: parent.width - 10
            text: dragGhost.name
            color: "#F2F7FB"
            font.family: "Microsoft YaHei UI"
            font.pixelSize: 12
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
            maximumLineCount: 1
            style: Text.Outline
            styleColor: "#80222A33"
        }
    }
}
