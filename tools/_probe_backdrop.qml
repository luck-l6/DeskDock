
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
        source: "C:/Users/15549/WorkBuddy/desk-space/deskdock/qml/assets/noise.png"
        fillMode: Image.Tile
        opacity: 0.5
    }
    Component.onCompleted: console.log("LOADED", Source.status)
}
