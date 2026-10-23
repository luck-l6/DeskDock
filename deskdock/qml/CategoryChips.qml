import QtQuick 2.15

// 分段式分类控件。
// 整条是一块玻璃轨道，选中项是里面一块会滑动过去的高亮 —— 比四个各自独立的
// 药丸整齐得多，切换时也有明确的"滑块移动"反馈。
Item {
    id: root

    property bool compact: false
    property bool showCounts: true

    readonly property int chipH: compact ? 34 : 40
    readonly property int fontSize: compact ? 13 : 14

    implicitWidth: row.width
    implicitHeight: chipH

    // 打字的时候过滤不看分类（搜索是全库的），这条就只是"当前视角"的提示，
    // 不该再顶着高亮误导人 —— 整条淡下去，高亮块收掉。
    readonly property bool muted: appModel.searching
    opacity: muted ? 0.42 : 1.0
    Behavior on opacity { NumberAnimation { duration: 160 } }

    // 高亮块跟随当前选中项
    property real indX: 0
    property real indW: 0

    function syncIndicator() {
        for (var i = 0; i < rep.count; i++) {
            var it = rep.itemAt(i);
            if (it && it.active) {
                // it.x 是相对 Row 的坐标，而高亮块画在 root 坐标系里。
                // Row 是居中的，直接用 it.x 会让整块偏掉 Row 的左边距——
                // 表现就是白色胶囊停在选中项文字的旁边、看着像没对上。
                root.indX = row.x + it.x;
                root.indW = it.width;
                return;
            }
        }
    }

    function iconFor(key) {
        if (key === "recent")
            return icRecent;
        if (key === "app")
            return icApp;
        if (key === "file")
            return icFile;
        if (key === "folder")
            return icFolder;
        return icAll;
    }

    Component.onCompleted: Qt.callLater(root.syncIndicator)

    Connections {
        target: controller
        function onCategoryChanged() { root.syncIndicator(); }
        // 计数变化会让每项的宽度变（数字位数不同），高亮块要跟着重算
        function onCategoryCountsChanged() { Qt.callLater(root.syncIndicator); }
    }

    // ---------------- 轨道 ----------------
    Rectangle {
        id: track
        anchors.centerIn: row
        width: row.width
        height: row.height
        radius: height / 2
        color: "#0CFFFFFF"
        border.width: 1
        border.color: "#1CFFFFFF"
    }

    // ---------------- 滑动高亮 ----------------
    Rectangle {
        id: ind
        x: root.indX + 3
        y: 3
        width: Math.max(0, root.indW - 6)
        height: root.chipH - 6
        radius: height / 2
        visible: root.indW > 0 && !root.muted

        gradient: Gradient {
            GradientStop { position: 0.0; color: "#46FFFFFF" }
            GradientStop { position: 1.0; color: "#26FFFFFF" }
        }

        Behavior on x { NumberAnimation { duration: 230; easing.type: Easing.OutCubic } }
        Behavior on width { NumberAnimation { duration: 230; easing.type: Easing.OutCubic } }
    }

    // ---------------- 分段 ----------------
    Row {
        id: row
        anchors.centerIn: parent
        spacing: 0
        height: root.chipH
        onWidthChanged: Qt.callLater(root.syncIndicator)

        Repeater {
            id: rep
            onItemAdded: Qt.callLater(root.syncIndicator)
            model: [
                { key: "all",    label: "全部",   count: -1 },
                { key: "recent", label: "常用",   count: controller.countRecent },
                { key: "app",    label: "应用",   count: controller.countApp },
                { key: "file",   label: "文件",   count: controller.countFile },
                { key: "folder", label: "文件夹", count: controller.countFolder }
            ]

            delegate: Item {
                id: chip
                readonly property bool active: !root.muted && controller.category === modelData.key
                width: inner.width + (root.compact ? 28 : 34)
                height: root.chipH

                Row {
                    id: inner
                    anchors.centerIn: parent
                    spacing: root.compact ? 6 : 7

                    Loader {
                        id: ld
                        anchors.verticalCenter: parent.verticalCenter
                        width: 11
                        height: 11
                        sourceComponent: root.iconFor(modelData.key)
                        onLoaded: ld.item.tint = Qt.binding(function () {
                            return chip.active ? "#FFFFFF" : "#8CA0B2";
                        })
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.label
                        color: chip.active ? "#FFFFFF" : "#A2B2C0"
                        font.family: "Microsoft YaHei UI"
                        font.pixelSize: root.fontSize
                        font.weight: chip.active ? Font.DemiBold : Font.Normal
                        Behavior on color { ColorAnimation { duration: 180 } }
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: root.showCounts && modelData.count >= 0
                        text: modelData.count
                        color: chip.active ? "#DCE7F0" : "#7C8C9B"
                        font.family: "Microsoft YaHei UI"
                        font.pixelSize: root.fontSize - 3
                        font.weight: Font.Medium
                        Behavior on color { ColorAnimation { duration: 180 } }
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: controller.setCategory(modelData.key)
                }
            }
        }
    }

    // ---------------- 小图标 ----------------
    Component {
        id: icRecent
        Item {
            property color tint: "#FFFFFF"
            // 时钟：圆 + 时针分针
            Rectangle {
                width: 11
                height: 11
                radius: 5.5
                color: "transparent"
                border.width: 1.5
                border.color: tint
            }
            Rectangle {
                x: 4.7
                y: 2.2
                width: 1.6
                height: 3.6
                radius: 0.8
                color: tint
            }
            Rectangle {
                x: 5.5
                y: 4.7
                width: 3.2
                height: 1.6
                radius: 0.8
                color: tint
            }
        }
    }

    Component {
        id: icAll
        Item {
            property color tint: "#FFFFFF"
            Grid {
                columns: 2
                rows: 2
                spacing: 2.4
                Repeater {
                    model: 4
                    Rectangle { width: 4.3; height: 4.3; radius: 1.3; color: tint }
                }
            }
        }
    }

    Component {
        id: icApp
        Item {
            property color tint: "#FFFFFF"
            Rectangle {
                width: 11
                height: 11
                radius: 3.4
                color: "transparent"
                border.width: 1.6
                border.color: tint
            }
        }
    }

    Component {
        id: icFile
        Item {
            property color tint: "#FFFFFF"
            Rectangle {
                width: 8.4
                height: 11
                radius: 1.6
                color: "transparent"
                border.width: 1.5
                border.color: tint
            }
            Rectangle {
                x: 5.2
                width: 4.2
                height: 4.2
                radius: 1
                color: tint
            }
        }
    }

    Component {
        id: icFolder
        Item {
            property color tint: "#FFFFFF"
            Rectangle {
                y: 3
                width: 11
                height: 8
                radius: 1.8
                color: "transparent"
                border.width: 1.5
                border.color: tint
            }
            Rectangle {
                width: 4.6
                height: 4.6
                radius: 1.4
                color: tint
            }
        }
    }
}
