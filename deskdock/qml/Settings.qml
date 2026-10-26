import QtQuick 2.15
import QtQuick.Window 2.15

// 设置界面。
// 不用 Qt Quick Controls 的默认控件：那套 Material Dark 是灰底方块 + 原生
// 边框，跟主界面的玻璃质感完全不是一回事。这里全部自己画：开关、选项卡、
// 药丸、分区卡片，风格与主面板统一。
Window {
    id: win
    title: "DeskDock 设置"
    width: 580
    height: 742
    minimumWidth: 520
    minimumHeight: 600
    visible: false
    color: "#141920"

    Component.onCompleted: controller.registerSettings(win)

    // -------------------------------------------------- 自绘控件
    component Switch: Item {
        id: sw
        property bool checked: false
        width: 44
        height: 24

        Rectangle {
            anchors.fill: parent
            radius: height / 2
            color: sw.checked ? "#2E7FD1" : "#242C34"
            border.width: 1
            border.color: sw.checked ? "#63AEEA" : "#39424C"
            Behavior on color { ColorAnimation { duration: 150 } }
            Behavior on border.color { ColorAnimation { duration: 150 } }
        }

        Rectangle {
            width: 18
            height: 18
            radius: 9
            color: "#F2F7FB"
            anchors.verticalCenter: parent.verticalCenter
            x: sw.checked ? parent.width - width - 3 : 3
            Behavior on x { NumberAnimation { duration: 170; easing.type: Easing.OutCubic } }
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                sw.checked = !sw.checked;
                sw.toggled(sw.checked);
            }
        }

        signal toggled(bool value)
    }

    // 一行：左边说明，右边开关
    component SwitchRow: Item {
        id: srow
        property string label: ""
        property bool checked: false
        width: parent.width
        height: 34

        Text {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: srow.label
            color: "#CBD6E0"
            font.family: "Microsoft YaHei UI"
            font.pixelSize: 13
        }

        Switch {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            checked: srow.checked
            onToggled: srow.toggled(value)
        }

        signal toggled(bool value)
    }

    // 数值档位行：Dock 图标大小这种"调一下看看"的参数，−/+ 比滑块更省地方，
    // 也不用引 Qt Quick Controls（这一整个界面都是自绘的）
    component StepRow: Item {
        id: strow
        property string label: ""
        property int value: 48
        property int step: 4
        property int low: 28
        property int high: 64
        width: parent.width
        height: 34
        // 信号参数叫 newValue 而不是 value：后者会和本组件的 value 属性撞名，
        // 处理器里到底指哪个容易出错
        signal changed(int newValue)

        Text {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: strow.label
            color: "#CBD6E0"
            font.family: "Microsoft YaHei UI"
            font.pixelSize: 13
        }

        Row {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 4

            Rectangle {
                width: 30
                height: 28
                radius: 8
                color: minusMa.containsMouse ? "#1AFFFFFF" : "#0FFFFFFF"
                border.width: 1
                border.color: "#2B333C"
                opacity: strow.value > strow.low ? 1.0 : 0.35

                Text {
                    anchors.centerIn: parent
                    text: "−"
                    color: "#EAF1F7"
                    font.family: "Microsoft YaHei UI"
                    font.pixelSize: 16
                }

                MouseArea {
                    id: minusMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    enabled: strow.value > strow.low
                    onClicked: strow.changed(Math.max(strow.low, strow.value - strow.step))
                }
            }

            Text {
                width: 46
                height: 28
                anchors.verticalCenter: parent.verticalCenter
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                text: strow.value + " px"
                color: "#EAF1F7"
                font.family: "Microsoft YaHei UI"
                font.pixelSize: 13
            }

            Rectangle {
                width: 30
                height: 28
                radius: 8
                color: plusMa.containsMouse ? "#1AFFFFFF" : "#0FFFFFFF"
                border.width: 1
                border.color: "#2B333C"
                opacity: strow.value < strow.high ? 1.0 : 0.35

                Text {
                    anchors.centerIn: parent
                    text: "+"
                    color: "#EAF1F7"
                    font.family: "Microsoft YaHei UI"
                    font.pixelSize: 15
                }

                MouseArea {
                    id: plusMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    enabled: strow.value < strow.high
                    onClicked: strow.changed(Math.min(strow.high, strow.value + strow.step))
                }
            }
        }
    }

    // 小药丸：二选一用
    component Pill: Rectangle {
        id: pill
        property string label: ""
        property bool on: false
        width: plabel.width + 26
        height: 28
        radius: 14
        color: pill.on ? "#33FFFFFF" : "#12FFFFFF"
        border.width: 1
        border.color: pill.on ? "#4AFFFFFF" : "#1AFFFFFF"
        signal clicked()

        Text {
            id: plabel
            anchors.centerIn: parent
            text: pill.label
            color: pill.on ? "#FFFFFF" : "#98A6B4"
            font.family: "Microsoft YaHei UI"
            font.pixelSize: 12
            font.weight: pill.on ? Font.DemiBold : Font.Normal
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: pill.clicked()
        }

        Behavior on color { ColorAnimation { duration: 150 } }
        Behavior on border.color { ColorAnimation { duration: 150 } }
    }

    component Btn: Rectangle {
        id: btn
        property string label: ""
        width: blabel.width + 30
        height: 32
        radius: 9
        color: bma.containsMouse ? "#28FFFFFF" : "#15FFFFFF"
        border.width: 1
        border.color: bma.containsMouse ? "#40FFFFFF" : "#20FFFFFF"
        signal clicked()

        Text {
            id: blabel
            anchors.centerIn: parent
            text: btn.label
            color: "#DCE5ED"
            font.family: "Microsoft YaHei UI"
            font.pixelSize: 13
        }

        MouseArea {
            id: bma
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: btn.clicked()
        }

        Behavior on color { ColorAnimation { duration: 140 } }
    }

    // -------------------------------------------------- 背景
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#1A2029" }
            GradientStop { position: 0.55; color: "#141920" }
            GradientStop { position: 1.0; color: "#0F141A" }
        }
    }

    // 顶部一抹冷光，跟面板同源
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 180
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#124A6E96" }
            GradientStop { position: 1.0; color: "#00000000" }
        }
    }

    // -------------------------------------------------- 内容
    Flickable {
        anchors.fill: parent
        contentHeight: body.height + 40
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: body
            x: 24
            y: 22
            width: win.width - 48
            spacing: 14

            // ---- 标题 ----
            Column {
                spacing: 3
                Text {
                    text: "DeskDock"
                    color: "#F4F8FB"
                    font.family: "Microsoft YaHei UI"
                    font.pixelSize: 22
                    font.weight: Font.DemiBold
                }
                Text {
                    text: "让桌面只留一个入口"
                    color: "#7D8B99"
                    font.family: "Microsoft YaHei UI"
                    font.pixelSize: 13
                }
            }

            // ---- 展开方式 ----
            Rectangle {
                width: parent.width
                height: sec1.height + 28
                radius: 14
                color: "#12FFFFFF"
                border.width: 1
                border.color: "#1AFFFFFF"

                Column {
                    id: sec1
                    x: 16
                    y: 14
                    width: parent.width - 32
                    spacing: 11

                    Text {
                        text: "展开方式"
                        color: "#93A2B0"
                        font.family: "Microsoft YaHei UI"
                        font.pixelSize: 12
                    }

                    Row {
                        width: parent.width
                        spacing: 10

                        Repeater {
                            model: [
                                {
                                    key: "launchpad",
                                    title: "全屏 Launchpad",
                                    desc: "铺满整个屏幕，图标大"
                                },
                                {
                                    key: "grid",
                                    title: "居中卡片面板",
                                    desc: "悬浮小卡片，不挡桌面"
                                }
                            ]

                            delegate: Rectangle {
                                width: (parent.width - 10) / 2
                                height: 68
                                radius: 11
                                readonly property bool on: controller.viewMode === modelData.key
                                color: on ? "#1E6FA8DC" : "#0DFFFFFF"
                                border.width: 1
                                border.color: on ? "#6FB4EE" : "#1CFFFFFF"

                                Column {
                                    anchors.left: parent.left
                                    anchors.leftMargin: 13
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 4
                                    Text {
                                        text: modelData.title
                                        color: on ? "#FFFFFF" : "#C6D2DD"
                                        font.family: "Microsoft YaHei UI"
                                        font.pixelSize: 14
                                        font.weight: on ? Font.DemiBold : Font.Normal
                                    }
                                    Text {
                                        text: modelData.desc
                                        color: on ? "#C9E2F6" : "#7E8C9A"
                                        font.family: "Microsoft YaHei UI"
                                        font.pixelSize: 12
                                    }
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: controller.setViewMode(modelData.key)
                                }

                                Behavior on color { ColorAnimation { duration: 160 } }
                                Behavior on border.color { ColorAnimation { duration: 160 } }
                            }
                        }
                    }

                    Row {
                        width: parent.width
                        spacing: 10
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "排序"
                            color: "#C3CDD6"
                            font.family: "Microsoft YaHei UI"
                            font.pixelSize: 13
                        }
                        Pill {
                            anchors.verticalCenter: parent.verticalCenter
                            label: "按使用频率"
                            on: controller.sortBy === "frequency"
                            onClicked: controller.setSortBy("frequency")
                        }
                        Pill {
                            anchors.verticalCenter: parent.verticalCenter
                            label: "按名称"
                            on: controller.sortBy === "name"
                            onClicked: controller.setSortBy("name")
                        }
                        Pill {
                            anchors.verticalCenter: parent.verticalCenter
                            label: "手动拖拽"
                            on: controller.sortBy === "manual"
                            onClicked: controller.setSortBy("manual")
                        }
                    }
                }
            }

            // ---- 收纳范围 ----
            Rectangle {
                width: parent.width
                height: sec2.height + 28
                radius: 14
                color: "#12FFFFFF"
                border.width: 1
                border.color: "#1AFFFFFF"

                Column {
                    id: sec2
                    x: 16
                    y: 14
                    width: parent.width - 32
                    spacing: 4

                    Text {
                        text: "收纳范围"
                        color: "#93A2B0"
                        font.family: "Microsoft YaHei UI"
                        font.pixelSize: 12
                    }

                    SwitchRow {
                        label: "开始菜单中的应用"
                        checked: controller.sourceStartMenu
                        onToggled: controller.setSourceStartMenu(value)
                    }
                    SwitchRow {
                        label: "公共开始菜单（Chrome / Office / JetBrains 等）"
                        checked: controller.sourceCommonStartMenu
                        onToggled: controller.setSourceCommonStartMenu(value)
                    }
                    SwitchRow {
                        label: "藏起控制台程序（Python 解释器、命令行工具）"
                        checked: controller.hideConsoleApps
                        onToggled: controller.setHideConsoleApps(value)
                    }
                    SwitchRow {
                        label: "桌面上的文件"
                        checked: controller.includeFiles
                        onToggled: controller.setIncludeFiles(value)
                    }
                    SwitchRow {
                        label: "桌面上的文件夹"
                        checked: controller.includeFolders
                        onToggled: controller.setIncludeFolders(value)
                    }
                    SwitchRow {
                        label: "隐藏卸载程序与帮助文档"
                        checked: controller.hideUninstallers
                        onToggled: controller.setHideUninstallers(value)
                    }
                }
            }

            // ---- 入口与系统 ----
            Rectangle {
                width: parent.width
                height: sec3.height + 28
                radius: 14
                color: "#12FFFFFF"
                border.width: 1
                border.color: "#1AFFFFFF"

                Column {
                    id: sec3
                    x: 16
                    y: 14
                    width: parent.width - 32
                    spacing: 4

                    Text {
                        text: "入口与系统"
                        color: "#93A2B0"
                        font.family: "Microsoft YaHei UI"
                        font.pixelSize: 12
                    }

                    Item {
                        width: parent.width
                        height: 38

                        Text {
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            text: "全局热键"
                            color: "#CBD6E0"
                            font.family: "Microsoft YaHei UI"
                            font.pixelSize: 13
                        }

                        Rectangle {
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            width: 158
                            height: 30
                            radius: 8
                            color: "#0FFFFFFF"
                            border.width: 1
                            border.color: hotkeyField.activeFocus ? "#4E90D6" : "#2B333C"

                            TextInput {
                                id: hotkeyField
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                verticalAlignment: TextInput.AlignVCenter
                                text: controller.hotkeyText
                                color: "#EAF1F7"
                                font.family: "Microsoft YaHei UI"
                                font.pixelSize: 13
                                selectByMouse: true
                                clip: true
                                onAccepted: {
                                    controller.setHotkey(text.trim());
                                    tip.text = hotkeyField.text.trim()
                                               ? "已生效：" + hotkeyField.text.trim()
                                               : "已清空热键";
                                }
                            }
                        }
                    }

                    SwitchRow {
                        label: "显示桌面胶囊入口"
                        checked: controller.capsuleVisible
                        onToggled: controller.setCapsuleVisible(value)
                    }
                    SwitchRow {
                        label: "显示底部 Dock 栏"
                        checked: controller.dockVisible
                        onToggled: controller.setDockVisible(value)
                    }
                    StepRow {
                        label: "Dock 图标大小"
                        value: controller.dockIconSize
                        // 不直接改 value，交给 Python 存盘后再由 optionsChanged 回流，
                        // 这样绑定不会被自己写断
                        onChanged: controller.setDockIconSize(newValue)
                    }
                    SwitchRow {
                        label: "胶囊平时半透明淡出"
                        checked: controller.autoHide
                        onToggled: controller.setAutoHide(value)
                    }
                    SwitchRow {
                        label: "显示系统桌面图标"
                        checked: controller.desktopIconsVisible
                        onToggled: controller.setDesktopIconsVisible(value)
                    }
                    SwitchRow {
                        label: "开机自动启动"
                        checked: controller.runAtStartup
                        onToggled: controller.setRunAtStartup(value)
                    }
                }
            }

            // ---- 底部 ----
            Row {
                width: parent.width
                spacing: 10

                Text {
                    id: tip
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - 190
                    text: ""
                    color: "#7F8C98"
                    font.family: "Microsoft YaHei UI"
                    font.pixelSize: 12
                    elide: Text.ElideRight
                }

                Btn {
                    anchors.verticalCenter: parent.verticalCenter
                    label: "恢复隐藏项"
                    onClicked: {
                        controller.unhideAll();
                        tip.text = "已恢复全部隐藏项";
                    }
                }

                Btn {
                    anchors.verticalCenter: parent.verticalCenter
                    label: "重新扫描"
                    onClicked: {
                        controller.refresh();
                        tip.text = "已重新扫描";
                    }
                }
            }
        }
    }
}
