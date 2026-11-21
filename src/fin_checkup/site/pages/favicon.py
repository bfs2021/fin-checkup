"""파비콘 `/favicon.svg` · `/favicon.ico` — 신호등 세 칸.

브라우저는 `<link rel="icon">` 이 없거나 SVG 를 못 읽으면 사이트 루트의 `/favicon.ico` 를 찾는다.
없으면 모든 페이지가 404 를 하나씩 낸다. ICO 는 같은 도형을 빌드 때 32×32 로 그려 만든다
(바이너리 파일을 저장소에 두지 않는다 — 도형을 바꾸면 둘이 함께 바뀐다).

색은 밝은 테마 신호색(`theme.SIGNAL_COLORS`)과 글자색.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator

from fin_checkup.metrics.signals import Signal
from fin_checkup.site.context import Site
from fin_checkup.site.registry import Output, page
from fin_checkup.theme import SIGNAL_COLORS

SIZE = 32
BODY = "#1b1b19"
#: (cx, cy, r) — 위에서부터 빨강·노랑·초록.
LIGHTS = (
    (16, 7.5, 4.2, SIGNAL_COLORS[Signal.RED]),
    (16, 16, 4.2, SIGNAL_COLORS[Signal.YELLOW]),
    (16, 24.5, 4.2, SIGNAL_COLORS[Signal.GREEN]),
)
#: 몸통 둥근 사각형 (x, y, w, h, 모서리 반지름).
FRAME = (8.5, 1.5, 15, 29, 6)


def favicon_svg() -> str:
    x, y, w, h, r = FRAME
    circles = "".join(f'<circle cx="{cx}" cy="{cy}" r="{cr}" fill="{c}"/>' for cx, cy, cr, c in LIGHTS)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}">'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{BODY}"/>{circles}</svg>\n'
    )


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _in_frame(px: float, py: float) -> bool:
    x, y, w, h, r = FRAME
    if not (x <= px <= x + w and y <= py <= y + h):
        return False
    # 모서리: 가장 가까운 모서리 원의 중심에서 r 안이면 안쪽.
    cx = min(max(px, x + r), x + w - r)
    cy = min(max(py, y + r), y + h - r)
    return (px - cx) ** 2 + (py - cy) ** 2 <= r * r


def _pixel(ix: int, iy: int, samples: int = 4) -> tuple[int, int, int, int]:
    """(ix, iy) 픽셀의 BGRA. 4×4 표본으로 가장자리를 부드럽게."""
    body, colors, covered = _rgb(BODY), [0.0, 0.0, 0.0], 0
    for sy in range(samples):
        for sx in range(samples):
            px, py = ix + (sx + 0.5) / samples, iy + (sy + 0.5) / samples
            if not _in_frame(px, py):
                continue
            rgb = body
            for cx, cy, cr, c in LIGHTS:
                if (px - cx) ** 2 + (py - cy) ** 2 <= cr * cr:
                    rgb = _rgb(c)
                    break
            covered += 1
            for k in range(3):
                colors[k] += rgb[k]
    if not covered:
        return (0, 0, 0, 0)
    r, g, b = (round(v / covered) for v in colors)
    return (b, g, r, round(255 * covered / samples**2))


def favicon_ico() -> bytes:
    """32×32 · 32비트 BMP 한 장을 담은 ICO."""
    rows = [b"".join(bytes(_pixel(ix, iy)) for ix in range(SIZE)) for iy in range(SIZE)]
    pixels = b"".join(reversed(rows))  # BMP 는 아래 줄부터.
    and_mask = b"\x00" * (SIZE * SIZE // 8)  # 투명도는 알파로. 마스크는 비워 둔다.
    header = struct.pack(
        "<IiiHHIIiiII", 40, SIZE, SIZE * 2, 1, 32, 0, len(pixels) + len(and_mask), 0, 0, 0, 0
    )
    image = header + pixels + and_mask
    icondir = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", SIZE, SIZE, 0, 0, 1, 32, len(image), 6 + 16)
    return icondir + entry + image


@page("favicon")
def favicon_files(site: Site) -> Iterator[Output]:
    yield Output("favicon.svg", favicon_svg())
    yield Output("favicon.ico", favicon_ico())
