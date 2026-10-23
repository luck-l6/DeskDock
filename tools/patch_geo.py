import io

p = 'deskdock/app.py'
s = io.open(p, encoding='utf-8').read()

old = '''    def _fit_to_cursor_screen(self) -> None:
        """面板铺满光标所在的显示器，多屏场景下才不会跑偏。"""
        screen = QGuiApplication.screenAt(QCursor.pos())'''
new = '''    def _fit_to_cursor_screen(self) -> None:
        """面板铺满光标所在的显示器，多屏场景下才不会跑偏。"""
        screen = QGuiApplication.screenAt(QCursor.pos())
        log.debug("_fit: screenAt=%s", screen)'''
assert old in s
s = s.replace(old, new)

old2 = '''        for name, value in (("x", geo.x()), ("y", geo.y()),
                            ("width", geo.width()), ("height", geo.height())):'''
assert old2 in s
s = s.replace(old2, old2 + '''
            log.debug("_fit: %s=%s", name, value)''')

# 显示后实际几何
old3 = '''        self.panelVisibleChanged.emit(True)
        if self._settings:'''
new3 = '''        self.panelVisibleChanged.emit(True)
        try:
            from PyQt5.QtCore import QTimer

            def _dump():
                w = self._panel
                log.info("panel 实际几何 x=%s y=%s w=%s h=%s visible=%s",
                         w.property("x"), w.property("y"),
                         w.property("width"), w.property("height"),
                         w.property("visible"))

            QTimer.singleShot(600, _dump)
        except Exception:
            pass
        if self._settings:'''
assert old3 in s
s = s.replace(old3, new3)

io.open(p, 'w', encoding='utf-8').write(s)
print('ok')
