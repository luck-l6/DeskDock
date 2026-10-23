"""生成界面用的两张底层贴图：接地阴影与颗粒噪点。

做成图片而不是 QML 实时效果，是为了零运行时开销：
所有图标代理共用同一张纹理，只占一份显存。
"""

from __future__ import annotations

import random
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QImage

OUT = Path(__file__).resolve().parent.parent / "deskdock" / "qml" / "assets"
OUT.mkdir(parents=True, exist_ok=True)


def make_shadow(size: int = 160) -> None:
    """柔和的椭圆暗斑，压在图标底下当接地阴影。"""
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    cx = cy = size / 2.0
    rx, ry = size / 2.0, size / 2.0 * 0.66
    for y in range(size):
        for x in range(size):
            dx = (x - cx) / rx
            dy = (y - cy) / ry
            d = (dx * dx + dy * dy) ** 0.5
            if d >= 1.0:
                continue
            a = (1.0 - d) ** 2.4
            img.setPixelColor(x, y, QColor(0, 0, 0, int(a * 168)))
    path = OUT / "shadow.png"
    img.save(str(path), "PNG")
    print("shadow ->", path)


def make_noise(size: int = 160) -> None:
    """细颗粒噪点，铺在最上层消掉色带、给出材质感。"""
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    random.seed(20261022)
    for y in range(size):
        for x in range(size):
            v = random.randint(0, 255)
            a = random.randint(0, 26)
            img.setPixelColor(x, y, QColor(v, v, v, a))
    path = OUT / "noise.png"
    img.save(str(path), "PNG")
    print("noise  ->", path)


if __name__ == "__main__":
    make_shadow()
    make_noise()
