"""把 frames/ 里的抓帧拼成一张联络表，方便一眼看出哪一帧在闪。"""

import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "frames")
CELL_W, CELL_H = 320, 200
COLS = 5


def main() -> None:
    app = QGuiApplication(sys.argv)
    names = sorted(n for n in os.listdir(SRC) if n.endswith(".png"))
    names.sort(key=lambda n: (0, "") if n.startswith("base") else (1, n))
    rows = (len(names) + COLS - 1) // COLS
    sheet = QImage(COLS * CELL_W, rows * (CELL_H + 18), QImage.Format_RGB32)
    sheet.fill(QColor(20, 20, 24))
    p = QPainter(sheet)
    f = QFont("Consolas", 11)
    p.setFont(f)
    for i, n in enumerate(names):
        img = QImage(os.path.join(SRC, n))
        small = img.scaled(CELL_W, CELL_H, Qt.IgnoreAspectRatio,
                           Qt.SmoothTransformation)
        r, c = divmod(i, COLS)
        x, y = c * CELL_W, r * (CELL_H + 18)
        p.drawImage(x, y, small)
        p.setPen(QColor(255, 230, 120))
        p.drawText(x + 4, y + CELL_H + 14, n.replace(".png", ""))
    p.end()
    out = os.path.join(SRC, "sheet.png")
    sheet.save(out, "PNG")
    print("wrote", out, sheet.width(), "x", sheet.height(), "frames:", len(names))


if __name__ == "__main__":
    main()
