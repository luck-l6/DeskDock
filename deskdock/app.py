"""主程序：控制器、单实例、托盘、热键、窗口装配。"""

from __future__ import annotations

import atexit
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import time
from pathlib import Path

from PyQt5.QtCore import (
    QCoreApplication,
    QEvent,
    QFileSystemWatcher,
    QObject,
    pyqtProperty,
    Qt,
    QThread,
    QTimer,
    QUrl,
    pyqtSignal,
    pyqtSlot,
)
from PyQt5.QtGui import QCursor, QGuiApplication, QIcon
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtQml import QQmlApplicationEngine
from PyQt5.QtWidgets import QAction, QApplication, QMenu, QStyle, QSystemTrayIcon

from . import desktop as desk
from .backdrop import BackdropProvider
from .config import config, localappdata_dir
from .hotkey import HotkeyManager
from .icons import IconStore
from .launcher import launch, open_in_explorer
from .model import AppFilterModel, AppModel
from .pinyin import warmup as warmup_pinyin
from .scanner import SPECIAL_ENTRIES, AppEntry, scan, source_dirs, special_entries

log = logging.getLogger(__name__)

SERVER_NAME = "DeskDock.SingleInstance"
QML_DIR = Path(__file__).resolve().parent / "qml"


class ScanWorker(QObject):
    finished = pyqtSignal(list)

    @pyqtSlot()
    def run(self) -> None:
        try:
            entries = scan(config)
        except Exception as exc:
            log.exception("扫描失败: %s", exc)
            entries = []
        self.finished.emit(entries)


