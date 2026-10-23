"""离线生成 deskdock/pinyin_data.py。

数据来源：pypinyin 的 pinyin_dict.json（41842 条汉字读音，cc-by pypinyin）。
只在开发机上跑一次，生成的 py 文件随程序分发，运行期不联网、不依赖第三方包。

用法：
    python tools/gen_pinyin.py <pinyin_dict.json 路径>
"""

from __future__ import annotations

import json
import sys
import unicodedata
from collections import defaultdict

OUT = "deskdock/pinyin_data.py"


def strip_tone(py: str) -> str:
    """去掉声调符号，ü 归一成 v（输入法习惯）。"""
    s = unicodedata.normalize("NFD", py)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("ü", "v").replace("ǖ", "v").replace("ǘ", "v")
    s = s.replace("ǚ", "v").replace("ǜ", "v")
    s = s.lower().strip()
    return "".join(ch for ch in s if "a" <= ch <= "z")


def main(path: str) -> int:
    raw = json.load(open(path, encoding="utf-8"))
    groups: dict[str, list[str]] = defaultdict(list)

    for cp, readings in raw.items():
        if not readings:
            continue
        # 只取第一个读音（pypinyin 数据里排在最前的是最常用读音）
        py = strip_tone(str(readings).split(",")[0])
        if not py:
            continue
        ch = chr(int(cp))
        groups[py].append(ch)

    parts = []
    for py in sorted(groups):
        chars = "".join(sorted(set(groups[py])))
        parts.append(f"{py}:{chars}")
    blob = "|".join(parts)

    total = sum(len(v) for v in groups.values())
    header = (
        '"""汉字 -> 拼音（无声调，ü 记作 v）离线表。\n'
        "\n"
        "由 tools/gen_pinyin.py 从 pypinyin 数据生成，运行期不联网、无第三方依赖。\n"
        "格式：每组 `拼音:汉字串`，组之间用 `|` 隔开；汉字串内字符互不重复。\n"
        '"""\n'
        "\n"
        "# 字数: %d  拼音组: %d\n" % (total, len(groups))
    )
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(header)
        f.write("_GROUPS = (\n")
        # 每行控制在 ~100 字符，diff 友好
        width = 96
        for i in range(0, len(blob), width):
            piece = blob[i : i + width].replace("\\", "\\\\").replace('"', '\\"')
            f.write('    "%s"\n' % piece)
        f.write(")\n")

    print(f"写入 {OUT}: {len(blob)} 字符, {total} 个汉字, {len(groups)} 个拼音组")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "tools/_tmp/pypinyin/pinyin_dict.json"))
