import QtQuick 2.15
import QtQuick.Window 2.15
import QtGraphicalEffects 1.15

Window {
    width: 200; height: 120; visible: true
    Rectangle { id: r; width: 60; height: 60; color: "#4DA6FF" }
    DropShadow { anchors.fill: r; source: r; radius: 8; samples: 12; color: "#88000000" }
    FastBlur { anchors.fill: r; source: r; radius: 6 }
    RadialGradient { width: 100; height: 100; gradient: Gradient { GradientStop { position: 0; color: "#ff0000" } GradientStop { position: 1; color: "#0000ff" } } }
}
