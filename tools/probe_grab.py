"""验证 QScreen.grabWindow(0) 在本机到底抓到什么。"""

from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QApplication

APP = QApplication([])
scr = QGuiApplication.primaryScreen()
OUT = r"C:\Users\15549\WorkBuddy\desk-space"


def stats(img, tag):
    if img.isNull():
        return f"{tag}: NULL 图像"
    small = img.scaled(64, 40)
    tot = 0.0
    for y in range(40):
        for x in range(64):
            c = small.pixelColor(x, y)
            tot += (c.red() + c.green() + c.blue()) / 3.0
    return (f"{tag}: {img.width()}x{img.height()} 平均亮度={tot / 2560:.1f}")


lines = []
shot = scr.grabWindow(0)
lines.append(stats(shot.toImage(), "grabWindow(0)"))
shot.toImage().scaled(320, 200).save(OUT + "/probe_grab.png")

try:
    img = scr.grabWindow(0).toImage()
    lines.append(stats(img, "第二次"))
except Exception as exc:
    lines.append(f"异常 {exc}")

# 壁纸文件
import os
cands = [
    os.path.join(os.environ.get("APPDATA", ""),
                 r"Microsoft\Windows\Themes\TranscodedWallpaper"),
]
try:
    import winreg
    with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as k:
        p, _ = winreg.QueryValueEx(k, "WallPaper")
        if p:
            cands.append(p)
except OSError:
    pass
from PyQt5.QtGui import QImage
for p in cands:
    if p and os.path.isfile(p):
        lines.append(f"壁纸文件: {p}")
        lines.append(stats(QImage(p), "  载入"))

with open(OUT + "/probe_grab.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
