"""扫描桌面与开始菜单，解析快捷方式，产出统一的应用条目。

设计要点：
  * 只读，绝不移动 / 复制 / 删除用户的任何文件。
  * 快捷方式解析走 IShellLinkW，比读字符串靠谱。
  * 扫描在子线程执行，COM 在各自线程内初始化。
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

log = logging.getLogger(__name__)

# CSIDL 常量（不依赖 pywin32 版本差异）
CSIDL_DESKTOP = 0x0000
CSIDL_COMMON_DESKTOPDIRECTORY = 0x0019
CSIDL_PROGRAMS = 0x0002
CSIDL_COMMON_PROGRAMS = 0x0017

_NOISE_PATTERN = re.compile(
    r"(uninstall|uninst|卸载|remove|readme|help|帮助|documentation|"
    r"license|licence|changelog|website|官网|主页|support|faq|"
    r"repair|setup|install|logger|日志)",
    re.IGNORECASE,
)

# 安装包常带的架构尾巴：python-3.12.4-amd64.exe 这种，双击是去安装，不是"打开"
_INSTALLER_PATTERN = re.compile(
    r"[-_ .](amd64|x64|x86|win64|win32|arm64)$", re.IGNORECASE
)

#: Dock 里的固定系统项。它们活在 Shell 命名空间里，磁盘上没有对应的 .lnk，
#: 扫描自然扫不到——但"打开此电脑""清空回收站"是最高频的动作之一，
#: 与其让人去面板里翻，不如直接钉在 Dock 上。
#: (条目 id, 显示名, Shell 命名空间路径)
SPECIAL_ENTRIES: tuple[tuple[str, str, str], ...] = (
    ("special:computer", "此电脑",
     "::{20D04FE0-3AEA-1069-A2D8-08002B30309D}"),
    ("special:recycle", "回收站",
     "::{645FF040-5081-101B-9F08-00AA002F954E}"),
)

# 开始菜单里这几个目录装的是系统工具（磁盘清理、注册表编辑器、放大镜…），
# 不是"应用"。整目录跳过，比挨个拉黑名字准得多。
_SKIP_DIRS = {
    "system tools", "accessibility", "administrative tools", "maintenance",
    "startup", "windows kits", "windows powershell", "windows system",
    "系统工具", "辅助功能", "辅助工具", "管理工具", "启动", "维护",
}

_SKIP_EXT = {
    ".ini", ".db", ".tmp", ".log", ".url2", ".lnk2",
    ".crdownload", ".part", ".bay", ".!ut",
}

# 快捷方式指向这些，才算"能双击启动的东西"
_EXEC_EXT = {".exe", ".com", ".bat", ".cmd", ".msc", ".cpl"}

# 这些 exe 要么一闪而过、要么只是别人的宿主，双击它们什么都不会发生。
# 解释器本体（python.exe）也在这里：它要开着终端才有意义，不是拿来点的。
_HOST_EXE = {
    "hh.exe", "cmd.exe", "conhost.exe", "rundll32.exe", "dllhost.exe",
    "wscript.exe", "cscript.exe", "regsvr32.exe", "msiexec.exe",
    # 解释器本体：开着终端才有意义，不是拿来双击的（IDLE 也是它们起的）
    "python.exe", "pythonw.exe", "python3.exe", "py.exe",
    # 控制面板外壳与步骤记录器：躺在开始菜单里，但不是"应用"
    "control.exe", "psr.exe", "javacpl.exe",
}


@dataclass
class AppEntry:
    id: str
    name: str
    path: str          # 磁盘上的原始条目路径（.lnk / .exe / 文件 / 文件夹）
    target: str        # 快捷方式指向的真实目标，非快捷方式时等于 path
    args: str = ""
    workdir: str = ""
    kind: str = "app"  # app | file | folder | url
    source: str = "desktop"  # desktop | startmenu
    icon_source: str = ""    # 用于提取图标的路径
    description: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "target": self.target,
            "args": self.args,
            "workdir": self.workdir,
            "kind": self.kind,
            "source": self.source,
            "iconSource": self.icon_source,
            "description": self.description,
        }


def special_entries() -> list[AppEntry]:
    """Dock 用的固定系统项（此电脑、回收站）。

    kind 标成 "special"：面板的分类里没有这一档，它们不会混进应用列表，
    只在 Dock 最左边出现。
    """
    from .icons import CLSID_PREFIX

    return [
        AppEntry(
            id=eid,
            name=name,
            path=ns,
            target=ns,
            kind="special",
            source="special",
            icon_source=CLSID_PREFIX + ns,
            description=name,
        )
        for eid, name, ns in SPECIAL_ENTRIES
    ]


def make_id(kind: str, key: str) -> str:
    raw = f"{kind}|{key}".lower()
    return hashlib.md5(raw.encode("utf-8", "ignore")).hexdigest()[:16]


# ---------------------------------------------------------------- 目录定位

def _known_dir(csidl: int) -> Path | None:
    try:
        import pythoncom
        from win32com.shell import shell

        pythoncom.CoInitialize()
        try:
            return Path(shell.SHGetFolderPath(0, csidl, None, 0))
        finally:
            pythoncom.CoUninitialize()
    except Exception as exc:  # pragma: no cover - 环境缺 pywin32 时退回环境变量
        log.warning("SHGetFolderPath 失败(%s)，退回环境变量", exc)

    home = Path.home()
    fallback = {
        CSIDL_DESKTOP: home / "Desktop",
        CSIDL_COMMON_DESKTOPDIRECTORY: Path(
            os.environ.get("PUBLIC", "C:/Users/Public")
        ) / "Desktop",
        CSIDL_PROGRAMS: Path(
            os.environ.get("APPDATA", str(home))
        ) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        CSIDL_COMMON_PROGRAMS: Path(
            os.environ.get("PROGRAMDATA", "C:/ProgramData")
        ) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    }
    return fallback.get(csidl)


def source_dirs(cfg) -> list[tuple[Path, str]]:
    """返回 (目录, source 标记) 列表。"""
    out: list[tuple[Path, str]] = []
    plan = [
        (cfg.get("source_desktop"), CSIDL_DESKTOP, "desktop"),
        (cfg.get("source_common_desktop"), CSIDL_COMMON_DESKTOPDIRECTORY, "desktop"),
        (cfg.get("source_start_menu"), CSIDL_PROGRAMS, "startmenu"),
        (cfg.get("source_common_start_menu"), CSIDL_COMMON_PROGRAMS, "startmenu"),
    ]
    for enabled, csidl, tag in plan:
        if not enabled:
            continue
        d = _known_dir(csidl)
        if d and d.exists():
            out.append((d, tag))
    return out


# ---------------------------------------------------------------- 快捷方式

_LNK_FAIL_WARNED = False


def resolve_lnk(lnk: str) -> dict:
    """解析 .lnk，返回 target/args/workdir/icon 信息；失败返回空 dict。"""
    try:
        import pythoncom
        from win32com.shell import shell, shellcon

        pythoncom.CoInitialize()
        try:
            link = pythoncom.CoCreateInstance(
                shell.CLSID_ShellLink,
                None,
                pythoncom.CLSCTX_INPROC_SERVER,
                shell.IID_IShellLinkW,
            )
            link.QueryInterface(pythoncom.IID_IPersistFile).Load(lnk, 0)
            raw_path = shellcon.SLGP_RAWPATH if hasattr(shellcon, "SLGP_RAWPATH") else 4
            target = link.GetPath(raw_path)[0]
            args = link.GetArguments() or ""
            workdir = link.GetWorkingDirectory() or ""
            icon_path, icon_index = link.GetIconLocation()
            desc = link.GetDescription() or ""
            return {
                "target": target,
                "args": args,
                "workdir": workdir,
                "icon_path": icon_path,
                "icon_index": icon_index,
                "description": desc,
            }
        finally:
            pythoncom.CoUninitialize()
    except Exception as exc:
        # 单个快捷方式解析失败很常见（目标被删掉、权限不足），逐条刷屏没意义。
        # 但**整体**失败必须让人看见：pythoncom 一旦 import 不了，所有 .lnk 都走
        # 这里被丢弃，列表会凭空少一大半却安静得像什么都没发生（打包成 exe 时
        # 真的发生过：145 条只剩 84 条，开始菜单几乎全空）。所以第一次记 warning。
        global _LNK_FAIL_WARNED
        if not _LNK_FAIL_WARNED:
            _LNK_FAIL_WARNED = True
            log.warning("解析快捷方式失败（后续同类只记 debug）：%s | %s: %s",
                        lnk, type(exc).__name__, exc)
        else:
            log.debug("解析快捷方式失败 %s: %s", lnk, exc)
        return {}


def resolve_url(path: str) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            line = line.strip()
            if line.upper().startswith("URL="):
                return line[4:].strip()
    except OSError:
        pass
    return ""


# ---------------------------------------------------------------- 目标判定

def pe_subsystem(path: str) -> int:
    """读 PE 头的 Subsystem：2=窗口程序，3=控制台程序，读不出来返回 -1。

    只翻开头几百个字节，不加载、不执行这个 exe。
    """
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
        if head[:2] != b"MZ":
            return -1
        pe = int.from_bytes(head[0x3C:0x40], "little")
        if head[pe : pe + 4] != b"PE\0\0":
            return -1
        opt = pe + 24  # 4 字节签名 + 20 字节 COFF 头
        magic = int.from_bytes(head[opt : opt + 2], "little")
        if magic not in (0x10B, 0x20B):  # PE32 / PE32+
            return -1
        # Subsystem 在可选头里的偏移，PE32 与 PE32+ 都是 68
        return int.from_bytes(head[opt + 68 : opt + 70], "little")
    except (OSError, ValueError, IndexError):
        return -1


def is_console_exe(path: str) -> bool:
    return pe_subsystem(path) == 3


def _target_kind(target: str, source: str, cfg) -> str | None:
    """快捷方式指向的东西决定它算哪一类 —— 而不是它自己是 .lnk 就算应用。

    之前一律按"应用"收，于是开始菜单里的帮助文档（Python 3.12 Manuals
    指向 index.html）、指向文件夹的快捷方式，全都混进了"应用"分类。
    """
    t = Path(target)
    ext = t.suffix.lower()
    if ext in _EXEC_EXT:
        return "app"
    if t.is_dir():
        # 指向文件夹的快捷方式就是文件夹，不是应用
        return "folder" if (source == "desktop" and cfg.get("include_folders")) else None
    # 文档之类的目标：只有桌面上的才留着，开始菜单里塞的文档快捷方式没意义
    return "file" if (source == "desktop" and cfg.get("include_files")) else None


def _is_non_app_exe(target: str, source: str, cfg) -> bool:
    """这类 exe 收进来只会占位置。"""
    name = Path(target).name.lower()
    if name in _HOST_EXE:
        return True
    # 控制台程序（python.exe / node.exe / powershell.exe …）只过滤开始菜单里的：
    # 用户自己摆在桌面上的，多半是有意要用的，别替他扔
    if source == "startmenu" and cfg.get("hide_console_apps") is not False:
        return is_console_exe(target)
    return False


# ---------------------------------------------------------------- 扫描

def _entry_from_path(p: Path, source: str, cfg) -> AppEntry | None:
    if p.name.startswith("~$") or p.name.startswith("."):
        return None

    suffix = p.suffix.lower()
    if suffix in _SKIP_EXT:
        return None

    hide_noise = cfg.get("hide_uninstallers")
    stem = p.stem if suffix != "" else p.name
    if hide_noise and _INSTALLER_PATTERN.search(stem):
        return None

    if suffix == ".lnk":
        info = resolve_lnk(str(p))
        target = info.get("target", "")
        if hide_noise and _NOISE_PATTERN.search(stem):
            return None
        # 快捷方式指向自身目录的“卸载”类目标也过滤
        if not target:
            return None
        kind = _target_kind(target, source, cfg)
        if kind is None or (kind == "app" and _is_non_app_exe(target, source, cfg)):
            return None
        icon_source = info.get("icon_path") or target
        if not icon_source:
            icon_source = str(p)
        return AppEntry(
            id=make_id("lnk", str(p)),
            name=stem,
            path=str(p),
            target=target,
            args=info.get("args", ""),
            workdir=info.get("workdir", ""),
            kind=kind,
            source=source,
            icon_source=icon_source,
            description=info.get("description", ""),
        )

    if suffix == ".url":
        if hide_noise and _NOISE_PATTERN.search(stem):
            return None
        return AppEntry(
            id=make_id("url", str(p)),
            name=stem,
            path=str(p),
            target=resolve_url(str(p)),
            kind="url",
            source=source,
            icon_source=str(p),
        )

    if suffix == ".exe":
        if hide_noise and _NOISE_PATTERN.search(stem):
            return None
        if _is_non_app_exe(str(p), source, cfg):
            return None
        return AppEntry(
            id=make_id("exe", str(p)),
            name=stem,
            path=str(p),
            target=str(p),
            kind="app",
            source=source,
            icon_source=str(p),
        )

    if p.is_dir():
        if not cfg.get("include_folders") or source != "desktop":
            return None
        return AppEntry(
            id=make_id("dir", str(p)),
            name=p.name,
            path=str(p),
            target=str(p),
            kind="folder",
            source=source,
            icon_source=str(p),
        )

    # 普通文件：只在桌面来源时收纳，且受开关控制
    if source != "desktop" or not cfg.get("include_files"):
        return None
    return AppEntry(
        id=make_id("file", str(p)),
        name=p.name,
        path=str(p),
        target=str(p),
        kind="file",
        source=source,
        icon_source=str(p),
    )


def scan(cfg, max_depth: int = 3) -> list[AppEntry]:
    entries: list[AppEntry] = []
    seen: set[str] = set()

    _dirs = source_dirs(cfg)
    # 打包成 exe 后扫到的条目数一度比源码版少一大截（145 -> 84），
    # 根因是某个扫描来源没被解析出来。把来源和存在性打出来，
    # 下次再有数量对不上，一眼就能看出是哪个目录掉了。
    log.info("扫描来源：%s",
             [(tag, str(d), d.exists()) for d, tag in _dirs])

    for directory, tag in _dirs:
        _n0 = len(entries)
        base_depth = len(directory.parts)
        try:
            walker: Iterable[tuple[Path, list[str], list[str]]] = os.walk(directory)
            for root, dirnames, filenames in walker:
                root_p = Path(root)
                depth = len(root_p.parts) - base_depth
                if depth >= max_depth:
                    dirnames[:] = []
                dirnames[:] = [
                    d for d in dirnames
                    if not d.startswith(".") and not d.startswith("~$")
                    and d.lower() not in _SKIP_DIRS
                ]

                for name in filenames:
                    entry = _entry_from_path(root_p / name, tag, cfg)
                    if entry and entry.id not in seen:
                        seen.add(entry.id)
                        entries.append(entry)

                if depth < max_depth:
                    for name in list(dirnames):
                        sub = root_p / name
                        if tag == "desktop" and depth == 0:
                            entry = _entry_from_path(sub, tag, cfg)
                            if entry and entry.id not in seen:
                                seen.add(entry.id)
                                entries.append(entry)
        except OSError as exc:
            log.warning("扫描 %s 失败: %s", directory, exc)
        log.info("  来源 %s 新增 %d 条：%s", tag, len(entries) - _n0, directory)

    # 目标相同、名称相同的重复项去重（桌面与开始菜单常有交集）
    dedup: dict[str, AppEntry] = {}
    order: list[str] = []
    for e in entries:
        key = (e.target or e.path).lower() if e.kind in ("app", "url") else e.path.lower()
        if key in dedup:
            existing = dedup[key]
            # 桌面来源优先展示
            if existing.source == "startmenu" and e.source == "desktop":
                dedup[key] = e
            continue
        dedup[key] = e
        order.append(key)

    result = [dedup[k] for k in order]
    log.info("扫描完成：去重前 %d 条，去重后 %d 条", len(entries), len(result))
    return result
