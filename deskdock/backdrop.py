"""桌面背景采样：抓一帧屏幕，多级降采样后交给界面当毛玻璃底图。

为什么这么做：Qt5 的 QML 读不到窗口以外的像素，没法直接对"身后的桌面"
做模糊。折中方案是先由 QScreen 抓一帧屏，再用连续减半的平滑缩放把它压成
低频图像 —— 多次 2x2 盒式滤波串联的效果非常接近大半径高斯模糊，成本却
几乎为零。界面拿到这张小图后拉伸铺满，就是一块真的毛玻璃。
"""

from __future__ import annotations

import logging
import os

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QGuiApplication, QImage
from PyQt5.QtQuick import QQuickImageProvider

log = logging.getLogger(__name__)


class BackdropProvider(QQuickImageProvider):
    """把最近一帧桌面底图暴露成 QML 的 image://backdrop/... 资源。"""

    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.Image)
        self._image = QImage()
        self._sharp = QImage()
        self._card = QImage()
        self._full_w = 0
        self._full_h = 0

    # QML 通过 image://backdrop/shot 访问
    # PyQt5 的签名是 requestImage(id, requestedSize) -> (QImage, QSize)
    def requestImage(self, _id, _requested_size):  # noqa: N802
        sid = str(_id)

        # image://backdrop/card?x,y,w,h —— 裁出卡片正后方那块模糊壁纸。
        # 用「整屏模糊图 + 按坐标裁切」而不是单独抓一块，能保证模糊半径一致，
        # 且颜色跟卡片背后的真实画面对齐，不会出现色块错位。
        if sid.startswith("card"):
            return self._card_region(sid)

        # image://backdrop/sharp —— 清晰壁纸，给卡片模式当整屏底图
        if sid.startswith("sharp"):
            return (self._sharp, self._sharp.size())

        return (self._image, self._image.size())

    def _card_region(self, sid: str):
        try:
            _, params = sid.split("?", 1)
        except ValueError:
            return (QImage(), QSize())
        parts = params.split(",")
        if len(parts) < 4:
            return (QImage(), QSize())
        try:
            x, y, w, h = (int(float(v)) for v in parts[:4])
        except ValueError:
            return (QImage(), QSize())

        src = self._card if not self._card.isNull() else self._image
        if src.isNull() or self._full_w <= 0 or self._full_h <= 0:
            return (QImage(), QSize())

        sx = src.width() / float(self._full_w)
        sy = src.height() / float(self._full_h)
        rx = max(0, min(src.width() - 1, int(x * sx)))
        ry = max(0, min(src.height() - 1, int(y * sy)))
        rw = max(1, min(src.width() - rx, int(w * sx)))
        rh = max(1, min(src.height() - ry, int(h * sy)))
        return (src.copy(rx, ry, rw, rh), QSize(rw, rh))

    @property
    def ready(self) -> bool:
        return not self._image.isNull()

    def capture(self, screen=None, steps: int = 3) -> bool:
        """抓屏并降采样。失败时返回 False，界面会退回纯渐变底。"""
        scr = screen or QGuiApplication.primaryScreen()
        if scr is None:
            return False

        dpr = scr.devicePixelRatio() or 1.0
        screen_w = int(scr.size().width() * dpr)
        screen_h = int(scr.size().height() * dpr)

        # 主路径：抓当前屏幕。桌面现在是什么（窗口、壁纸、壁纸软件）就是什么，
        # 卡片里的模糊层和屏幕上的真实画面才能对得上。
        src = None
        try:
            shot = scr.grabWindow(0)
            src = shot.toImage()
        except Exception as exc:  # 独占全屏 / 远程桌面等场景可能失败
            log.debug("抓屏失败: %s", exc)
            src = None
        if src is None or src.isNull() or src.width() < 8 or src.height() < 8:
            # 兜底：抓不到再读壁纸文件
            src = self._load_wallpaper()
        if src is None or src.isNull() or src.width() < 8 or src.height() < 8:
            return False

        # 先按屏幕比例铺满并居中裁切（cover），保证和大屏等比
        img = src.scaled(
            max(8, screen_w), max(8, screen_h),
            Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        ox = max(0, (img.width() - screen_w) // 2)
        oy = max(0, (img.height() - screen_h) // 2)
        img = img.copy(ox, oy, min(screen_w, img.width()), min(screen_h, img.height()))
        self._sharp = img
        self._full_w = img.width()
        self._full_h = img.height()

        # 卡片用的磨砂层：降得轻一些，保留一点色彩结构，不至于糊成一片色块
        cw = max(8, img.width() // 6)
        ch = max(8, img.height() // 6)
        self._card = img.scaled(
            cw, ch, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

        # 连续减半：每级都是一次平滑下采样，串起来≈高斯
        for _ in range(max(1, steps)):
            w = max(8, img.width() // 2)
            h = max(8, img.height() // 2)
            img = img.scaled(
                w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self._image = img
        return True

    @staticmethod
    def _load_wallpaper() -> QImage | None:
        """直接读系统壁纸文件。

        比抓屏更可靠：抓屏会把当前前台窗口也拍进去，热键唤出时背景里全是不相干
        的窗口，观感很脏。壁纸永远干净，且与「桌面收纳」的语义一致。
        """
        candidates = []
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(
                os.path.join(appdata, r"Microsoft\Windows\Themes\TranscodedWallpaper"))
        try:
            import winreg

            with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as key:
                path, _ = winreg.QueryValueEx(key, "WallPaper")
                if path:
                    candidates.append(path)
        except OSError:
            pass

        for path in candidates:
            try:
                if not path or not os.path.isfile(path):
                    continue
                img = QImage(path)
                if not img.isNull() and img.width() >= 64:
                    return img
            except Exception:
                continue
        return None
