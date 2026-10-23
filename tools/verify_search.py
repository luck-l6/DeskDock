"""离线验证搜索与分类过滤（不起窗口、不动桌面图标）。

    python tools/verify_search.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt5.QtCore import QCoreApplication  # noqa: E402

from deskdock.config import config  # noqa: E402
from deskdock.model import AppFilterModel, AppModel  # noqa: E402
from deskdock.scanner import scan  # noqa: E402


def main() -> int:
    app = QCoreApplication(sys.argv)
    entries = scan(config)
    model = AppModel()
    model.set_entries(entries)
    filt = AppFilterModel()
    filt.setSourceModel(model)

    from deskdock.pinyin import warmup

    t = time.perf_counter()
    warmup()
    print(f"[pinyin] 建表 { (time.perf_counter()-t)*1000:.1f} ms")

    cats = ["all", "recent", "app", "file", "folder"]
    print("\n== 分类计数 ==")
    for c in cats:
        filt.setCategory("all")
        filt.setCategory(c)
        print(f"  {c:7s} {filt.rowCount():4d}")

    queries = ["wx", "weixin", "tx", "jsq", "jsb", "kzmb", "dn", "wps",
               "vs", "code", "qq", "chrome", "7z", "微", "pdf", "xiazai", "xz"]
    print("\n== 拼音/原文搜索（分类=全部，搜索时应跨分类）==")
    filt.setCategory("all")
    for q in queries:
        filt.setQuery("")
        filt.setQuery(q)
        n = filt.rowCount()
        names = []
        for i in range(min(4, n)):
            idx = filt.index(i, 0)
            names.append(str(filt.data(idx, AppModel.NameRole)))
        t = time.perf_counter()
        filt.setQuery("")
        filt.setQuery(q)
        dt = (time.perf_counter() - t) * 1000
        print(f"  {q:8s} {n:4d} 项  {dt:5.1f} ms  {names}")

    # 搜索态是否真的跳过了分类
    print("\n== 搜索时忽略分类 ==")
    filt.setCategory("folder")
    filt.setQuery("")
    base = filt.rowCount()
    filt.setQuery("wx")
    print(f"  文件夹分类 {base} 项，搜 wx -> {filt.rowCount()} 项")
    print(f"  searching = {filt.searching}")

    # 常用：只看打开过的应用
    print("\n== 常用分类抽样 ==")
    filt.setQuery("")
    filt.setCategory("recent")
    for i in range(min(10, filt.rowCount())):
        idx = filt.index(i, 0)
        kind = str(filt.data(idx, AppModel.KindRole))
        name = str(filt.data(idx, AppModel.NameRole))
        uses = int(filt.data(idx, AppModel.UseCountRole) or 0)
        print(f"  {kind:7s} x{uses:<3d} {name}")

    print("\n== 常用分类里不应出现的类型 ==")
    kinds = set()
    for i in range(filt.rowCount()):
        kinds.add(str(filt.data(filt.index(i, 0), AppModel.KindRole)))
    print("  ", sorted(kinds))
    return 0


if __name__ == "__main__":
    sys.exit(main())