class Controller(QObject):
    """暴露给 QML 的控制器。"""

    viewModeChanged = pyqtSignal(str)
    panelVisibleChanged = pyqtSignal(bool)
    capsuleVisibleChanged = pyqtSignal(bool)
    queryChanged = pyqtSignal(str)
    resultCountChanged = pyqtSignal(int)
    statusChanged = pyqtSignal(str)
    originChanged = pyqtSignal()
    capsulePosChanged = pyqtSignal()
    autoHideChanged = pyqtSignal(bool)
    hotkeyTextChanged = pyqtSignal(str)
    backdropTokenChanged = pyqtSignal(int)
    backdropReadyChanged = pyqtSignal(bool)
    categoryChanged = pyqtSignal(str)
    categoryCountsChanged = pyqtSignal()
    dockVisibleChanged = pyqtSignal(bool)
    dockItemsChanged = pyqtSignal()
    dockGeometryChanged = pyqtSignal()
    # 开关类选项共用一个通知：值变了让 QML 重读一次即可
    optionsChanged = pyqtSignal()

    def __init__(self, engine: QQmlApplicationEngine, parent=None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._view_mode = config.get("view_mode") or "launchpad"
        self._panel_visible = False
        self._capsule_visible = bool(config.get("capsule_visible"))
        self._query = ""
        self._origin_x = 0
        self._origin_y = 0
        self._panel = None
        self._capsule = None
        self._settings = None
        self._dock = None
        self._backdrop_token = 0
        self._last_toggle_at = 0.0
        self._category = config.get("category") or "all"
        self._count_app = 0
        self._count_file = 0
        self._count_folder = 0
        self._count_recent = 0
        self._save_timer = None

        # 毛玻璃底图必须在 QML 加载前注册好
        self._backdrop = BackdropProvider()
        self._engine.addImageProvider("backdrop", self._backdrop)

        self.model = AppModel(self)
        self.filter = AppFilterModel(self)
        self.filter.setSourceModel(self.model)
        self.filter.countChanged.connect(self.resultCountChanged)
        self.filter.setCategory(self._category)

        # Dock 的列表刷新：图标是异步一个个到的，一次扫描会触发上百次
        # dataChanged。攒到一起再通知，否则 Dock 会重建上百遍。
        self._dock_refresh = QTimer(self)
        self._dock_refresh.setSingleShot(True)
        self._dock_refresh.setInterval(280)
        self._dock_refresh.timeout.connect(self.dockItemsChanged)
        self.model.dataChanged.connect(lambda *a: self._dock_refresh.start())
        self.model.modelReset.connect(self.dockItemsChanged)

        self.icons = IconStore(self)
        self.icons.iconReady.connect(self.model.set_icon)
        # 上一轮的条目数，用来判断"这轮是不是扫漏了"，避免误删图标缓存
        self._last_entry_count = 0

        self._scan_thread = QThread(self)
        self._worker = ScanWorker()
        self._worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_scan_finished)
        self._scan_thread.start()

        self.hotkey = HotkeyManager(self)
        self.hotkey.triggered.connect(self.toggle_panel)
        if config.get("hotkey_enabled"):
            self.hotkey.register(config.get("hotkey"))

        # ---- 目录监听：装了新软件 / 桌面添了文件，不用手动刷新 ----
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_source_dir_changed)
        self._watched: set[str] = set()
        self._refresh_pending = False
        # 安装程序会连着写几十个文件，每个都触发一次 directoryChanged。
        # 防抖到"写完之后的安静时刻"再扫一次。
        self._watch_timer = QTimer(self)
        self._watch_timer.setSingleShot(True)
        self._watch_timer.setInterval(1500)
        self._watch_timer.timeout.connect(self._on_watch_timer)
        self._pending_path = ""

    # ---------------- 属性 ----------------

    def getViewMode(self) -> str:
        return self._view_mode

    def setViewMode(self, mode: str) -> None:
        mode = "grid" if mode == "grid" else "launchpad"
        if mode == self._view_mode:
            return
        self._view_mode = mode
        config.set("view_mode", mode, autosave=False)
        self._schedule_save()
        self.viewModeChanged.emit(mode)

    viewMode = pyqtProperty(str, getViewMode, setViewMode, notify=viewModeChanged)

    def getPanelVisible(self) -> bool:
        return self._panel_visible

    panelVisible = pyqtProperty(bool, getPanelVisible, notify=panelVisibleChanged)

    def getBackdropToken(self) -> int:
        return self._backdrop_token

    backdropToken = pyqtProperty(int, getBackdropToken,
                                 notify=backdropTokenChanged)

    def getBackdropReady(self) -> bool:
        return self._backdrop.ready

    backdropReady = pyqtProperty(bool, getBackdropReady,
                                 notify=backdropReadyChanged)

    @pyqtSlot(str, result=str)
    def backdropSource(self, _hint: str = "") -> str:
        """给 QML 一个带版本号的 URL，避免 Image 命中旧缓存。"""
        if not self._backdrop.ready:
            return ""
        return "image://backdrop/shot?%d" % self._backdrop_token

    def _refresh_backdrop(self) -> None:
        """面板显示前重新拍一帧桌面，随时反映当前壁纸。"""
        screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        was_ready = self._backdrop.ready
        ok = self._backdrop.capture(screen)
        if ok:
            self._backdrop_token += 1
            self.backdropTokenChanged.emit(self._backdrop_token)
        if was_ready != self._backdrop.ready:
            self.backdropReadyChanged.emit(self._backdrop.ready)

    def getCapsuleVisible(self) -> bool:
        return self._capsule_visible

    capsuleVisible = pyqtProperty(bool, getCapsuleVisible,
                              notify=capsuleVisibleChanged)

    def getQuery(self) -> str:
        return self._query

    query = pyqtProperty(str, getQuery, notify=queryChanged)

    def getResultCount(self) -> int:
        return self.filter.rowCount()

    resultCount = pyqtProperty(int, getResultCount, notify=resultCountChanged)

    # ---- 分类 ----

    def getCategory(self) -> str:
        return self._category

    def _schedule_save(self) -> None:
        """延迟落盘：连续切换分类只写一次文件。

        切分类是高频操作，早先每次都同步写整个 config.json，UI 会顿一下。
        """
        if self._save_timer is None:
            from PyQt5.QtCore import QTimer

            self._save_timer = QTimer(self)
            self._save_timer.setSingleShot(True)
            self._save_timer.timeout.connect(config.save)
        self._save_timer.start(1200)

    @pyqtSlot(str)
    def setCategory(self, name: str) -> None:
        if name not in AppFilterModel.CATEGORIES:
            name = "all"
        if name == self._category:
            return
        self._category = name
        config.set("category", name, autosave=False)
        self._schedule_save()
        self.filter.setCategory(name)
        # 点分类就是"换个视角重新看"，留着上一次的搜索词只会让人以为没切成功
        self.setQuery("")
        self.categoryChanged.emit(name)

    category = pyqtProperty(str, getCategory, setCategory, notify=categoryChanged)

    def getCountApp(self) -> int:
        return self._count_app

    def getCountFile(self) -> int:
        return self._count_file

    def getCountFolder(self) -> int:
        return self._count_folder

    def getCountRecent(self) -> int:
        return self._count_recent

    countApp = pyqtProperty(int, getCountApp, notify=categoryCountsChanged)
    countFile = pyqtProperty(int, getCountFile, notify=categoryCountsChanged)
    countFolder = pyqtProperty(int, getCountFolder, notify=categoryCountsChanged)
    countRecent = pyqtProperty(int, getCountRecent, notify=categoryCountsChanged)

    def _recount_categories(self) -> None:
        app = file = folder = recent = 0
        for e in self.model.all_entries():
            if config.use_count(e.id) > 0:
                recent += 1
            if e.kind in ("app", "url"):
                app += 1
            elif e.kind == "file":
                file += 1
            elif e.kind == "folder":
                folder += 1
        self._count_app = app
        self._count_file = file
        self._count_folder = folder
        self._count_recent = recent
        self.categoryCountsChanged.emit()

    #: 卡片四周留给投影/发光的透明边距
    CARD_PAD = 34

    def getCardPad(self) -> int:
        return self.CARD_PAD

    cardPad = pyqtProperty(int, getCardPad, constant=True)

    @pyqtSlot()
    def panelDeactivated(self) -> None:
        """面板窗口失去焦点：焦点跑到别的进程就自动收起。

        焦点还留在本进程（打开设置、点胶囊）时不收，否则刚点开设置面板就没了。
        """
        if QGuiApplication.focusWindow() is not None:
            log.info("panelDeactivated：焦点仍在本进程，忽略")
            return
        log.info("panelDeactivated -> hide_panel")
        self.hide_panel()
        # 面板开着时发现的目录变化，等收起来再补扫，免得列表在眼皮底下跳
        if self._refresh_pending:
            self._refresh_pending = False
            log.info("面板已收起，补做挂起的刷新")
            self.refresh()

    def getOriginX(self) -> int:
        return self._origin_x

    def getOriginY(self) -> int:
        return self._origin_y

    originX = pyqtProperty(int, getOriginX, notify=originChanged)
    originY = pyqtProperty(int, getOriginY, notify=originChanged)

    def getCapsuleX(self) -> int:
        return int(config.get("capsule_x") or -1)

    def getCapsuleY(self) -> int:
        return int(config.get("capsule_y") or -1)

    capsuleX = pyqtProperty(int, getCapsuleX, notify=capsulePosChanged)
    capsuleY = pyqtProperty(int, getCapsuleY, notify=capsulePosChanged)

    def getAutoHide(self) -> bool:
        return bool(config.get("capsule_auto_hide"))

    autoHide = pyqtProperty(bool, getAutoHide, notify=autoHideChanged)

    def getSortBy(self) -> str:
        return str(config.get("sort_by") or "frequency")

    sortBy = pyqtProperty(str, getSortBy, notify=optionsChanged)

    def getIncludeFiles(self) -> bool:
        return bool(config.get("include_files"))

    includeFiles = pyqtProperty(bool, getIncludeFiles, notify=optionsChanged)

    def getIncludeFolders(self) -> bool:
        return bool(config.get("include_folders"))

    includeFolders = pyqtProperty(bool, getIncludeFolders, notify=optionsChanged)

    def getHideUninstallers(self) -> bool:
        return bool(config.get("hide_uninstallers"))

    hideUninstallers = pyqtProperty(bool, getHideUninstallers,
                                    notify=optionsChanged)

    def getSourceStartMenu(self) -> bool:
        return bool(config.get("source_start_menu"))

    sourceStartMenu = pyqtProperty(bool, getSourceStartMenu,
                                   notify=optionsChanged)

    def getSourceCommonStartMenu(self) -> bool:
        return bool(config.get("source_common_start_menu"))

    sourceCommonStartMenu = pyqtProperty(bool, getSourceCommonStartMenu,
                                         notify=optionsChanged)

    def getHideConsoleApps(self) -> bool:
        return bool(config.get("hide_console_apps"))

    hideConsoleApps = pyqtProperty(bool, getHideConsoleApps,
                                   notify=optionsChanged)

    def getRunAtStartup(self) -> bool:
        return desk.run_at_startup()

    runAtStartup = pyqtProperty(bool, getRunAtStartup, notify=optionsChanged)

    def getDesktopIconsVisible(self) -> bool:
        return desk.desktop_icons_visible()

    desktopIconsVisible = pyqtProperty(bool, getDesktopIconsVisible,
                                       notify=optionsChanged)

    def getHotkey(self) -> str:
        return str(config.get("hotkey") or "")

    hotkeyText = pyqtProperty(str, getHotkey, notify=hotkeyTextChanged)

    # ---------------- 窗口注册 ----------------

    @pyqtSlot(QObject)
    def registerPanel(self, win) -> None:
        self._panel = win

    @pyqtSlot(QObject)
    def registerCapsule(self, win) -> None:
        self._capsule = win

    @pyqtSlot(QObject)
    def registerSettings(self, win) -> None:
        self._settings = win

    @pyqtSlot(QObject)
    def registerDock(self, win) -> None:
        self._dock = win

    # ---------------- Dock 栏 ----------------

    def getDockVisible(self) -> bool:
        return bool(config.get("dock_visible"))

    @pyqtSlot(bool)
    def setDockVisible(self, visible: bool) -> None:
        visible = bool(visible)
        if visible == self.getDockVisible():
            return
        config.set("dock_visible", visible)
        self.dockVisibleChanged.emit(visible)
        self.optionsChanged.emit()

    dockVisible = pyqtProperty(bool, getDockVisible, notify=dockVisibleChanged)

    def getDockIconSize(self) -> int:
        try:
            return max(28, min(64, int(config.get("dock_icon_size") or 48)))
        except (TypeError, ValueError):
            return 48

    @pyqtSlot(int)
    def setDockIconSize(self, size: int) -> None:
        """Dock 图标大小。范围收紧到 28–64：再小就点不准，再大一个屏幕放不下几个。"""
        try:
            size = int(size)
        except (TypeError, ValueError):
            return
        size = max(28, min(64, size))
        if size == self.getDockIconSize():
            return
        config.set("dock_icon_size", size)
        self.optionsChanged.emit()

    dockIconSize = pyqtProperty(int, getDockIconSize, notify=optionsChanged)

    def getDockItems(self) -> list:
        """Dock 里显示的应用：沿用面板那套排序，只要应用，截前 N 个。

        这里直接算一份列表给 QML，而不是再挂一个 QSortFilterProxyModel：
        代理模型和面板共用一个 sourceModel 时，两边 setCategory / setQuery
        会互相踩，面板一搜索 Dock 就跟着变空。
        """
        try:
            limit = max(1, int(config.get("dock_max_items") or 12))
        except (TypeError, ValueError):
            limit = 12
        hidden = set(config.get("hidden") or [])
        items: list[dict] = []
        for e in self.model.all_entries():
            if e.id in hidden or e.kind not in ("app", "url"):
                continue
            items.append({
                "entryId": e.id,
                "name": e.name,
                "iconPath": self.model.icon_path(e.id),
            })
            if len(items) >= limit:
                break
        return items

    def getDockSpecial(self) -> list:
        """Dock 最左边的固定系统项（此电脑、回收站）。

        和 dockItems 分开给：QML 里两组之间要插一条分隔线，混在一个列表里
        没法分。它们不进面板，是 Dock 独有的。
        """
        # 顺序照 SPECIAL_ENTRIES 定，不能用模型的顺序。模型按"使用频率 + 名字"
        # 排，中文名比大小是按码位的：回 U+56DE < 此 U+6B64，于是回收站会跑到
        # 此电脑前面，和 Windows 桌面上的习惯顺序正好相反。
        rank = {eid: i for i, (eid, _name, _ns) in enumerate(SPECIAL_ENTRIES)}
        rows = [e for e in self.model.all_entries() if e.kind == "special"]
        rows.sort(key=lambda e: rank.get(e.id, len(rank)))
        items: list[dict] = []
        for e in rows:
            items.append({
                "entryId": e.id,
                "name": e.name,
                "iconPath": self.model.icon_path(e.id),
            })
        return items

    dockSpecial = pyqtProperty("QVariantList", getDockSpecial,
                               notify=dockItemsChanged)

    dockItems = pyqtProperty("QVariantList", getDockItems,
                             notify=dockItemsChanged)

    @pyqtSlot(str)
    def launchDockItem(self, entry_id: str) -> None:
        """从 Dock 直接启动。不碰面板状态——Dock 是常驻的，不该顺手收起面板。"""
        if not entry_id:
            return
        entry = self.model.entry_by_id(entry_id)
        if entry is None:
            log.info("launchDockItem: 找不到条目 %r", entry_id)
            return
        log.info("launchDockItem: %s kind=%s", entry.name, entry.kind)
        launch(entry)
        config.record_use(entry_id)
        self._schedule_save()
        self.model.reorder()
        self._recount_categories()
        # 频率变了，Dock 的排序跟着变（延迟一下，等图标/顺序都稳下来）
        self._dock_refresh.start()

    @pyqtSlot()
    def openSettings(self) -> None:
        if self._settings is None:
            return
        self.hide_panel()
        self._settings.setProperty("visible", True)

    @pyqtSlot(result="QVariant")
    def dockScreenInfo(self) -> dict:
        """Dock 定位要用的屏幕信息。

        放 Python 里算而不是 QML 里读 Screen：Qt 5.15 的 Screen attached
        property 在多屏下拿的是"窗口当前所在屏"，窗口还没显示时不可靠。
        """
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return {"x": 0, "y": 0, "w": 1920, "h": 1080, "bottom": 1040}
        geo = screen.availableGeometry()
        return {"x": geo.x(), "y": geo.y(),
                "w": geo.width(), "h": geo.height(),
                "bottom": geo.y() + geo.height()}

    @pyqtSlot(QObject, int)
    def applyEffects(self, win, backdrop: int = 3) -> None:
        """给窗口套上 Win11 亚克力背景与圆角。失败不影响使用。"""
        try:
            hwnd = int(win.winId())
        except Exception:
            return
        try:
            import ctypes

            dwm = ctypes.WinDLL("dwmapi")
            # DWMWA_SYSTEMBACKDROP_TYPE = 38
            val = ctypes.c_int(backdrop)
            dwm.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(val),
                                      ctypes.sizeof(val))
            # DWMWA_WINDOW_CORNER_PREFERENCE = 33, 2 = 圆角
            corner = ctypes.c_int(2)
            dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner),
                                      ctypes.sizeof(corner))
            # 窗口类背景刷设成黑色：Qt 首帧渲染完成之前，Windows 用类背景刷
            # 填窗口，默认是白的——全屏白块就是"闪一下"的来源。黑色在深色
            # 壁纸上看起来只是一次压暗淡入。
            brush = ctypes.windll.gdi32.GetStockObject(4)  # BLACK_BRUSH
            ctypes.windll.user32.SetClassLongPtrW(hwnd, -10, brush)  # GCLP_HBRBACKGROUND
        except Exception as exc:
            log.debug("设置窗口效果失败: %s", exc)

    @pyqtSlot(QObject)
    def pinToBottom(self, win) -> bool:
        """把胶囊压到所有窗口之下：桌面露出来时它才可见，观感与桌面图标一致。

        这里不用跨进程 SetParent 把窗口挂进 Explorer 的桌面图层——那样会和 Qt
        的窗口管理状态冲突，实测会让进程直接崩掉。置底方案稳定得多。
        """
        try:
            hwnd = int(win.winId())
        except Exception:
            return False
        return desk.set_bottommost(hwnd)

    # ---------------- 行为 ----------------

    @pyqtSlot()
    def toggle_panel(self) -> None:
        # 双击 / 事件重复上报时会连着触发两次，面板就会"闪一下又没了"。
        # 短时间内只认第一次。
        now = time.monotonic()
        if now - self._last_toggle_at < 0.25:
            log.info("toggle_panel 被防抖拦截")
            return
        self._last_toggle_at = now
        log.info("toggle_panel -> %s", "hide" if self._panel_visible else "show")
        if self._panel_visible:
            self.hide_panel()
        else:
            self.show_panel()

    @pyqtSlot()
    def show_panel(self) -> None:
        log.info("show_panel(panel=%s, visible=%s)",
                 self._panel is not None, self._panel_visible)
        if self._panel is None or self._panel_visible:
            return
        # 先清空搜索，避免显示之后网格再重排一次造成闪动
        self.setQuery("")
        self._layout_window()
        self._compute_origin()
        # 先拍背景，再显示窗口：否则会把面板自己拍进底图。
        # 这一步是唤出延迟的几乎全部来源（实测 60–80ms，其余步骤加起来不到
        # 1ms）。没有改成「复用上一帧」：那样能省到 20ms，但底图会和真实桌面
        # 对不上，而这个工具卖的就是"桌面前台是什么就读什么"。
        self._refresh_backdrop()
        self._panel_visible = True
        # 显隐统一交给 QML：Python 再调一次 show() / requestActivate()
        # 会让窗口显示两遍，看起来就是闪两下
        self.panelVisibleChanged.emit(True)
        if self._settings:
            self._settings.setProperty("visible", False)

    @pyqtSlot()
    def hide_panel(self) -> None:
        log.debug("hide_panel(visible=%s)", self._panel_visible)
        if self._panel is None or not self._panel_visible:
            return
        self._panel_visible = False
        self.panelVisibleChanged.emit(False)

    def _layout_window(self) -> None:
        """按视图模式给面板定几何。

        卡片模式刻意**不**铺满整屏：窗口只包住卡片本身加一圈投影边距，
        屏幕其余部分还是真实桌面，唤出时只有那一小块发生变化。
        早先窗口是全屏的，每次唤出都要把整屏重画一遍（静态截图 + 压暗层），
        观感就是"锁屏"式地闪一下 —— 卡片明明只有巴掌大，却占满了屏幕。
        """
        screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None or self._panel is None:
            return
        geo = screen.geometry()
        if self._view_mode == "grid":
            cw = int(min(max(880, geo.width() * 0.48), 1180))
            ch = int(min(max(600, geo.height() * 0.68), 980))
            cx = geo.x() + (geo.width() - cw) // 2
            cy = geo.y() + int((geo.height() - ch) * 0.40)
            pad = self.CARD_PAD
            values = (("x", cx - pad), ("y", cy - pad),
                      ("width", cw + pad * 2), ("height", ch + pad * 2))
        else:
            values = (("x", geo.x()), ("y", geo.y()),
                      ("width", geo.width()), ("height", geo.height()))
        for name, value in values:
            self._panel.setProperty(name, value)

    def _compute_origin(self) -> None:
        """面板从胶囊所在位置放大展开，动画更有来处。"""
        cx = int(config.get("capsule_x") or -1)
        cy = int(config.get("capsule_y") or -1)
        if cx < 0 or cy < 0:
            screen = QGuiApplication.screenAt(QCursor.pos())
            if screen is None:
                screen = QGuiApplication.primaryScreen()
            if screen:
                geo = screen.geometry()
                cx = geo.center().x()
                cy = geo.center().y()
        elif not self._on_any_screen(cx, cy):
            # 记下来的坐标落在已经不存在的屏幕上了：拔掉外接显示器、改了分辨率、
            # 或者显示器换过位置。直接用旧坐标的话胶囊会显示在屏幕外，面板也会
            # 从屏幕外弹进来——所以把它拉回当前屏幕中心，并把配置一起改掉，
            # 否则下次启动又跑到外面。
            screen = QGuiApplication.screenAt(QCursor.pos())
            if screen is None:
                screen = QGuiApplication.primaryScreen()
            if screen:
                geo = screen.geometry()
                cx = geo.center().x()
                cy = geo.center().y()
                config.set("capsule_x", cx - 66, autosave=False)
                config.set("capsule_y", cy - 39, autosave=False)
                self._schedule_save()

    @staticmethod
    def _on_any_screen(x: int, y: int) -> bool:
        """坐标是否落在某个还连着的屏幕上（留 80px 余量，允许贴边）。"""
        margin = 80
        for screen in QGuiApplication.screens():
            geo = screen.geometry().adjusted(-margin, -margin, margin, margin)
            if geo.contains(x, y):
                return True
        return False
        # 取胶囊中心，而不是左上角，弹出的方向才自然。
        # 偏移值 = Capsule.qml 里窗口尺寸的一半（132x78）
        self._origin_x = cx + 66
        self._origin_y = cy + 39
        self.originChanged.emit()

    @pyqtSlot(str)
    def setQuery(self, text: str) -> None:
        text = text or ""
        if text == self._query:
            return
        self._query = text
        self.queryChanged.emit(self._query)
        self.filter.setQuery(self._query)
        self.resultCountChanged.emit(self.filter.rowCount())

    @pyqtSlot(str)
    def launchById(self, entry_id: str) -> None:
        if not entry_id:
            entry_id = self.filter.first_row_id()
        log.info("launchById 请求 id=%r", entry_id)
        if not entry_id:
            log.info("launchById: 无 id，放弃")
            return
        entry = self.model.entry_by_id(entry_id)
        if entry is None:
            log.info("launchById: 找不到条目 %r", entry_id)
            return
        log.info("launchById: %s kind=%s path=%r target=%r",
                 entry.name, entry.kind, entry.path, entry.target)
        # 先收起面板再启动：startfile 可能阻塞好几秒，不能让它挡着动画
        self.hide_panel()
        # launch 是异步的，调用即返回；真正的成败在后台线程里记日志
        launch(entry)
        config.record_use(entry_id)
        self._schedule_save()
        self.model.reorder()
        # 首次打开某个应用后，"常用"的数量就变了
        self._recount_categories()

    @pyqtSlot(str)
    def reveal(self, entry_id: str) -> None:
        entry = self.model.entry_by_id(entry_id)
        if entry:
            self.hide_panel()
            open_in_explorer(entry.path)

    @pyqtSlot(str, result=bool)
    def isPinned(self, entry_id: str) -> bool:
        return entry_id in (config.get("pinned") or [])

    @pyqtSlot(str)
    def togglePin(self, entry_id: str) -> None:
        pinned = list(config.get("pinned") or [])
        if entry_id in pinned:
            pinned.remove(entry_id)
        else:
            pinned.append(entry_id)
        config.set("pinned", pinned)
        self.model.reorder()

    @pyqtSlot(str)
    def hideEntry(self, entry_id: str) -> None:
        hidden = list(config.get("hidden") or [])
        if entry_id not in hidden:
            hidden.append(entry_id)
            config.set("hidden", hidden)
            self.model.reorder()

    @pyqtSlot()
    def unhideAll(self) -> None:
        config.set("hidden", [])
        config.set("pinned", [])
        self.model.reorder()

    @pyqtSlot()
    def refresh(self) -> None:
        self.statusChanged.emit("正在扫描…")
        if not self._scan_thread.isRunning():
            self._scan_thread.start()

    # ---------------------------------------------------- 目录监听
    # QFileSystemWatcher 不递归，所以监听"源目录 + 一层子目录"：
    # 安装软件通常创建 Programs\厂商\App.lnk，只听 Programs 是听不到的。
    # 再深就不听了——Windows 上一个目录一个句柄，开始菜单深挖下去有几百个。
    _WATCH_DEPTH = 1
    _WATCH_MAX = 400

    def _collect_watch_dirs(self) -> list[str]:
        out: list[str] = []
        try:
            for directory, _tag in source_dirs(config):
                base = Path(directory)
                if not base.is_dir():
                    continue
                out.append(str(base))
                if self._WATCH_DEPTH <= 0:
                    continue
                try:
                    for child in sorted(base.iterdir()):
                        if len(out) >= self._WATCH_MAX:
                            break
                        if child.is_dir() and not child.name.startswith("."):
                            out.append(str(child))
                except OSError:
                    pass
        except Exception as exc:
            log.warning("收集监听目录失败: %s", exc)
        return out

    def _update_watch_paths(self) -> None:
        want = set(self._collect_watch_dirs())
        if want == self._watched:
            return
        stale = self._watched - want
        if stale:
            # 目录被删掉时 removePath 会失败，失败也无所谓，忽略即可
            self._watcher.removePaths(sorted(stale))
        fresh = sorted(want - self._watched)
        if fresh:
            # 返回值不能信：PyQt 的 addPaths 在这里返回空列表，实际上
            # 目录全都挂上了（watcher.directories() 里看得到）。以 watcher
            # 自己的状态为准，否则每轮扫描都会重复 add 一遍。
            self._watcher.addPaths(fresh)
        self._watched = set(self._watcher.directories())
        log.info("目录监听：%d 个目录（本轮新增 %d）", len(self._watched), len(fresh))

    def _on_source_dir_changed(self, path: str) -> None:
        # 只记下来、不立刻扫：安装过程会连着写很多文件
        self._watch_timer.start()
        self._pending_path = path

    def _on_watch_timer(self) -> None:
        if self._panel_visible:
            self._refresh_pending = True
            log.info("目录变化（%s），面板开着，挂起到收起后刷新",
                     getattr(self, "_pending_path", ""))
            return
        log.info("目录变化（%s），自动刷新", getattr(self, "_pending_path", ""))
        self.refresh()

    # ---------------------------------------------------- 手动排序
    @pyqtSlot(str)
    def debugLog(self, msg: str) -> None:
        """QML 侧的落盘日志。console.log 在 pythonw 下会丢，只能绕一道。"""
        log.info("QML: %s", msg)

    @pyqtSlot(str, int)
    def moveEntry(self, entry_id: str, target_index: int) -> None:
        """把条目拖到第 target_index 个位置（index 是过滤后的可见序号）。

        第一次拖就自动切成手动排序——否则拖完 model 按频率重排，
        格子立刻弹回原处，看起来像没拖动。
        """
        if not entry_id or target_index < 0:
            return
        if config.get("sort_by") != "manual":
            config.set("sort_by", "manual", autosave=False)
            config.set("order", self.model.order_ids(), autosave=False)
            self.optionsChanged.emit()

        src_idx = self.filter.index(target_index, 0)
        if not src_idx.isValid():
            return
        to_row = self.filter.mapToSource(src_idx).row()
        from_row = self.model.row_of(entry_id)
        if from_row < 0:
            return
        log.info("moveEntry target=%d src=%d->%d", target_index, from_row, to_row)
        if not self.model.move_row(from_row, to_row):
            return
        config.set("order", self.model.order_ids(), autosave=False)
        self._schedule_save()

    @pyqtSlot(int, int)
    def saveCapsulePos(self, x: int, y: int) -> None:
        config.set("capsule_x", int(x), autosave=False)
        config.set("capsule_y", int(y), autosave=False)
        config.save()
        self.capsulePosChanged.emit()

    @pyqtSlot(bool)
    def setCapsuleVisible(self, visible: bool) -> None:
        self._capsule_visible = visible
        config.set("capsule_visible", visible)
        self.capsuleVisibleChanged.emit(visible)

    @pyqtSlot(bool)
    def setDesktopIconsVisible(self, visible: bool) -> None:
        desk.set_desktop_icons_visible(visible)
        # 用户主动恢复图标，兜底就该撤掉；重新隐藏时再埋上
        if visible:
            desk.disarm_restore_fallback()
        else:
            desk.arm_restore_fallback()
        config.set("hide_system_desktop_icons", not visible)
        self.optionsChanged.emit()

    @pyqtSlot(bool)
    def setRunAtStartup(self, enabled: bool) -> None:
        desk.set_run_at_startup(enabled)
        config.set("run_at_startup", enabled)
        self.optionsChanged.emit()

    @pyqtSlot(str)
    def setHotkey(self, combination: str) -> None:
        config.set("hotkey", combination)
        self.hotkeyTextChanged.emit(combination)
        if config.get("hotkey_enabled"):
            self.hotkey.register(combination)

    @pyqtSlot(str)
    def setSortBy(self, mode: str) -> None:
        if mode == "manual":
            # 以当前看到的顺序作为起点，否则一选"手动"列表就按名字重排了
            config.set("order", self.model.order_ids(), autosave=False)
        config.set("sort_by", mode)
        self.model.reorder()
        self.optionsChanged.emit()

    @pyqtSlot(bool)
    def setAutoHide(self, enabled: bool) -> None:
        config.set("capsule_auto_hide", enabled)
        self.autoHideChanged.emit(enabled)

    @pyqtSlot(bool)
    def setIncludeFiles(self, enabled: bool) -> None:
        config.set("include_files", enabled)
        self.optionsChanged.emit()
        self.refresh()

    @pyqtSlot(bool)
    def setIncludeFolders(self, enabled: bool) -> None:
        config.set("include_folders", enabled)
        self.optionsChanged.emit()
        self.refresh()

    @pyqtSlot(bool)
    def setHideUninstallers(self, enabled: bool) -> None:
        config.set("hide_uninstallers", enabled)
        self.optionsChanged.emit()
        self.refresh()

    @pyqtSlot(bool)
    def setSourceStartMenu(self, enabled: bool) -> None:
        config.set("source_start_menu", enabled)
        self.optionsChanged.emit()
        self.refresh()

    @pyqtSlot(bool)
    def setSourceCommonStartMenu(self, enabled: bool) -> None:
        config.set("source_common_start_menu", enabled)
        self.optionsChanged.emit()
        self.refresh()

    @pyqtSlot(bool)
    def setHideConsoleApps(self, enabled: bool) -> None:
        config.set("hide_console_apps", enabled)
        self.optionsChanged.emit()
        self.refresh()

    @pyqtSlot()
    def openSettings(self) -> None:
        if self._settings:
            self._settings.setProperty("visible", True)
            self._settings.requestActivate()

    @pyqtSlot()
    def quit(self) -> None:
        QCoreApplication.quit()

    # ---------------- 内部 ----------------

    def _on_scan_finished(self, entries) -> None:
        # 固定系统项（此电脑、回收站）排在最前，Dock 按这个顺序摆
        entries = special_entries() + list(entries)
        self.model.set_entries(list(entries))
        self._recount_categories()
        hits = self.icons.prime([(e.id, e.icon_source) for e in entries])
        for entry_id, path in hits.items():
            self.model.set_icon(entry_id, path)
        self.filter.setQuery(self._query)
        self.resultCountChanged.emit(self.filter.rowCount())
        self.statusChanged.emit(f"共 {len(entries)} 项")
        # 拼音表晚点建会在用户敲第一个字母时卡一下，趁现在（后台线程）先摊开
        warmup_pinyin()
        self._scan_thread.quit()
        log.info("扫描完成：%d 项，图标命中 %d", len(entries), len(hits))
        # 目录可能增删过（装了新软件就多一层），监听表跟着重算
        self._update_watch_paths()
        # 顺手回收用不到的图标缓存：条目都没了，缓存还留着就是白占磁盘。
        # 条目数比上次骤降一半以上时跳过——那通常是某块盘/某个源目录这次没读到，
        # 这时候删缓存等于白删，下次还得重新提取。
        n = len(entries)
        if n and n >= self._last_entry_count * 0.5:
            self.icons.purge_unused({e.icon_source for e in entries})
        elif n:
            log.info("条目数从 %d 掉到 %d，本轮跳过缓存回收",
                     self._last_entry_count, n)
        self._last_entry_count = n


