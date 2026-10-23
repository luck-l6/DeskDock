"""Windows 桌面相关：隐藏系统桌面图标、定位桌面图层、开机自启。

关键设计：不动用户文件。桌面图标只是"不再由 Explorer 绘制"，
文件仍然完整地留在原来的目录里，随时可以恢复。
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes
from pathlib import Path

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

WM_SETTINGCHANGE = 0x001A
HWND_BROADCAST = 0xFFFF
SMTO_NORMAL = 0x0000
SHCNE_ASSOCCHANGED = 0x08000000
SHCNF_IDLIST = 0x0000

HKEY_CURRENT_USER = 0x80000001
KEY_SET_VALUE = 0x0002
KEY_QUERY_VALUE = 0x0001
REG_DWORD = 4
REG_SZ = 1

ADVANCED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUNONCE_KEY = r"Software\Microsoft\Windows\CurrentVersion\RunOnce"

user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = wintypes.HWND
user32.FindWindowExW.argtypes = [
    wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.SendMessageTimeoutW.restype = wintypes.LPARAM
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetParent.restype = wintypes.HWND
user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
user32.SetWindowPos.restype = wintypes.BOOL


# ------------------------------------------------------------ 注册表

def _set_dword(root: int, subkey: str, name: str, value: int) -> bool:
    handle = wintypes.HKEY()
    res = advapi32.RegCreateKeyExW(
        root, subkey, 0, None, 0, KEY_SET_VALUE | KEY_QUERY_VALUE, None,
        ctypes.byref(handle), None)
    if res != 0:
        log.warning("打开注册表失败 %s: %d", subkey, res)
        return False
    try:
        raw = ctypes.c_uint32(value)
        res = advapi32.RegSetValueExW(
            handle, name, 0, REG_DWORD, ctypes.byref(raw), ctypes.sizeof(raw))
        return res == 0
    finally:
        advapi32.RegCloseKey(handle)


def _get_dword(root: int, subkey: str, name: str) -> int | None:
    handle = wintypes.HKEY()
    if advapi32.RegOpenKeyExW(root, subkey, 0, KEY_QUERY_VALUE,
                              ctypes.byref(handle)) != 0:
        return None
    try:
        size = wintypes.DWORD(ctypes.sizeof(ctypes.c_uint32))
        value = ctypes.c_uint32()
        if advapi32.RegQueryValueExW(handle, name, None, None,
                                     ctypes.byref(value),
                                     ctypes.byref(size)) != 0:
            return None
        return value.value
    finally:
        advapi32.RegCloseKey(handle)


def _set_sz(root: int, subkey: str, name: str, value: str) -> bool:
    handle = wintypes.HKEY()
    if advapi32.RegCreateKeyExW(
            root, subkey, 0, None, 0, KEY_SET_VALUE, None,
            ctypes.byref(handle), None) != 0:
        return False
    try:
        raw = ctypes.create_unicode_buffer(value)
        res = advapi32.RegSetValueExW(
            handle, name, 0, REG_SZ, raw,
            (len(value) + 1) * ctypes.sizeof(ctypes.c_wchar))
        return res == 0
    finally:
        advapi32.RegCloseKey(handle)


def _delete_value(root: int, subkey: str, name: str) -> bool:
    handle = wintypes.HKEY()
    if advapi32.RegOpenKeyExW(root, subkey, 0, KEY_SET_VALUE,
                              ctypes.byref(handle)) != 0:
        return False
    try:
        return advapi32.RegDeleteValueW(handle, name) == 0
    finally:
        advapi32.RegCloseKey(handle)


# ------------------------------------------------------------ 桌面图标

WM_COMMAND = 0x0111
CMD_TOGGLE_DESKTOP_ICONS = 0x7402  # 桌面右键「显示桌面图标」发出的就是这条命令


def _notify_shell() -> None:
    """通知 Explorer 重新读取设置。"""
    shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
    user32.SendMessageTimeoutW(
        HWND_BROADCAST, WM_SETTINGCHANGE, 0,
        ctypes.c_wchar_p("Environment"),
        SMTO_NORMAL, 500, None)


def _icons_listview() -> int:
    """桌面图标所在的 SysListView32 控件句柄。"""
    dv = find_shell_defview()
    if not dv:
        return 0
    return int(user32.FindWindowExW(dv, None, "SysListView32", None) or 0)


def desktop_icons_visible() -> bool:
    """以运行时状态为准，注册表只是兜底。

    只改 HideIcons 注册表并不会即时生效——Explorer 在运行期间根本不去读它。
    """
    lv = _icons_listview()
    if lv:
        return bool(user32.IsWindowVisible(lv))
    v = _get_dword(HKEY_CURRENT_USER, ADVANCED_KEY, "HideIcons")
    return v in (0, None)


def set_desktop_icons_visible(visible: bool) -> bool:
    """显示 / 隐藏系统桌面图标。文件不动。

    运行时通过给 SHELLDLL_DefView 发 0x7402 命令切换（和桌面右键菜单同一个命令）；
    同时写注册表，保证 Explorer 重启后仍然保持。
    """
    dv = find_shell_defview()
    ok = True
    if dv:
        if desktop_icons_visible() != visible:
            r = user32.SendMessageTimeoutW(
                dv, WM_COMMAND, CMD_TOGGLE_DESKTOP_ICONS, 0,
                SMTO_NORMAL, 500, None)
            ok = bool(r)
    else:
        log.warning("未找到桌面视图窗口，只能改注册表")
        ok = False

    # 注册表让 Explorer 下次启动时保持这个状态
    if not _set_dword(HKEY_CURRENT_USER, ADVANCED_KEY, "HideIcons",
                      0 if visible else 1):
        log.warning("写入 HideIcons 失败")
    _notify_shell()
    return ok


# ------------------------------------------------------------ 图标恢复兜底
#
# 隐藏桌面图标是写进注册表的（HideIcons=1），进程一旦崩溃或被强杀，
# 没有任何代码会去把它改回来 —— 桌面图标就这么消失了，而托盘也跟着
# 进程一起没了，用户只能自己摸索「右键桌面 → 查看 → 显示桌面图标」。
# 更糟的一种：用户关掉开机自启后重启电脑，图标依然隐藏，而且再也没有
# 程序会恢复它。这里用三道保险把「一切可逆」真正兑现。

RESTORE_RUNONCE_NAME = "DeskDockRestoreIcons"

# 兜底命令**刻意不含 Python、不含任何文件路径**。
#
# 早期这里埋的是 `pythonw main.py --restore-icons`。问题是：需要兜底的时刻恰恰
# 就是"程序起不来"的时刻——Python 被卸载或升了级、desk-space 目录被挪走，
# 这条命令必然失败，而它本该是最后一道保险。一个接管桌面的常驻程序，
# 不能把自己的恢复路径押在"用户别动我的运行环境"上。
#
# 所以改成纯 cmd 内建命令 + 系统自带的 reg.exe：
#   1. reg add 把 HideIcons 写回 0（uninstall 脚本改不掉的也是这个值）
#   2. 重启 Explorer —— 只改注册表不会即时生效，运行中的 Explorer 不去读它，
#      必须让它重新启动才会按新值绘制图标
# 整串不含引号（注册表路径里没有空格），避免 cmd /c 的引号嵌套踩坑。
RESTORE_CMD = (
    r"cmd.exe /c reg add "
    r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced "
    r"/v HideIcons /t REG_DWORD /d 0 /f "
    r"& taskkill /f /im explorer.exe & start explorer.exe"
)


def _emergency_restore() -> None:
    """纯 ctypes 的应急恢复，一行 Python 对象都不碰。

    给「未处理异常过滤器」用的：那种时刻解释器可能已经处于损坏状态，
    任何 Python 层调用都可能二次崩溃。所以这里只做两件事——发 0x7402
    把图标切回来，把注册表改回 0。
    """
    try:
        progman = user32.FindWindowW("Progman", "Program Manager")
        dv = 0
        if progman:
            dv = user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
        if not dv:
            res = wintypes.HWND()

            @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def _enum(hwnd, _lp):
                found = user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None)
                if found:
                    res.value = found
                    return False
                return True

            user32.EnumWindows(_enum, 0)
            dv = res.value
        if dv:
            user32.SendMessageTimeoutW(dv, WM_COMMAND, CMD_TOGGLE_DESKTOP_ICONS,
                                       0, SMTO_NORMAL, 500, None)
        _set_dword(HKEY_CURRENT_USER, ADVANCED_KEY, "HideIcons", 0)
    except Exception:
        pass


def arm_restore_fallback() -> bool:
    """埋一条 RunOnce：下次登录若 DeskDock 没能自己起来，就自动恢复图标。

    只要程序活着就一直埋着；正常退出时才撤掉。这样无论是崩溃、被强杀，
    还是用户关掉自启后重启，图标都还能自己回来。

    命令用的是 RESTORE_CMD（纯 cmd），不依赖 Python 是否存在。
    """
    return _set_sz(HKEY_CURRENT_USER, RUNONCE_KEY,
                   RESTORE_RUNONCE_NAME, RESTORE_CMD)


def disarm_restore_fallback() -> bool:
    return _delete_value(HKEY_CURRENT_USER, RUNONCE_KEY, RESTORE_RUNONCE_NAME)


def restore_fallback_armed() -> bool:
    handle = wintypes.HKEY()
    if advapi32.RegOpenKeyExW(HKEY_CURRENT_USER, RUNONCE_KEY, 0,
                              KEY_QUERY_VALUE, ctypes.byref(handle)) != 0:
        return False
    try:
        return advapi32.RegQueryValueExW(handle, RESTORE_RUNONCE_NAME, None,
                                         None, None, None) == 0
    finally:
        advapi32.RegCloseKey(handle)


def install_crash_restore_hook() -> None:
    """注册未处理异常过滤器：进程硬崩溃时先把图标还回去。

    atexit 只覆盖正常退出路径，而 Qt 在 native 层 abort 时根本不走 Python。
    这是最后一道保险。
    """
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        FILTER = ctypes.WINFUNCTYPE(wintypes.LONG, ctypes.POINTER(ctypes.c_void_p))
        k32.SetUnhandledExceptionFilter.restype = FILTER

        @FILTER
        def _filter(_info):
            _emergency_restore()
            return 1  # EXCEPTION_EXECUTE_HANDLER：让进程安静退出

        k32.SetUnhandledExceptionFilter.argtypes = [FILTER]
        k32.SetUnhandledExceptionFilter(_filter)
    except Exception:
        pass


# ------------------------------------------------------------ 桌面图层

def find_shell_defview() -> int:
    """找到承载桌面图标的 SHELLDLL_DefView 窗口句柄。

    Win10/11 上它可能挂在 Progman 下，也可能挂在 WorkerW 下（多显示器）。
    先发 0x052C 触发系统生成 WorkerW，再逐层查找。
    """
    progman = user32.FindWindowW("Progman", "Program Manager")
    if not progman:
        progman = user32.FindWindowW("Progman", None)
    if not progman:
        return 0

    defview = user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
    if defview:
        return defview

    user32.SendMessageTimeoutW(progman, 0x052C, 0, 0, SMTO_NORMAL, 300, None)

    result = wintypes.HWND()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd, _lparam):
        if user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
            result.value = user32.FindWindowExW(
                hwnd, None, "SHELLDLL_DefView", None)
            return False
        return True

    user32.EnumWindows(_enum, 0)
    return int(result.value or 0)


def desktop_parent_hwnd() -> int:
    return find_shell_defview()


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    if hwnd and user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return rect.left, rect.top, rect.right, rect.bottom
    return 0, 0, 0, 0


def set_bottommost(hwnd: int) -> bool:
    """把窗口压到 Z 序最底层，只有桌面露出来时用户才看得到它。"""
    HWND_BOTTOM = 1
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOACTIVATE = 0x0010
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    return bool(user32.SetWindowPos(
        hwnd, wintypes.HWND(HWND_BOTTOM), 0, 0, 0, 0,
        SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE))


def attach_to_desktop(child_hwnd: int) -> bool:
    """把窗口挂到桌面图层下，使其随 Win+D 一起出现且不被普通窗口盖住。"""
    parent = desktop_parent_hwnd()
    if not parent:
        log.warning("未找到桌面图层，胶囊降级为独立置底窗口")
        return False
    prev = user32.SetParent(child_hwnd, parent)
    return prev != 0 or ctypes.get_last_error() == 0


# ------------------------------------------------------------ 开机自启

def _startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    here = Path(__file__).resolve().parent.parent
    main_py = here / "main.py"
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" "{main_py}"'


def set_run_at_startup(enabled: bool) -> bool:
    if enabled:
        return _set_sz(HKEY_CURRENT_USER, RUN_KEY, "DeskDock",
                       _startup_command())
    return _delete_value(HKEY_CURRENT_USER, RUN_KEY, "DeskDock")


def run_at_startup() -> bool:
    handle = wintypes.HKEY()
    if advapi32.RegOpenKeyExW(HKEY_CURRENT_USER, RUN_KEY, 0, KEY_QUERY_VALUE,
                              ctypes.byref(handle)) != 0:
        return False
    try:
        return advapi32.RegQueryValueExW(handle, "DeskDock", None, None,
                                         None, None) == 0
    finally:
        advapi32.RegCloseKey(handle)
