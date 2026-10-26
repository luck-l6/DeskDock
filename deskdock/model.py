"""供 QML 使用的条目模型与过滤代理。"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt5.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)

from . import pinyin
from .config import config
from .scanner import AppEntry

log = logging.getLogger(__name__)


class AppModel(QAbstractListModel):
    IdRole = Qt.UserRole + 1
    NameRole = Qt.UserRole + 2
    KindRole = Qt.UserRole + 3
    SourceRole = Qt.UserRole + 4
    IconRole = Qt.UserRole + 5
    UseCountRole = Qt.UserRole + 6
    PathRole = Qt.UserRole + 7
    DescRole = Qt.UserRole + 8

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._entries: list[AppEntry] = []
        self._icons: dict[str, str] = {}

    # ---- QAbstractListModel ----

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._entries)

    def roleNames(self) -> dict:
        return {
            self.IdRole: b"entryId",
            self.NameRole: b"name",
            self.KindRole: b"kind",
            self.SourceRole: b"source",
            self.IconRole: b"iconPath",
            self.UseCountRole: b"useCount",
            self.PathRole: b"path",
            self.DescRole: b"desc",
        }

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._entries)):
            return None
        e = self._entries[index.row()]
        if role == self.IdRole:
            return e.id
        if role == self.NameRole:
            return e.name
        if role == self.KindRole:
            return e.kind
        if role == self.SourceRole:
            return e.source
        if role == self.IconRole:
            return self._icons.get(e.id, "")
        if role == self.UseCountRole:
            return config.use_count(e.id)
        if role == self.PathRole:
            return e.path
        if role == self.DescRole:
            return e.description or e.target
        return None

    # ---- 数据维护 ----

    def set_entries(self, entries: list[AppEntry]) -> None:
        self.beginResetModel()
        self._entries = self._sorted(entries)
        self.endResetModel()

    def _sorted(self, entries: list[AppEntry]) -> list[AppEntry]:
        pinned = set(config.get("pinned") or [])
        hidden = set(config.get("hidden") or [])
        visible = [e for e in entries if e.id not in hidden]
        mode = config.get("sort_by") or "frequency"

        if mode == "name":
            return sorted(visible, key=lambda e: e.name.lower())

        if mode == "manual":
            # 手拖出来的顺序是绝对的，置顶让位给它。新出现的条目（表里还没有）
            # 落到末尾，内部按名字排，不至于每次扫描都换位置。
            pos = {eid: i for i, eid in enumerate(config.get("order") or [])}
            tail = len(pos)
            return sorted(visible, key=lambda e: (pos.get(e.id, tail),
                                                  e.name.lower()))

        def key(e: AppEntry):
            return (
                0 if e.id in pinned else 1,
                -config.use_count(e.id),
                -config.last_used(e.id),
                e.name.lower(),
            )

        return sorted(visible, key=key)

    def reorder(self) -> None:
        self.set_entries(list(self._entries))

    def move_row(self, from_row: int, to_row: int) -> bool:
        """把一个条目从 from_row 挪到 to_row（源模型坐标）。

        用 beginMoveRows 而不是整表 reset：后者会让 GridView 把所有委托
        销毁重建，拖一次闪一下；前者只搬一个格子，QSortFilterProxyModel
        会自动跟着重映射。
        """
        rows = self._entries
        n = len(rows)
        if not 0 <= from_row < n:
            return False
        to_row = max(0, min(int(to_row), n - 1))
        if to_row == from_row:
            return False

        parent = QModelIndex()
        # Qt 的 destination 是"移动后目标行前面那一行"的位置，往下拖要 +1
        dest = to_row + 1 if to_row > from_row else to_row
        if not self.beginMoveRows(parent, from_row, from_row, parent, dest):
            return False
        entry = rows.pop(from_row)
        rows.insert(to_row, entry)
        self.endMoveRows()
        return True

    def row_of(self, entry_id: str) -> int:
        for i, e in enumerate(self._entries):
            if e.id == entry_id:
                return i
        return -1

    def order_ids(self) -> list[str]:
        return [e.id for e in self._entries]

    def set_icon(self, entry_id: str, path: str) -> None:
        self._icons[entry_id] = path
        for i, e in enumerate(self._entries):
            if e.id == entry_id:
                idx = self.index(i, 0)
                self.dataChanged.emit(idx, idx, [self.IconRole])
                break

    def entry_by_id(self, entry_id: str) -> Optional[AppEntry]:
        for e in self._entries:
            if e.id == entry_id:
                return e
        return None

    # 拖拽浮层要按 id 取名字和图标。QML 里走 model.data(index, role) 拿不到
    # 东西——QModelIndex 不是 QML 认得的值类型，传进去就是个空 variant。
    @pyqtSlot(str, result=str)
    def nameOf(self, entry_id: str) -> str:
        e = self.entry_by_id(entry_id)
        return e.name if e else ""

    @pyqtSlot(str, result=str)
    def iconOf(self, entry_id: str) -> str:
        return self._icons.get(entry_id, "")

    def icon_path(self, entry_id: str) -> str:
        return self._icons.get(entry_id, "")

    def all_entries(self) -> list[AppEntry]:
        return list(self._entries)

    def ids(self) -> set[str]:
        return {e.id for e in self._entries}


class AppFilterModel(QSortFilterProxyModel):
    countChanged = pyqtSignal(int)
    searchingChanged = pyqtSignal(bool)

    # 分类 -> 接受的 kind 集合；None 表示不过滤 kind
    CATEGORIES: dict[str, Optional[set[str]]] = {
        "all": None,
        # "常用"是"打开过的应用"，文件/文件夹不算——它们躺在"文件"里按名字找更快，
        # 混进来只会把这个本来一眼能扫完的短列表撑长。
        "recent": {"app", "url"},
        "app": {"app", "url"},
        "file": {"file"},
        "folder": {"folder"},
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._query = ""
        self._category = "all"
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setSortCaseSensitivity(Qt.CaseInsensitive)
        self.rowsInserted.connect(lambda *a: self._emit_count())
        self.rowsRemoved.connect(lambda *a: self._emit_count())
        self.modelReset.connect(self._emit_count)

    @pyqtSlot(str)
    def setQuery(self, text: str) -> None:
        text = (text or "").strip()
        if text == self._query:
            # 查询没变就什么都不做：invalidateFilter 会让 GridView 重建全部
            # 代理，唤出面板时白白多卡几百毫秒（就是那块"白闪"的一部分）
            return
        was_searching = bool(self._query)
        self._query = text
        self.invalidateFilter()
        self._emit_count()
        if bool(text) != was_searching:
            self.searchingChanged.emit(bool(text))

    @pyqtSlot(str)
    def setCategory(self, name: str) -> None:
        name = name if name in self.CATEGORIES else "all"
        if name == self._category:
            return
        self._category = name
        self.invalidateFilter()
        self._emit_count()

    def _emit_count(self) -> None:
        self.countChanged.emit(self.rowCount())

    @pyqtProperty(bool, notify=searchingChanged)
    def searching(self) -> bool:
        """搜索框里有东西 —— 此时分类不参与过滤，UI 上把分类条淡化掉。"""
        return bool(self._query)

    def filterAcceptsRow(self, source_row, source_parent) -> bool:
        model = self.sourceModel()
        if model is None:
            return False
        idx = model.index(source_row, 0, source_parent)
        if not idx.isValid():
            return False

        entry_id = str(model.data(idx, AppModel.IdRole) or "")

        # 打字的时候不再看分类：想找的东西在哪个分类里，用户不应该先想明白。
        # 清空搜索框才回到分类视图。
        if not self._query:
            # "常用"只留下真的打开过的应用。usage 数据一直躺着没用，
            # 这里把它变成一个能一眼扫完的短列表——高频应用不用打字也能直达。
            if self._category == "recent" and config.use_count(entry_id) <= 0:
                return False

            kinds = self.CATEGORIES.get(self._category)
            if kinds is not None:
                if str(model.data(idx, AppModel.KindRole) or "") not in kinds:
                    return False
            return True

        name = str(model.data(idx, AppModel.NameRole) or "")
        desc = str(model.data(idx, AppModel.DescRole) or "")
        return pinyin.matches(self._query, name, desc)

    def first_row_id(self) -> str:
        """当前过滤结果的第一项 id，用于回车直接启动。"""
        if self.rowCount() <= 0:
            return ""
        idx = self.index(0, 0)
        return str(self.data(idx, AppModel.IdRole) or "")
