import QtQuick 2.15
import QtQuick.Controls 2.15

Item {
    id: root

    property string currentId: ""

    function showFor(entryId, mx, my) {
        root.currentId = entryId;
        menu.popup();
    }

    // 面板收起时必须由外面主动关掉：菜单是一个独立窗口，主窗口 hide() 不会
    // 带走它，于是"面板没了、菜单还挂在屏幕上"——就是这个 bug 的来源。
    function close() {
        menu.close();
    }

    Menu {
        id: menu
        width: 196
        padding: 6
        margins: 10
        // 默认策略够用，但写出来：点外面 / 松手在外面 / Esc 都要关
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
                     | Popup.CloseOnReleaseOutside
        modal: true
        dim: false

        palette.window: "#F2171D24"
        palette.windowText: "#DCE6EE"
        palette.buttonText: "#DCE6EE"
        palette.text: "#DCE6EE"
        palette.highlight: "#264A6E96"
        palette.highlightedText: "#FFFFFF"
        palette.mid: "#26FFFFFF"
        palette.dark: "#26FFFFFF"

        background: Rectangle {
            radius: 13
            color: "#F2171D24"
            border.width: 1
            border.color: "#2BFFFFFF"

            // 顶部玻璃反光
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 1
                height: parent.height * 0.5
                radius: 12
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "#10FFFFFF" }
                    GradientStop { position: 1.0; color: "#00FFFFFF" }
                }
            }
        }

        MenuItem {
            text: "打开"
            onTriggered: controller.launchById(root.currentId)
        }
        MenuItem {
            text: root.currentId && controller.isPinned(root.currentId) ? "取消置顶" : "置顶"
            onTriggered: controller.togglePin(root.currentId)
        }
        MenuItem {
            // 在 Dock 上的显示"移出"，否则"放进"——自动填的那批也算"在"，
            // 所以移出对自动模式同样有效（里面会先固化成手动列表）
            text: root.currentId && controller.isDockItem(root.currentId)
                  ? "从 Dock 移除" : "放进 Dock"
            onTriggered: controller.toggleDock(root.currentId)
        }
        MenuSeparator {}
        MenuItem {
            text: "在资源管理器中显示"
            onTriggered: controller.reveal(root.currentId)
        }
        MenuItem {
            text: "从列表隐藏"
            onTriggered: controller.hideEntry(root.currentId)
        }
    }
}
