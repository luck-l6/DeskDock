"""生成托盘图标与胶囊图标（纯标准库，无第三方依赖）。"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "deskdock" / "qml"


def write_png(path: Path, size: int, pixels: list[list[tuple[int, int, int, int]]]) -> None:
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for r, g, b, a in row:
            raw += bytes((r, g, b, a))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    blob = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))
    path.write_bytes(blob)


def grid_icon(size: int, bg: tuple[int, int, int, int],
              fg: tuple[int, int, int, int], radius: int) -> list:
    """深色圆角底 + 2x2 浅色方块。"""
    cells: list[list[tuple[int, int, int, int]]] = []
    pad = size * 0.22
    gap = size * 0.06
    cell = (size - pad * 2 - gap) / 2

    for y in range(size):
        row = []
        for x in range(size):
            # 圆角处理
            in_corner = False
            for cx, cy in ((radius, radius), (size - 1 - radius, radius),
                           (radius, size - 1 - radius),
                           (size - 1 - radius, size - 1 - radius)):
                if (x < radius and y < radius and (x - cx) ** 2 + (y - cy) ** 2 > radius ** 2
                        and cx == radius and cy == radius):
                    in_corner = True
                elif (x > size - 1 - radius and y < radius
                        and (x - cx) ** 2 + (y - cy) ** 2 > radius ** 2
                        and cx == size - 1 - radius and cy == radius):
                    in_corner = True
                elif (x < radius and y > size - 1 - radius
                        and (x - cx) ** 2 + (y - cy) ** 2 > radius ** 2
                        and cx == radius and cy == size - 1 - radius):
                    in_corner = True
                elif (x > size - 1 - radius and y > size - 1 - radius
                        and (x - cx) ** 2 + (y - cy) ** 2 > radius ** 2
                        and cx == size - 1 - radius and cy == size - 1 - radius):
                    in_corner = True
            if in_corner:
                row.append((0, 0, 0, 0))
                continue

            # 2x2 方块
            color = bg
            for gy in range(2):
                for gx in range(2):
                    x0 = pad + gx * (cell + gap)
                    y0 = pad + gy * (cell + gap)
                    if x0 <= x < x0 + cell and y0 <= y < y0 + cell:
                        color = fg
                        break
                else:
                    continue
                break
            row.append(color)
        cells.append(row)
    return cells


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    bg = (31, 37, 43, 255)
    fg = (185, 216, 245, 255)
    for size, name in ((64, "tray.png"), (128, "app.png")):
        write_png(OUT / name, size, grid_icon(size, bg, fg, max(4, size // 5)))
        print("生成", OUT / name)


if __name__ == "__main__":
    main()
