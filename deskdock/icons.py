"""图标提取与磁盘缓存。

说明：QFileIconProvider 内部会生成 QPixmap，属于 GUI 资源，不能跨线程使用。
这里改为主线程 + 定时器分批提取：每批处理若干条后立即让出事件循环，
首次启动几百个图标也不会卡住界面；之后全部走磁盘缓存，冷启动秒开。
"""

from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path

from PyQt5.QtCore import QFileInfo, QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QBitmap, QIcon, QImage, QPainter, QPixmap, QRegion
from PyQt5.QtWidgets import QFileIconProvider

from .config import localappdata_dir

log = logging.getLogger(__name__)

ICON_SIZE = 256
ICON_VERSION = "v3"  # 改尺寸/算法时递增，让旧缓存自动失效
BATCH_SIZE = 8
BATCH_INTERVAL_MS = 12


def _cache_dir() -> Path:
    p = localappdata_dir() / "icons"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_key(icon_source: str) -> str:
    digest = hashlib.md5(icon_source.encode("utf-8", "ignore")).hexdigest()
    return f"{digest}_{ICON_VERSION}.png"


def _trim_transparent(pix: QPixmap) -> QImage:
    """裁掉四周的透明留白。

    Windows 的图标普遍带一圈透明边距，直接铺进网格会显得又小又散。
    裁到图形实际边界再居中，整片图标才有统一的视觉重量。
    """
    img = pix.toImage()
    try:
        mask = img.createAlphaMask(Qt.AutoColor)
        region = QRegion(QBitmap.fromImage(mask))
        rect = region.boundingRect()
        if rect.isValid() and rect.width() > 4 and rect.height() > 4:
            pad = 2
            rect = rect.adjusted(-pad, -pad, pad, pad).intersected(img.rect())
            if rect.width() > 4 and rect.height() > 4:
                img = img.copy(rect)
    except Exception as exc:
        log.debug("裁剪透明边距失败: %s", exc)
    return img


def _fit_square(img: QImage, size: int) -> QImage:
    """等比缩放后居中放进正方形画布，保持图标比例不变形。"""
    scaled = img.scaled(size, size, Qt.KeepAspectRatio,
                        Qt.SmoothTransformation)
    canvas = QImage(size, size, QImage.Format_ARGB32)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.drawImage((size - scaled.width()) // 2,
                      (size - scaled.height()) // 2, scaled)
    painter.end()
    return canvas


class IconStore(QObject):
    """按需提取图标并缓存到磁盘，通过信号把可用路径推给界面。"""

    iconReady = pyqtSignal(str, str)  # entry_id, 本地 png 路径

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._dir = _cache_dir()
        self._provider = QFileIconProvider()
        self._queue: list[tuple[str, str]] = []  # (entry_id, icon_source)
        self._pending: set[str] = set()
        self._timer = QTimer(self)
        self._timer.setInterval(BATCH_INTERVAL_MS)
        self._timer.timeout.connect(self._process_batch)
        self._gc_thread: threading.Thread | None = None

    # ---- 对外 ----

    def resolve(self, entry_id: str, icon_source: str) -> str | None:
        """同步查缓存，命中返回文件路径，未命中则入队并返回 None。"""
        if not icon_source:
            return None
        cached = self._dir / _cache_key(icon_source)
        if cached.exists() and cached.stat().st_size > 0:
            return str(cached).replace("\\", "/")
        if entry_id not in self._pending:
            self._pending.add(entry_id)
            self._queue.append((entry_id, icon_source))
            if not self._timer.isActive():
                self._timer.start()
        return None

    def prime(self, items: list[tuple[str, str]]) -> dict[str, str]:
        """批量查询，返回已命中的 {entry_id: path}，未命中的自动入队。"""
        hits: dict[str, str] = {}
        for entry_id, icon_source in items:
            p = self.resolve(entry_id, icon_source)
            if p:
                hits[entry_id] = p
        return hits

    def is_busy(self) -> bool:
        return bool(self._queue)

    def purge_unused(self, keep_sources: set[str],
                     max_delete: int = 40) -> int:
        """回收用不到的缓存文件，返回本次安排删除的个数。

        keep_sources 是当前列表里所有条目的图标来源路径。除此之外的一律删。
        这一步不能省：提取算法一改（ICON_VERSION 递增），旧版本的文件就永远
        不再被命中，没人回收的话目录只增不减——实测放过两周就攒到 414 个
        文件 7MB，而当时列表里只有 145 个条目。

        只在条目非空时调用：万一扫描失败返回空列表，会把整个缓存清空。

        **删除必须放到后台线程并且限量**。实测逐个 unlink 在这个环境下要
        0.4 秒一个（Defender 实时扫描），221 个就是 88 秒——放在主线程等于
        扫描完成后把界面冻住一分半。所以：文件少就直接删，文件多就丢后台
        线程、每次限量，删不完的下次启动接着删。
        """
        if not keep_sources:
            return 0
        keep = set()
        for src in keep_sources:
            if src:
                keep.add(Path(_cache_key(src)).stem)
        try:
            stale = [f for f in self._dir.glob("*.png")
                     if f.stem not in keep]
        except OSError:
            return 0
        if not stale:
            return 0
        if len(stale) <= 5:
            return self._unlink_all(stale)
        if self._gc_thread is not None and self._gc_thread.is_alive():
            return 0  # 上一轮还没删完，别再起一个
        batch = stale[:max_delete]
        self._gc_thread = threading.Thread(
            target=self._unlink_all, args=(batch,), daemon=True)
        self._gc_thread.start()
        log.info("图标缓存待回收 %d 个，本轮后台删 %d 个",
                 len(stale), len(batch))
        return len(batch)

    @staticmethod
    def _unlink_all(files: list[Path]) -> int:
        n = 0
        for f in files:
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
        if n:
            log.info("图标缓存回收 %d 个文件", n)
        return n

    # ---- 内部 ----

    def _process_batch(self) -> None:
        if not self._queue:
            self._timer.stop()
            return

        for _ in range(min(BATCH_SIZE, len(self._queue))):
            entry_id, icon_source = self._queue.pop(0)
            try:
                path = self._extract(icon_source)
            except Exception as exc:
                log.debug("图标提取失败 %s: %s", icon_source, exc)
                path = None
            self._pending.discard(entry_id)
            if path:
                self.iconReady.emit(entry_id, path)

        if not self._queue:
            self._timer.stop()

    def _extract(self, icon_source: str) -> str | None:
        out = self._dir / _cache_key(icon_source)
        if out.exists() and out.stat().st_size > 0:
            return str(out).replace("\\", "/")

        icon: QIcon = self._provider.icon(QFileInfo(icon_source))
        if icon.isNull():
            return None

        # 尽量往大尺寸取：能拿到 256 的图标在面板里才不会发虚
        pix = QPixmap()
        for probe in (ICON_SIZE, 128, 96, 64, 48, 32):
            candidate = icon.pixmap(probe, probe)
            if not candidate.isNull() and (
                    pix.isNull() or candidate.width() > pix.width()):
                pix = candidate
        if pix.isNull():
            return None

        # 先裁掉透明边距，再等比缩放进正方形画布
        canvas = _fit_square(_trim_transparent(pix), ICON_SIZE)
        if not canvas.save(str(out), "PNG"):
            return None
        return str(out).replace("\\", "/")
