"""색각 이상 시뮬레이션과 색차 — 테스트 전용 계산 (의존성 없음).

- 이색형 색각(제1·2색맹) 시뮬레이션: Viénot, Brettel & Mollon (1999) "Digital video colourmaps for
  checking the legibility of displays by dichromats". 선형 sRGB → LMS 로 옮겨 없는 원뿔 하나를 나머지 둘로
  다시 만든다.
- 색차: CIEDE2000 (Sharma, Wu & Dalal 2005 의 구현 노트와 시험 자료로 확인).
"""

from __future__ import annotations

import math

_RGB_TO_LMS = (
    (17.8824, 43.5161, 4.11935),
    (3.45565, 27.1554, 3.86714),
    (0.0299566, 0.184309, 1.46709),
)
_LMS_TO_RGB = (
    (0.0809444479, -0.130504409, 0.116721066),
    (-0.0102485335, 0.0540193266, -0.113614708),
    (-0.000365296938, -0.00412161469, 0.693511405),
)
KINDS = ("normal", "protanopia", "deuteranopia")


def _mul(m, v):
    return tuple(sum(m[i][j] * v[j] for j in range(3)) for i in range(3))


def _to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _to_srgb(c: float) -> float:
    c = min(max(c, 0.0), 1.0)
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))


def simulate(hex_color: str, kind: str) -> tuple[float, float, float]:
    """kind 의 눈에 보이는 색 (sRGB 0~1)."""
    linear = tuple(_to_linear(c) for c in hex_to_rgb(hex_color))
    if kind == "normal":
        return tuple(_to_srgb(c) for c in linear)
    lms_l, lms_m, lms_s = _mul(_RGB_TO_LMS, linear)
    if kind == "protanopia":
        lms_l = 2.02344 * lms_m - 2.52581 * lms_s
    elif kind == "deuteranopia":
        lms_m = 0.494207 * lms_l + 1.24827 * lms_s
    else:
        raise ValueError(kind)
    return tuple(_to_srgb(c) for c in _mul(_LMS_TO_RGB, (lms_l, lms_m, lms_s)))


def to_lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """sRGB(0~1) → CIELAB (D65)."""
    r, g, b = (_to_linear(c) for c in rgb)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e_2000(lab1, lab2) -> float:
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
    c_bar = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(c_bar**7 / (c_bar**7 + 25**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if c1p else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if c2p else 0.0

    dlp, dcp = l2 - l1, c2p - c1p
    if c1p * c2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    d_hp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp / 2))

    l_bar, cp_bar = (l1 + l2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        hp_bar = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hp_bar = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hp_bar = (h1p + h2p + 360) / 2
    else:
        hp_bar = (h1p + h2p - 360) / 2

    t = (
        1
        - 0.17 * math.cos(math.radians(hp_bar - 30))
        + 0.24 * math.cos(math.radians(2 * hp_bar))
        + 0.32 * math.cos(math.radians(3 * hp_bar + 6))
        - 0.20 * math.cos(math.radians(4 * hp_bar - 63))
    )
    d_theta = 30 * math.exp(-(((hp_bar - 275) / 25) ** 2))
    r_c = 2 * math.sqrt(cp_bar**7 / (cp_bar**7 + 25**7))
    s_l = 1 + 0.015 * (l_bar - 50) ** 2 / math.sqrt(20 + (l_bar - 50) ** 2)
    s_c = 1 + 0.045 * cp_bar
    s_h = 1 + 0.015 * cp_bar * t
    r_t = -math.sin(math.radians(2 * d_theta)) * r_c
    return math.sqrt(
        (dlp / s_l) ** 2 + (dcp / s_c) ** 2 + (d_hp / s_h) ** 2 + r_t * (dcp / s_c) * (d_hp / s_h)
    )


def seen_delta_e(color_a: str, color_b: str, kind: str) -> float:
    """kind 의 눈으로 본 두 색의 CIEDE2000 색차."""
    return delta_e_2000(to_lab(simulate(color_a, kind)), to_lab(simulate(color_b, kind)))