def _build_tray(ctrl: Controller, app: QApplication) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(app)
    icon_path = Path(__file__).resolve().parent / "qml" / "tray.png"
    if icon_path.exists():
        tray.setIcon(QIcon(str(icon_path)))
    else:
        tray.setIcon(app.style().standardIcon(QStyle.SP_ComputerIcon))
    tray.setToolTip("DeskDock 桌面收纳")

    menu = QMenu()

    act_show = QAction("显示面板", menu)
    act_show.triggered.connect(ctrl.show_panel)
    menu.addAction(act_show)

    act_refresh = QAction("重新扫描", menu)
    act_refresh.triggered.connect(ctrl.refresh)
    menu.addAction(act_refresh)

    menu.addSeparator()

    act_launch = QAction("全屏 Launchpad", menu)
    act_launch.setCheckable(True)
    act_launch.triggered.connect(lambda: ctrl.setViewMode("launchpad"))
    menu.addAction(act_launch)

    act_grid = QAction("居中网格面板", menu)
    act_grid.setCheckable(True)
    act_grid.triggered.connect(lambda: ctrl.setViewMode("grid"))
    menu.addAction(act_grid)

    def sync_views():
        act_launch.setChecked(ctrl.getViewMode() == "launchpad")
        act_grid.setChecked(ctrl.getViewMode() == "grid")

    ctrl.viewModeChanged.connect(sync_views)
    sync_views()

    menu.addSeparator()

    act_capsule = QAction("显示桌面胶囊", menu)
    act_capsule.setCheckable(True)
    act_capsule.setChecked(ctrl.getCapsuleVisible())
    act_capsule.triggered.connect(ctrl.setCapsuleVisible)
    menu.addAction(act_capsule)

    act_icons = QAction("显示系统桌面图标", menu)
    act_icons.setCheckable(True)
    act_icons.setChecked(desk.desktop_icons_visible())
    act_icons.triggered.connect(ctrl.setDesktopIconsVisible)
    menu.addAction(act_icons)

    act_startup = QAction("开机自启", menu)
    act_startup.setCheckable(True)
    act_startup.setChecked(desk.run_at_startup())
    act_startup.triggered.connect(ctrl.setRunAtStartup)
    menu.addAction(act_startup)

    menu.addSeparator()

    act_settings = QAction("设置", menu)
    act_settings.triggered.connect(ctrl.openSettings)
    menu.addAction(act_settings)

    act_quit = QAction("退出", menu)
    act_quit.triggered.connect(ctrl.quit)
    menu.addAction(act_quit)

    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: ctrl.show_panel()
        if reason == QSystemTrayIcon.Trigger else None)
    tray.show()
    return tray


