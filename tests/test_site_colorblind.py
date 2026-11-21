"""색약 대응 — 신호는 색만으로 전하지 않고, 색끼리도 색각 이상 눈으로 갈린다.

1. 신호 색을 입히는 곳(`sig-*` 클래스, 동종업계 띠, 배지 점)에는 신호 이름이 글자로 함께 있다.
   🟢🟡🔴 이모지는 모양이 같은 동그라미라 기호로 치지 않는다 — '정상/주의/위험' 글자가 있어야 한다.
   ⊘(사선 원)·⚪(흰 원)·⚫(검은 원)은 모양·밝기가 달라 기호로 친다.
2. 신호 팔레트(밝은·어두운 모드)의 정상·주의·위험 세 색은 정상 색각·제1색맹·제2색맹 시뮬레이션
   (Viénot 1999) 모두에서 서로 CIEDE2000 색차가 `MIN_DELTA_E` 이상이다.
"""

from __future__ import annotations

import itertools
import re
import xml.etree.ElementTree as ET
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import pytest
from colorvision import KINDS, delta_e_2000, seen_delta_e, simulate
from hub_seed import seed_site_cache

from fin_checkup.metrics.engine import Category, Metric
from fin_checkup.metrics.peers import PeerScope, PeerStat
from fin_checkup.metrics.signals import Band, Signal
from fin_checkup.site.build import build_site
from fin_checkup.site.charts import BAND_LABEL_MIN_WIDTH, badge_svg, peer_strip
from fin_checkup.storage import Cache
from fin_checkup.theme import SIGNAL_COLORS

CSS = Path(__file__).resolve().parents[1] / "src" / "fin_checkup" / "site" / "static" / "site.css"
SVG = "{http://www.w3.org/2000/svg}"

#: 색 셋이 '한눈에 다르다' 고 볼 최소 색차 (CIEDE2000). 2.3 이 겨우 알아채는 정도(JND)이고,
#: 범주 색을 고를 때 흔히 10 안팎을 하한으로 둔다. 신호는 글자로도 적으니 색은 보조 — 그래도 서로 섞이지 않게.
MIN_DELTA_E = 10.0
JUDGED = ("green", "yellow", "red")
#: 모양·밝기로 갈리는 기호. 동그라미 이모지(🟢🟡🔴)는 색만 다르다.
SHAPE_SYMBOLS = {Signal.NOT_APPLICABLE: "⊘", Signal.NEUTRAL: "⚪", Signal.UNKNOWN: "⚫"}


# ── 색각 계산이 맞는지 ──────────────────────────────────────────────


def test_ciede2000_matches_sharma_reference_pairs():
    # Sharma, Wu & Dalal (2005) 표 1 의 1·7·17번 쌍.
    assert delta_e_2000((50, 2.6772, -79.7751), (50, 0, -82.7485)) == pytest.approx(2.0425, abs=1e-4)
    assert delta_e_2000((50, 0, 0), (50, -1, 2)) == pytest.approx(2.3669, abs=1e-4)
    assert delta_e_2000((50, 2.5, 0), (73, 25, -18)) == pytest.approx(27.1492, abs=1e-4)


def test_simulation_keeps_greys_and_merges_red_green_for_dichromats():
    for grey in ("#ffffff", "#808080", "#000000"):
        for kind in KINDS:
            r, g, b = simulate(grey, kind)
            assert max(r, g, b) - min(r, g, b) < 0.02, (grey, kind)
    # 같은 밝기의 빨강·초록은 제2색맹 눈에 거의 같은 색이어야 한다 — 시뮬레이션이 실제로 일을 하는지.
    assert seen_delta_e("#c0392b", "#6b8e23", "normal") > 30
    assert (
        seen_delta_e("#c0392b", "#6b8e23", "deuteranopia") < seen_delta_e("#c0392b", "#6b8e23", "normal") / 2
    )


# ── 팔레트 ───────────────────────────────────────────────────────


def _vars(block: str) -> dict[str, str]:
    return dict(re.findall(r"--(sig-[\w-]+):\s*(#[0-9a-fA-F]{6})\s*;", block))


def palettes() -> dict[str, dict[str, str]]:
    text = CSS.read_text(encoding="utf-8")
    light_block, rest = text.split("@media (prefers-color-scheme: dark)", 1)
    light = _vars(light_block)
    return {"light": light, "dark": {**light, **_vars(rest.split("\n}\n", 1)[0])}}


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(("a", "b"), list(itertools.combinations(JUDGED, 2)))
def test_judged_signal_colors_stay_apart_for_colour_blind_eyes(theme, kind, a, b):
    colors = palettes()[theme]
    ca, cb = colors[f"sig-{a}"], colors[f"sig-{b}"]
    de = seen_delta_e(ca, cb, kind)
    assert de >= MIN_DELTA_E, f"{theme} {kind}: {a} {ca} vs {b} {cb} ΔE2000 {de:.1f} < {MIN_DELTA_E}"


def test_streamlit_badge_and_card_colors_are_the_checked_light_palette():
    light = palettes()["light"]
    for signal in (Signal.GREEN, Signal.YELLOW, Signal.RED):
        assert SIGNAL_COLORS[signal] == light[f"sig-{signal.value}"]


# ── 색 말고 글자 ─────────────────────────────────────────────────


def _has_text(signal: Signal, text: str) -> bool:
    return signal.label in text or SHAPE_SYMBOLS.get(signal, "\0") in text


