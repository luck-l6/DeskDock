"""汉字 -> 拼音 的离线匹配工具。

表里只有字到读音的映射（见 pinyin_data.py，随程序分发），运行期不联网、
不依赖任何第三方包。对外只暴露一个 `matches()`，搜索路径里用到。

支持三种打法：
    "微信"   原文子串
    "weixin" 全拼
    "wx"     首字母（需 2 个字符以上，单字母太宽泛，交给原文匹配）
"""

from __future__ import annotations

from functools import lru_cache

from . import pinyin_data

_map: dict[str, str] | None = None


def _table() -> dict[str, str]:
    global _map
    if _map is None:
        table: dict[str, str] = {}
        for part in "".join(pinyin_data._GROUPS).split("|"):
            if not part:
                continue
            py, _, chars = part.partition(":")
            if not py or not chars:
                continue
            for ch in chars:
                table[ch] = py
        _map = table
    return _map


def warmup() -> None:
    """提前把表建好。

    首次匹配要花 ~30ms 拆表，正好卡在用户敲下第一个字母的瞬间。
    扫描结束后在后台调用一次，真正搜索时就是零成本。
    """
    _table()


def initial_of(ch: str) -> str:
    py = _table().get(ch)
    return py[0] if py else ""


def _ascii_initials(word: str) -> str:
    """英文词怎么取缩写。

    全大写的短词（QQ / WPS / VS / PDF）本来就是缩写，整个留下；
    普通词只留首字母。所以 "Visual Studio Code" 是 vsc，而 "腾讯QQ" 是 txqq。
    """
    low = word.lower()
    if len(word) <= 4 and word.isupper():
        return low
    return low[0]


@lru_cache(maxsize=8192)
def keys(text: str) -> tuple[str, str]:
    """把一个名字摊成 (全拼串, 首字母串)。

    汉字转成拼音（"微信" -> weixin / wx），英文按词取缩写
    （"Visual Studio Code" -> visual studio code / vsc），两种都塞进串里，
    所以中英混排的应用名怎么打都能命中。
    """
    full: list[str] = []
    initials: list[str] = []
    table = _table()
    text = text or ""
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        py = table.get(ch)
        if py:
            full.append(py)
            initials.append(py[0])
            i += 1
            continue
        if ch.isascii() and ch.isalnum():
            j = i
            while j < n and text[j].isascii() and text[j].isalnum():
                j += 1
            word = text[i:j]
            full.append(word.lower())
            initials.append(_ascii_initials(word))
            i = j
            continue
        low = ch.lower()
        full.append(low)
        if not ch.isspace():
            initials.append(low)
        i += 1
    return "".join(full), "".join(initials)


def matches(query: str, name: str, desc: str = "") -> bool:
    """查询是否命中某个条目。"""
    q = (query or "").strip().lower().replace(" ", "")
    if not q:
        return True

    if q in (name or "").lower():
        return True
    if desc and q in desc.lower():
        return True

    # 拼音只对 ASCII 查询生效（中文走上面的原文匹配就够了）；
    # 至少含一个字母，纯数字/符号不值得摊拼音表。
    if not q.isascii() or len(q) < 2 or not any(c.isalpha() for c in q):
        return False

    full, initials = keys(name or "")
    # 名字里的空格不该逼着用户也打空格："新建 文本文档" 搜 xinjianwendang 也要中
    return q in full.replace(" ", "") or q in initials


def annotate(name: str) -> str:
    """给一个中文名标注首字母，仅用于调试/验证。"""
    full, initials = keys(name)
    return f"{name} -> {full} / {initials}"