def _single_instance() -> tuple[QLocalServer | None, bool]:
    """返回 (server, 是否首个实例)。非首个实例时已通知旧实例并退出。"""
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if socket.waitForConnected(300):
        socket.write(b"show")
        socket.flush()
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        return None, False
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)
    return server, True


QML_MESSAGES: list[str] = []


def _install_message_handler() -> None:
    """把 Qt / QML 的警告收集起来，便于自检时发现问题。"""
    from PyQt5.QtCore import qInstallMessageHandler

    def handler(mode, context, message):
        QML_MESSAGES.append(message)
        level = logging.INFO if os.environ.get("DESKDOCK_QML_VERBOSE") else logging.DEBUG
        log.log(level, "Qt(%s): %s", mode, message)

    qInstallMessageHandler(handler)


def _session_file() -> Path:
    return localappdata_dir() / "session.json"


#: 见 main()：把 Controller 钉住，避免它先于 QML 对象被回收
_CONTROLLER_REF: object | None = None


def _teardown_qml(engine) -> None:
    """退出时先拆 QML 引擎，再让进程收尾。

    QML 对象在析构过程中还会回头读 controller 的属性。如果 controller 先被
    回收，它们读到的就是 null，每次退出刷几十条
    "Cannot read property 'X' of null"（实测 48 条）。

    controller 已经由模块级引用钉住，这里只要保证 QML 对象先销毁。显式
    deleteLater + 冲掉 DeferredDelete 事件，比赌解释器的析构顺序可靠：
    光靠引用计数时好时坏，同一份代码有时 0 条有时 48 条。
    """
    try:
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    except Exception as exc:
        log.debug("拆除 QML 引擎失败: %s", exc)


