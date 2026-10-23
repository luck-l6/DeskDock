"""离线验证：手动拖拽排序 + 目录监听。

不抢单实例、不隐藏桌面图标、不改自启，只建一个 QCoreApplication 直接调
控制器里那两段逻辑（moveEntry / 排序键 / QFileSystemWatcher）。

用法：python tools/verify_order.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt5.QtCore import QCoreApplication, QFileSystemWatcher, QTimer  # noqa: E402

from deskdock.config import config  # noqa: E402
from deskdock.model import AppFilterModel, AppModel  # noqa: E402
from deskdock.scanner import scan  # noqa: E402


def check(cond: bool, label: str) -> bool:
    print(f"  [{'通过' if cond else '失败'}] {label}")
    return cond


def names(model: AppFilterModel, n: int = 6) -> list[str]:
    return [str(model.data(model.index(i, 0), AppModel.NameRole))
            for i in range(min(n, model.rowCount()))]


def main() -> int:
    app = QCoreApplication([])  # noqa: F841
    ok = True

    model = AppModel()
    model.set_entries(scan(config))
    proxy = AppFilterModel()
    proxy.setSourceModel(model)
    total = model.rowCount()

    print(f"扫描 {total} 条\n")

    # ---------------------------------------------------------- 手动排序
    print("== 手动拖拽排序 ==")
    config.set("sort_by", "manual", autosave=False)
    config.set("order", [e.id for e in model.all_entries()], autosave=False)
    model.reorder()

    before = names(proxy, 5)
    print(f"  拖之前 前5: {before}")

    # 把第 0 个拖到第 3 个位置
    dragged_id = str(proxy.data(proxy.index(0, 0), AppModel.IdRole))
    src = proxy.mapToSource(proxy.index(3, 0)).row()
    dst_from = model.row_of(dragged_id)
    model.move_row(dst_from, src)
    config.set("order", model.order_ids(), autosave=False)

    after = names(proxy, 5)
    print(f"  拖之后 前5: {after}")
    ok &= check(before[0] not in after[:1], "原第 1 项已离开首位")
    ok &= check(after[3] == before[0], f"'{before[0]}' 落在第 4 位")
    ok &= check([n for n in after if n != before[0]][:3] == before[1:4],
                "其余项相对顺序不变")

    # 重新扫描（模拟刷新）之后顺序要保住，新条目排末尾
    print("\n== 刷新后保持顺序 ==")
    entries = scan(config)
    fake = None
    for e in entries:
        if e.id == dragged_id:
            fake = e
            break
    if fake is not None:
        # 造一个"新装的软件"：复制一条并换个 id
        from dataclasses import replace
        fresh = replace(fake, id=fake.id + "__new", name="ZZ新装的软件")
        entries.append(fresh)
    model.set_entries(entries)
    after2 = names(proxy, 6)
    print(f"  刷新后 前6: {after2}")
    ok &= check(after2[3] == before[0], "刷新后手动顺序仍在")
    if fake is not None:
        pos = [str(model.data(model.index(i, 0), AppModel.NameRole))
               for i in range(proxy.rowCount())]
        ok &= check(pos[-1] == "ZZ新装的软件", "未排过序的新条目落在末尾")

    # ---------------------------------------------------------- 目录监听
    print("\n== 目录监听 ==")
    hits: list[str] = []

    def on_changed(path: str) -> None:
        hits.append(path)

    tmp = Path(tempfile.mkdtemp(prefix="deskdock_watch_"))
    w = QFileSystemWatcher([str(tmp)])
    w.directoryChanged.connect(on_changed)

    def step1() -> None:
        (tmp / "新建应用.lnk").write_text("x", encoding="utf-8")

    def step2() -> None:
        sub = tmp / "厂商目录"
        sub.mkdir()
        w.addPath(str(sub))
        (sub / "app.lnk").write_text("x", encoding="utf-8")

    def finish() -> None:
        nonlocal ok
        ok &= check(len(hits) >= 2, f"收到 {len(hits)} 次变更通知（新建文件 + 子目录内新建）")
        print(f"  通知路径: {[os.path.basename(p) for p in hits]}")
        w.removePath(str(tmp))
        try:
            for p in sorted(tmp.rglob("*"), reverse=True):
                p.unlink() if p.is_file() else p.rmdir()
            tmp.rmdir()
        except OSError:
            pass
        app.quit()

    QTimer.singleShot(200, step1)
    QTimer.singleShot(700, step2)
    QTimer.singleShot(1600, finish)
    QTimer.singleShot(4000, app.quit)

    t = time.perf_counter()
    app.exec_()
    print(f"\n  监听测试耗时 {time.perf_counter() - t:.1f}s")

    print("\n结论:", "全部通过" if ok else "有失败项")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
