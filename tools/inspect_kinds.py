"""诊断分类判定：把每条 app/url 的真实目标打出来，看谁被误判、谁被漏掉。

    python tools/inspect_kinds.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deskdock.config import config  # noqa: E402
from deskdock.scanner import scan, source_dirs, resolve_lnk  # noqa: E402

WATCH = ["qq", "pycharm", "python", "微信", "wechat", "jetbrains", "chrome", "code"]


def main() -> int:
    print("== 扫描目录 ==")
    for d, tag in source_dirs(config):
        print(f"  {tag:10s} {d}")

    entries = scan(config)
    print(f"\n== 共 {len(entries)} 条 ==")

    print("\n== kind=app / url 的真实目标后缀 ==")
    from collections import Counter

    c: Counter[str] = Counter()
    odd: list[tuple[str, str, str]] = []
    for e in entries:
        if e.kind not in ("app", "url"):
            continue
        t = (e.target or "").lower()
        ext = Path(t).suffix if "." in Path(t).name else "<无后缀>"
        c[ext] += 1
        if ext not in (".exe", ".url", "") and not ext.startswith("<"):
            odd.append((e.name, e.target, e.source))
    for ext, n in c.most_common():
        print(f"  {ext:12s} {n}")
    print("\n  目标不是 exe 的 app（可疑）：")
    for name, tgt, src in odd[:40]:
        print(f"    [{src}] {name} -> {tgt}")

    print("\n== 关注的关键词 ==")
    low = [(e.name.lower(), e) for e in entries]
    for kw in WATCH:
        hits = [e for n, e in low if kw in n]
        print(f"  {kw}: 命中 {len(hits)} 条")
        for e in hits[:6]:
            print(f"      [{e.kind}/{e.source}] {e.name} -> {e.target or e.path}")

    print("\n== 磁盘上确实存在、但没进列表的快捷方式 ==")
    seen_paths = {e.path.lower() for e in entries}
    for d, tag in source_dirs(config):
        for p in Path(d).rglob("*.lnk"):
            if p.name.lower() in seen_paths:
                continue
            for kw in WATCH:
                if kw in p.name.lower():
                    info = resolve_lnk(str(p))
                    print(f"  [{tag}] {p.name}")
                    print(f"      路径 {p}")
                    print(f"      解析 {info}")
                    break
    return 0


if __name__ == "__main__":
    sys.exit(main())