def _mark_session_start() -> bool:
    """标记本次会话开始，返回 True 表示上次是非正常退出。

    正常退出时会把这个文件删掉；下次启动还在，就说明上次是崩了或被强杀的，
    那种情况下桌面图标大概率还处于隐藏状态，得先还回去。
    """
    path = _session_file()
    crashed = False
    try:
        if path.exists():
            crashed = True
    except Exception:
        pass
    try:
        path.write_text(json.dumps({"pid": os.getpid(), "at": time.time()}),
                        encoding="utf-8")
    except Exception:
        pass
    return crashed


def _clear_session() -> None:
    try:
        _session_file().unlink(missing_ok=True)
    except Exception:
        pass


def main() -> int:
    # 无窗口启动（pythonw）时 stdout 不可见，必须落盘，否则进程莫名退出无从查起
    _log_file = localappdata_dir() / "deskdock.log"
    try:
        _log_file.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            # 必须轮转：早期用裸 FileHandler，只 append 不回收，跑两天就 500KB+，
            # 而里面大半是调试期留下的调用栈——磁盘慢慢涨，真正有用的记录被淹掉。
            RotatingFileHandler(str(_log_file), maxBytes=1024 * 1024,
                                backupCount=3, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    log.info("---- DeskDock 启动 pid=%s ----", os.getpid())

    # RunOnce 兜底被触发：上次 DeskDock 没能正常退出（崩溃、被强杀、自启被关），
    # Windows 在本次登录时替它把图标还回去。这里不启动完整程序。
    if "--restore-icons" in sys.argv:
        try:
            desk.set_desktop_icons_visible(True)
            desk.disarm_restore_fallback()
            _clear_session()
            log.info("RunOnce 兜底执行完毕：桌面图标已恢复")
        except Exception as exc:
            log.error("恢复桌面图标失败: %s", exc)
        return 0

    import faulthandler
    try:
        _faulth = open(str(_log_file.with_name("deskdock.crash.txt")), "w",
                       encoding="utf-8")
        faulthandler.enable(file=_faulth)
    except Exception:
        pass

    def _excepthook(etype, value, tb):
        import traceback
        log.error("未捕获异常：\n%s", "".join(
            traceback.format_exception(etype, value, tb)))
        sys.__excepthook__(etype, value, tb)

    sys.excepthook = _excepthook
    selftest = "--selftest" in sys.argv
    if selftest:
        logging.getLogger().setLevel(logging.DEBUG)

    _install_message_handler()

    # 打包成 exe 之后 Qt 不知道自己的 QML 插件被放哪了，必须由我们指认，
    # 否则 Panel.qml 一加载就失败、面板全白。必须在 QApplication 构造之前设好，
    # 晚了引擎已经把导入路径缓存起来了。
    #
    # 只指认**一份**：PyInstaller 的 PyQt5 hook 已经把插件放到
    # _MEIPASS/PyQt5/Qt5/qml。若再自己拷一份并指过去，引擎会看到两份
    # QtQuick.Controls，刷一屏 "Cannot install type ... into protected module"。
    if getattr(sys, "frozen", False):
        _bundle = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        for _cand in (_bundle / "PyQt5" / "Qt5" / "qml", _bundle / "qml"):
            if _cand.is_dir():
                os.environ["QML2_IMPORT_PATH"] = str(_cand)
                log.info("冻结模式：QML2_IMPORT_PATH=%s", _cand)
                break
        else:
            log.warning("冻结模式：没找到 QML 插件目录，QML 可能加载失败")

    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except AttributeError:
        pass
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("DeskDock")
    app.setOrganizationName("DeskDock")

    server, first = _single_instance()
    if not first:
        return 0

    engine = QQmlApplicationEngine()
    ctrl = Controller(engine)
    # controller 必须比 QML 引擎活得久。QML 对象析构时还会回头读 controller
    # 的属性，要是它先被回收，QML 侧拿到的是 null，每次退出刷几十条
    # "Cannot read property 'X' of null"（实测 48 条）。用模块级引用钉住它，
    # 等解释器收尾时才释放——那时 QML 对象早没了。
    global _CONTROLLER_REF
    _CONTROLLER_REF = ctrl

    engine.rootContext().setContextProperty("controller", ctrl)
    engine.rootContext().setContextProperty("appModel", ctrl.filter)
    engine.rootContext().setContextProperty("rawModel", ctrl.model)

    for name in ("Panel.qml", "Capsule.qml", "Settings.qml", "Dock.qml"):
        path = QML_DIR / name
        if not path.exists():
            log.error("缺少 QML 文件: %s", name)
            continue
        before = len(engine.rootObjects())
        engine.load(QUrl.fromLocalFile(str(path)))
        after = len(engine.rootObjects())
        log.info("加载 %s：根对象 %d -> %d", name, before, after)
        if after == before:
            log.error("QML 加载失败：%s", name)
            for m in QML_MESSAGES[-20:]:
                log.error("  %s", m)
        elif QML_MESSAGES:
            for m in QML_MESSAGES[-20:]:
                log.warning("  %s", m)

    if not engine.rootObjects():
        log.error("QML 加载失败")
        return 1

    tray = _build_tray(ctrl, app)

    def on_new_connection():
        conn = server.nextPendingConnection()
        if conn:
            def _on_ready():
                cmd = bytes(conn.readAll()).strip()
                # readyRead 会在数据读完后再触发一次，那时 readAll() 是空的。
                # 空命令落进 else 分支就会凭空弹一次面板，必须先挡掉。
                if not cmd:
                    return
                if cmd == b"hide":
                    ctrl.hide_panel()
                elif cmd == b"settings":
                    ctrl.openSettings()
                elif cmd == b"quit":
                    # 走正规的退出路径，用来验证 aboutToQuit 有没有把图标还回去
                    QCoreApplication.quit()
                elif cmd == b"launch":
                    # 调试用：直接启动第一条，绕开 QML 点击，用来区分
                    # 「点击没送到 Python」还是「启动本身失败」
                    ctrl.launchById("")
                else:
                    ctrl.show_panel()
                conn.close()

            conn.readyRead.connect(_on_ready)

    server.newConnection.connect(on_new_connection)

    if selftest:
        import faulthandler

        faulthandler.enable()
        from PyQt5.QtCore import QTimer

        def report():
            print("ROOT_OBJECTS:", len(engine.rootObjects()))
            print("QML_MESSAGES:", len(QML_MESSAGES))
            for m in QML_MESSAGES[:40]:
                print("  -", m)
            app.quit()

        QTimer.singleShot(1500, report)
        rc = app.exec_()
        _teardown_qml(engine)
        return rc

    # 预热渲染：第一次 show 要编译着色器、解码全部图标，首帧能慢近 1 秒，
    # 这就是唤出时"全屏闪一下"的主要来源。趁刚启动用户还没操作，先把面板
    # 完整渲染一遍再藏起来。预热时卡片进度为 0、窗口显示的是刚拍的桌面
    # 快照，用户基本无感；之后每次唤出首帧都很快。
    from PyQt5.QtCore import QTimer as _QTimer

    def _prewarm_show():
        if ctrl._panel is None or ctrl._panel_visible:
            return
        log.info("预热：渲染面板首帧…")
        ctrl._layout_window()
        ctrl._refresh_backdrop()
        w = ctrl._panel
        # 挪到屏幕左外侧再显示：渲染照常发生，但用户眼前完全无感
        w.setProperty("x", -w.property("width") - 400)
        w.setProperty("visible", True)

    def _prewarm_hide():
        if ctrl._panel is None or ctrl._panel_visible:
            return
        ctrl._panel.setProperty("visible", False)
        log.info("预热完成")

    if not os.environ.get("DESKDOCK_NO_PREWARM"):
        _QTimer.singleShot(1500, _prewarm_show)
        _QTimer.singleShot(3300, _prewarm_hide)

    # 调试用：把某个窗口**自身**的渲染结果存成图片。
    # 屏幕截图不可靠：锁屏时拍到的是锁屏画面，被全屏视频之类置顶窗口盖住时
    # 拍到的是那个窗口（两次都误判成"根本没渲染"）。QQuickWindow::grabWindow()
    # 抓的是窗口内容本身，屏幕上盖了什么完全无关。
    #   DESKDOCK_SHOT="dock=D:\out\dock.png;settings=D:\out\set.png"
    # 指定 settings 会先把设置页打开再抓。老的 DESKDOCK_DOCK_SHOT 仍然有效。
    _shot_spec = os.environ.get("DESKDOCK_SHOT", "").strip()
    if os.environ.get("DESKDOCK_DOCK_SHOT"):
        _shot_spec = (_shot_spec + ";dock=" + os.environ["DESKDOCK_DOCK_SHOT"]).strip(";")
    _shot_targets = []
    for _part in _shot_spec.split(";"):
        if "=" not in _part:
            continue
        _k, _v = _part.split("=", 1)
        if _v.strip():
            _shot_targets.append((_k.strip().lower(), _v.strip()))
    if _shot_targets:

        def _grab(name: str, path: str) -> None:
            win = getattr(ctrl, "_" + name, None)
            if win is None:
                log.info("%s 抓图：窗口还没注册", name)
                return
            try:
                img = win.grabWindow()
                ok = img.save(path, "PNG")
                log.info("%s 抓图 %dx%d 保存=%s", name, img.width(), img.height(), ok)
            except Exception as exc:
                log.exception("%s 抓图失败: %s", name, exc)

        if any(k == "settings" for k, _ in _shot_targets):
            _QTimer.singleShot(2500, ctrl.openSettings)
        for _k, _v in _shot_targets:
            # 用默认参数把循环变量钉住，否则所有 lambda 都指向最后一次迭代
            _QTimer.singleShot(6000, lambda k=_k, v=_v: _grab(k, v))

    # ---- 系统桌面图标：埋好恢复兜底再隐藏，退出时必须还回去 ----
    crashed = _mark_session_start()
    desk.install_crash_restore_hook()
    if config.get("hide_system_desktop_icons"):
        if crashed:
            log.warning("检测到上次非正常退出，先把桌面图标恢复一次")
            desk.set_desktop_icons_visible(True)
            # 崩溃这种事不该让用户自己猜。崩溃当时图标已经由异常钩子还回去了，
            # 这里再明确说一声，顺便告诉他还有个手动开关。
            try:
                tray.showMessage(
                    "DeskDock", "上次是异常退出的，桌面图标已自动恢复。"
                    "若没看到图标，可从托盘菜单里手动恢复。",
                    QSystemTrayIcon.Information, 6000)
            except Exception:
                pass
        desk.arm_restore_fallback()
        desk.set_desktop_icons_visible(False)
    if config.get("run_at_startup"):
        desk.set_run_at_startup(True)

    _exit_state = {"restored": False}

    def _restore_icons_on_exit() -> None:
        # aboutToQuit 和 atexit 都会走到这里，只执行一次
        if _exit_state["restored"]:
            return
        _exit_state["restored"] = True
        if config.get("hide_system_desktop_icons"):
            log.info("退出：恢复系统桌面图标")
            desk.set_desktop_icons_visible(True)
            desk.disarm_restore_fallback()
        _clear_session()

    app.aboutToQuit.connect(_restore_icons_on_exit)
    atexit.register(_restore_icons_on_exit)

    app.aboutToQuit.connect(ctrl.hotkey.unregister)

    # 心跳：进程若被异常终止或事件循环自己退出，日志里能一眼看出差别
    def _on_quit():
        log.info("aboutToQuit —— 事件循环即将结束")

    app.aboutToQuit.connect(_on_quit)
    try:
        from PyQt5.QtCore import QTimer
        _hb = {"n": 0}

        def _beat():
            _hb["n"] += 1
            log.info("heartbeat %d", _hb["n"])

        _t = QTimer()
        _t.timeout.connect(_beat)
        _t.start(300000)
    except Exception:
        pass

    code = app.exec_()
    log.info("exec_ 返回 %s", code)
    _teardown_qml(engine)
    return code


if __name__ == "__main__":
    sys.exit(main())
