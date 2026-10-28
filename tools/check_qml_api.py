"""核对 QML 里调用的 Python 接口是不是真的注册了。

为什么要有它（2026-10-28 事故的教训）
------------------------------------
`launchById` 上方少了 `@pyqtSlot`（装饰器被误放到内部方法上），于是 QML 里
`controller.launchById(id)` 调了个不存在的方法——**不报错、不崩溃、日志里
一条记录都没有**，表现只是"点网格里的应用没反应"。排查花了很久，因为从
现象上看什么都看不出来。

规则很简单：QML 只能调到 meta-object 里注册过的东西（`@pyqtSlot` 装饰的
方法、`pyqtProperty` 的属性、`pyqtSignal` 的信号）。漏一个装饰器就是静默失效。
而 **pyqtProperty 的 setter 不会自动成为可调用方法**，QML 里显式调用
`controller.setXxx()` 也得自己补 `@pyqtSlot`。

用法：python tools/check_qml_api.py
退出码 0 = 全部注册到位；1 = 有漏网的（此时会列出名字）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# QML 里 context property 的名字 -> Python 类名
TARGETS = [
    ("controller", "Controller"),
    ("appModel", "AppFilterModel"),
    ("rawModel", "AppModel"),
]


def main() -> int:
    qml_dir = ROOT / "deskdock" / "qml"
    qml = "\n".join(p.read_text(encoding="utf-8")
                    for p in sorted(qml_dir.glob("*.qml")))

    from PyQt5.QtWidgets import QApplication  # noqa: F401  (必须先有 QApplication)

    app = QApplication(sys.argv)  # noqa: F841
    import deskdock.app as A

    bad = 0
    for obj, cls_name in TARGETS:
        cls = getattr(A, cls_name, None)
        if cls is None:
            print(f"{obj}: 找不到类 {cls_name}，跳过")
            continue
        used = sorted(set(re.findall(rf"\b{obj}\.([a-zA-Z_]+)", qml)))
        mo = cls.staticMetaObject
        methods = {bytes(mo.method(i).name()).decode()
                   for i in range(mo.methodCount())}
        props = {str(mo.property(i).name()) for i in range(mo.propertyCount())}
        missing = [n for n in used if n not in methods and n not in props]
        flag = "OK" if not missing else "缺失"
        print(f"{obj} ({cls_name}): QML 用到 {len(used)} 个 -> {flag}"
              + (f" {missing}" if missing else ""))
        bad += len(missing)

    if bad:
        print(f"\n共 {bad} 个名字 QML 调不到：给它们补 @pyqtSlot / pyqtProperty")
        return 1
    print("\n全部注册到位")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
