"""配置持久化与路径常量。"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

APP_NAME = "DeskDock"

_DEFAULTS: dict[str, Any] = {
    "view_mode": "grid",          # launchpad | grid
    "category": "all",                 # all | app | file | folder
    "hotkey": "Ctrl+Alt+Space",
    "hotkey_enabled": True,
    "source_desktop": True,
    "source_common_desktop": True,
    "source_start_menu": True,
    # 公共开始菜单（C:\ProgramData\...\Programs）：Chrome / Office / JetBrains /
    # Steam 这些给所有用户装的程序，快捷方式只放这里，不扫就整类漏掉
    "source_common_start_menu": True,
    "include_files": True,             # 桌面上的文档也一并收纳
    "include_folders": True,           # 桌面上的文件夹也一并收纳
    "hide_system_desktop_icons": True, # 关掉 Windows 自己的桌面图标
    "hide_uninstallers": True,
    "hide_console_apps": True,         # 控制台程序（解释器、命令行工具）不收
    "capsule_visible": True,
    "capsule_x": -1,                   # -1 表示未设置，首次启动自动贴右下角
    "capsule_y": -1,
    "capsule_auto_hide": True,         # 鼠标不靠近时半透明淡出
    "capsule_always_on_desktop": True, # 嵌到桌面图层（Win+D 时跟随桌面）
    "sort_by": "frequency",            # frequency | name | manual（拖拽排出来的顺序）
    "order": [],                       # manual 模式下的 id 顺序；不在表里的排在末尾
    "grid_columns": 7,
    "launchpad_columns": 8,
    "run_at_startup": True,
    "usage": {},                       # id -> [count, last_ts]
    "pinned": [],                      # 手动置顶的 id 列表
    "hidden": [],                      # 手动隐藏的 id 列表
}

_lock = threading.Lock()

# 默认值改过语义时用它把老配置抬上来，不然用户文件里那句旧默认值永远生效
_SCHEMA_VERSION = 2

_MIGRATIONS: dict[int, dict[str, Any]] = {
    # v1 -> v2：公共开始菜单当年默认关着，老用户文件里的 False 不是他自己选的
    2: {"source_common_start_menu": True},
}


def appdata_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    p = Path(base) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def localappdata_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    p = Path(base) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    return appdata_dir() / "config.json"


class Config:
    """线程安全的配置读写，自动补默认值。"""

    def __init__(self) -> None:
        self._data: dict[str, Any] = dict(_DEFAULTS)
        self.load()

    def load(self) -> None:
        with _lock:
            path = config_path()
            if path.exists():
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        for k, v in raw.items():
                            self._data[k] = v
                except (json.JSONDecodeError, OSError):
                    pass
            # 补齐新增的默认值
            for k, v in _DEFAULTS.items():
                self._data.setdefault(k, v)

            version = int(self._data.get("schema") or 1)
            need_save = False
            for target in sorted(v for v in _MIGRATIONS if v > version):
                for k, v in _MIGRATIONS[target].items():
                    if self._data.get(k) != v:
                        self._data[k] = v
                        need_save = True
            if version < _SCHEMA_VERSION:
                self._data["schema"] = _SCHEMA_VERSION
                need_save = True

        # 锁外面写：save() 自己也要拿锁，threading.Lock 不可重入
        if need_save:
            self.save()

    def save(self) -> None:
        with _lock:
            tmp = config_path().with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(config_path())

    def get(self, key: str) -> Any:
        with _lock:
            return self._data.get(key, _DEFAULTS.get(key))

    def set(self, key: str, value: Any, autosave: bool = True) -> None:
        with _lock:
            if self._data.get(key) == value:
                return
            self._data[key] = value
        if autosave:
            self.save()

    def all(self) -> dict[str, Any]:
        with _lock:
            return dict(self._data)

    # ---- 使用频率 ----

    def record_use(self, entry_id: str) -> None:
        import time

        with _lock:
            usage = self._data.setdefault("usage", {})
            count, _ = usage.get(entry_id, (0, 0.0))
            usage[entry_id] = [count + 1, time.time()]
        # 频率变化不立即落盘，由调用方择机 save，避免每次启动都写文件

    def use_count(self, entry_id: str) -> int:
        with _lock:
            return self._data.get("usage", {}).get(entry_id, [0, 0.0])[0]

    def last_used(self, entry_id: str) -> float:
        with _lock:
            return self._data.get("usage", {}).get(entry_id, [0, 0.0])[1]


config = Config()