class _SignalElements(HTMLParser):
    """`sig-*` 클래스가 붙은 요소마다 (신호, 보이는 글자, 클래스). <title>·<desc> 는 보이지 않으니 뺀다."""

    VOID = frozenset("area base br col embed hr img input link meta source track wbr".split())

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[dict] = []
        self.found: list[tuple[Signal, str, str]] = []

    def handle_starttag(self, tag, attrs):
        classes = (dict(attrs).get("class") or "").split()
        sig = next((c[4:] for c in classes if c.startswith("sig-")), None)
        if tag in self.VOID:
            if sig:
                self.found.append((Signal(sig), "", " ".join(classes)))
            return
        hidden = tag in ("title", "desc") or bool(self.stack and self.stack[-1]["hidden"])
        self.stack.append({"tag": tag, "sig": sig, "text": [], "classes": classes, "hidden": hidden})

    def handle_endtag(self, tag):
        while self.stack:
            el = self.stack.pop()
            text = "".join(el["text"])
            if self.stack and not el["hidden"]:
                self.stack[-1]["text"].append(text)
            if el["sig"]:
                self.found.append((Signal(el["sig"]), text, " ".join(el["classes"])))
            if el["tag"] == tag:
                return

    def handle_data(self, data):
        if self.stack and not self.stack[-1]["hidden"]:
            self.stack[-1]["text"].append(data)


#: 신호 색을 쓰지만 이름은 둘레가 말해 주는 곳.
#: 위험 신호 목록은 제목('위험 신호')이 종류를 말하고 항목은 한 종류뿐.
CONTEXT_NAMED = ("fc-flags",)


@pytest.fixture
async def out(tmp_path):
    with Cache(tmp_path / "site.duckdb") as cache:
        seed_site_cache(cache)
        target = tmp_path / "out"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    return target


def _context_named(html: str, text: str) -> bool:
    return any(
        re.search(rf'class="{c}"[^>]*>(?:(?!</ul>).)*{re.escape(text[:20])}', html, re.S)
        for c in CONTEXT_NAMED
    )


async def test_every_signal_colored_element_in_the_site_also_says_its_name(out):
    checked, missing = 0, []
    for path in sorted(out.rglob("*.html")):
        html = path.read_text(encoding="utf-8")
        parser = _SignalElements()
        parser.feed(html)
        for signal, text, classes in parser.found:
            checked += 1
            if _has_text(signal, text) or (text.strip() and _context_named(html, text.strip())):
                continue
            missing.append(f"{path.relative_to(out)}: .{classes} — {text.strip()[:40]!r}")
    assert checked > 50
    assert missing == []


def _metric(value: float, band: Band, signal: Signal) -> Metric:
    return Metric(
        key="operating_margin",
        label="영업이익률",
        category=Category.PROFITABILITY,
        value=value,
        unit="%",
        signal=signal,
        description="",
        formula="영업이익 ÷ 매출액 × 100",
        band=band,
    )


def _stat(**kw) -> PeerStat:
    values = dict(median=4.0, p10=-3.0, q1=1.0, q3=8.0, p90=15.0) | kw
    return PeerStat(
        "operating_margin", sample_size=34, scope=PeerScope.INDUSTRY, unit="%", percentile=50.0, **values
    )


STRIPS = [
    (_metric(12.0, Band(good=7, warn=0), Signal.GREEN), _stat()),
    (_metric(-20.0, Band(good=7, warn=0), Signal.RED), _stat(p10=-40.0, q1=-10.0)),
    (
        _metric(80.0, Band(good=100, warn=200, higher_is_better=False), Signal.GREEN),
        _stat(p10=30.0, p90=400.0),
    ),
    (_metric(5.0, Band(good=8, warn=7.8), Signal.YELLOW), _stat()),  # 주의 구간이 아주 좁다
]


@pytest.mark.parametrize(("metric", "stat"), STRIPS)
def test_peer_strip_bands_are_named_where_there_is_room(metric, stat):
    root = ET.fromstring(str(peer_strip(metric, stat, "KRW", "p").svg))
    labels = [
        (float(t.get("x")), t.text) for t in root.iter(f"{SVG}text") if t.get("class") == "fc-ch-band-label"
    ]
    bands = [r for r in root.iter(f"{SVG}rect") if "fc-ch-band" in (r.get("class") or "")]
    assert bands
    for rect in bands:
        signal = Signal(rect.get("class").split()[-1][4:])
        x0, width = float(rect.get("x")), float(rect.get("width"))
        if width < BAND_LABEL_MIN_WIDTH:
            continue  # 좁은 구간은 경계값 숫자와 카드의 경계값 문장이 말한다
        centre = x0 + width / 2
        assert any(abs(x - centre) < 0.2 and text == signal.label for x, text in labels), (signal, x0, width)


def test_badge_names_the_judged_counts_and_shapes_the_rest():
    counts = {Signal.GREEN: 9, Signal.YELLOW: 4, Signal.RED: 2, Signal.NEUTRAL: 1, Signal.NOT_APPLICABLE: 1}
    root = ET.fromstring(badge_svg(counts, 2024))
    visible = [t.text for t in root.iter(f"{SVG}text")]
    for signal in (Signal.GREEN, Signal.YELLOW, Signal.RED):
        assert f"{signal.label} {counts[signal]}" in visible, signal
    dots = [c for c in root.iter(f"{SVG}circle")]
    # ⚪ 는 흰 속, ⊘ 는 빈 원 + 사선 — 같은 모양의 색 점은 이름이 붙은 셋뿐이다.
    filled = [c for c in dots if c.get("fill") not in ("none", "#ffffff")]
    assert len(filled) == 3
    assert root.find(f".//{SVG}path[@stroke]") is not None
