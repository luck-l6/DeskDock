@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 优先用打包好的 exe：不依赖系统 Python，也不怕源码目录被挪。
rem 目录版（dist\DeskDock\DeskDock.exe）优先：启动 1.3 秒；
rem 单文件版 dist\DeskDock.exe 每次启动要先解压 55MB，实测 7.8 秒。
rem 要拷给别人时，把下面两段顺序颠倒即可（或直接用单文件版）。
set "EXE=%~dp0dist\DeskDock\DeskDock.exe"
if exist "%EXE%" (
  start "" "%EXE%"
  exit /b 0
)
set "EXE=%~dp0dist\DeskDock.exe"
if exist "%EXE%" (
  start "" "%EXE%"
  exit /b 0
)

rem 没有 exe 就退回源码方式。重装或升级过 Python 就改下面这一行。
set "PYW=C:\Users\15549\AppData\Local\Programs\Python\Python312\pythonw.exe"
if exist "%PYW%" goto run

where pythonw >nul 2>nul
if "%errorlevel%"=="0" (
  for /f "delims=" %%i in ('where pythonw') do set "PYW=%%i"
  goto run
)

echo.
echo  DeskDock 启动失败：既没有打包好的 exe，也找不到 Python。
echo.
echo  1) 打包 exe：python -m PyInstaller tools\build.spec --noconfirm
echo  2) 或者安装 Python 3.12，再改本文件里的 PYW 那一行
echo.
echo  桌面图标不会丢，也跟这个脚本无关：
echo  右键桌面 - 查看 - 显示桌面图标，随时能恢复。
echo.
pause
exit /b 1

:run
start "" "%PYW%" "main.py"
