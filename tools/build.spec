# -*- mode: python ; coding: utf-8 -*-
"""打包 DeskDock 为独立 exe。

为什么需要它：程序常驻接管桌面显示层，而源码版依赖"系统 Python 一直存在、
desk-space 目录不被挪走"——用户升级或卸载 Python 就会打不开，连带桌面图标
恢复也失效。打包成 exe 后不依赖任何外部 Python。

一个反复踩到的坑（改动前请先读这段）：
  Qt 的 QML 插件（QtQuick.2 / QtQuick.Controls.2 / QtGraphicalEffects）**不要
  手动拷**。PyInstaller 的 PyQt5 hook 已经把它们放进了
  `_internal/PyQt5/Qt5/qml`，再拷一份到别处并指认过去，引擎会看到两份
  QtQuick.Controls，于是刷一屏
      Cannot install type 'Button' into protected module 'QtQuick.Controls'
  并且 Panel.qml 直接加载失败（根对象 0 -> 0，面板全白）。
  正确做法是：只指认 hook 放好的那一份——由 app.py 在 QApplication 构造前
  把 QML2_IMPORT_PATH 设到 `_MEIPASS/PyQt5/Qt5/qml`（见 app.py 的 frozen 分支）。
  这里只需要把程序自己的 QML 和资源带进去（deskdock/qml）。

用法：python -m PyInstaller tools/build.spec --noconfirm
产物：dist/DeskDock.exe（单文件，双击即用、可随手拷给别人）
     想要启动更快的目录版（免解压），把下面 MODE 改成 "onedir"。

单文件模式的代价：每次启动要把 140MB 解到 %TEMP%\\_MEIxxxxx，首次自启会慢
一两秒。它是开机自启的常驻程序，一次性成本，换来的是"一个文件走天下"。
"""

import glob
import importlib.util
import os

# spec 里的相对路径是相对于 spec 自己所在的目录（tools/），不是当前工作目录。
# 一律用 SPECPATH 锚回项目根，否则从别的目录执行打包就会找不到 main.py。
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

# Qt 的 QML 插件由 PyQt5 hook 自动收集，这里只带程序自己的 QML 与资源。
datas = [(os.path.join(ROOT, "deskdock", "qml"), "deskdock/qml")]

# pywin32 的坑：pythoncom / pywintypes 在新版本里是 .py shim，真正的实现
# pythoncom3XX.dll 躺在 site-packages/pywin32_system32/ 下。PyInstaller 会把这个
# 目录原样搬进包里，但冻结后 shim 按包内路径找不到它 —— import pythoncom 直接
# ImportError。而解析 .lnk 全靠 pythoncom，于是**所有快捷方式被静默丢弃**
# （实测 145 条只剩 84 条，开始菜单几乎全空，且没有任何报错）。
# 把这两个 DLL 提到包的根目录（DLL 搜索路径上）即可。
binaries = []
_pywin32_dlls = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(
        importlib.util.find_spec("pywintypes").origin))),
    "pywin32_system32")
for _dll in glob.glob(os.path.join(_pywin32_dlls, "*.dll")):
    binaries.append((_dll, "."))
if not binaries:
    raise SystemExit(f"没找到 pywin32 的 DLL：{_pywin32_dlls}")

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "PyQt5.QtQml", "PyQt5.QtQuick", "PyQt5.QtNetwork", "PyQt5.sip",
        # pywin32：解析 .lnk 全靠它。win32timezone 是被 pythoncom 间接 import 的，
        # 静态分析看不到，漏掉它就会 No module named 'win32timezone'，
        # 于是每个快捷方式都解析失败、被静默丢弃（列表凭空少掉一小半）。
        "pythoncom", "pywintypes", "win32timezone",
        "win32com.shell", "win32com.shellcon",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc", "doctest", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

MODE = "onedir"

exe = EXE(
    pyz,
    a.scripts,
    # 单文件：把二进制和资源一起塞进 exe，启动时解到临时目录
    (a.binaries + a.datas) if MODE == "onefile" else [],
    [],
    exclude_binaries=(MODE != "onefile"),
    name="DeskDock",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # 纯窗口程序：常驻托盘，不能有黑色控制台一闪而过。
    # 排错靠 %LOCALAPPDATA%\DeskDock\deskdock.log，不要临时改回 console=True 就交付。
    console=False,
    disable_windowed_traceback=False,
)

if MODE != "onefile":
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="DeskDock",
    )
