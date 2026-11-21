"""회사 페이지 인라인 SVG — 구조(접근성), 빈 해 처리(0 으로 메우지 않음), 이스케이프."""

from __future__ import annotations

import dataclasses
import xml.etree.ElementTree as ET
from datetime import date

import pytest
from hub_seed import KB, SAMSUNG, seed_site_cache

from fin_checkup.metrics.engine import MONEY
from fin_checkup.site.build import build_site, collect_companies
from fin_checkup.site.charts import (
    Gap,
    TrendPoint,
    TrendSeries,
    nice_ticks,
    trend_series,
    trend_svg,
)
from fin_checkup.storage import Cache

SVG = "{http://www.w3.org/2000/svg}"


@pytest.fixture
def cache(tmp_path):
    with Cache(tmp_path / "charts.duckdb") as c:
        seed_site_cache(c)
        yield c


@pytest.fixture
async def checkups(cache):
    entries, _ = await collect_companies(cache, 2024)
    return {e.stock_code: e.checkup for e in entries}


def parse(svg: str) -> ET.Element:
    """잘 짜인 XML 이어야 한다 — 이스케이프가 새면 여기서 깨진다."""
    return ET.fromstring(str(svg))


def series(values: list[float | None], label: str = "매출액", unit: str = MONEY) -> TrendSeries:
    points = tuple(
        TrendPoint(2020 + i, v, f"{v}")
        if v is not None
        else TrendPoint(2020 + i, None, "⚫ 데이터 없음", Gap.NO_YEAR)
        for i, v in enumerate(values)
    )
    return TrendSeries("revenue", label, unit, "KRW", points)


# ── 추이 데이터 ───────────────────────────────────────────────────


async def test_trend_keeps_five_year_slots_and_marks_uncollected_years(checkups):
    revenue = next(s for s in trend_series(checkups[SAMSUNG.stock_code]) if s.key == "revenue")
    assert [p.year for p in revenue.points] == [2020, 2021, 2022, 2023, 2024]
    assert [p.gap for p in revenue.points[:2]] == [Gap.NO_YEAR, Gap.NO_YEAR]
    assert all(p.value is None and p.text == "⚫ 데이터 없음" for p in revenue.points[:2])
    assert [p.value for p in revenue.points[2:]] == [1100.0, 1200.0, 900.0]


async def test_missing_account_is_a_gap_not_zero(checkups):
    data = checkups[SAMSUNG.stock_code]
    history = list(data.history)
    history[-2] = history[-2].model_copy(update={"revenue": None})
    data = dataclasses.replace(data, history=history)

    revenue = next(s for s in trend_series(data) if s.key == "revenue")
    assert revenue.points[3].gap is Gap.NO_ACCOUNT and revenue.points[3].value is None
    margin = next(s for s in trend_series(data) if s.key == "operating_margin")
    assert margin.points[3].gap is Gap.NO_ACCOUNT, "매출이 없으면 영업이익률도 0 이 아니라 ⚫"


async def test_ratio_that_is_not_applicable_for_the_sector_is_not_drawn(checkups):
    keys = {s.key for s in trend_series(checkups[KB.stock_code])}
    assert "debt_ratio" not in keys and "current_ratio" not in keys
    assert {"revenue", "operating_income", "net_income", "operating_cash_flow"} <= keys
    assert "debt_ratio" in {s.key for s in trend_series(checkups[SAMSUNG.stock_code])}


# ── SVG ───────────────────────────────────────────────────────────


def test_trend_svg_is_accessible_and_uses_css_classes_only():
    root = parse(trend_svg(series([None, None, 1.1e14, 1.2e14, 9e13]), "t1"))
    assert root.get("role") == "img"
    assert root.get("aria-labelledby") == "t1-t t1-d"
    assert root.find(f"{SVG}title").get("id") == "t1-t"
    desc = root.find(f"{SVG}desc").text
    assert "2020년 ⚫ 데이터 없음" in desc and "2024년" in desc
    text = str(trend_svg(series([1.0, 2.0]), "t2"))
    assert "style=" not in text and "<script" not in text, "CSP 가 막는 인라인 스타일·스크립트 없음"
    assert 'fill="#' not in text, "색은 CSS 변수(클래스)로 — 다크 모드가 따라오게"


def test_each_year_has_a_hover_title():
    root = parse(trend_svg(series([1.0, None, 3.0]), "t"))
    years = root.findall(f"{SVG}g")
    assert len(years) == 3
    assert all(g.find(f"{SVG}title") is not None for g in years)
    assert "2021년 매출액: ⚫ 데이터 없음" in years[1].find(f"{SVG}title").text


def test_gap_years_draw_a_labelled_empty_slot_and_no_bar():
    root = parse(trend_svg(series([None, 5.0, None, 7.0, None]), "t"))
    bars = root.findall(f".//{SVG}path[@class='fc-ch-bar']")
    gaps = root.findall(f".//{SVG}rect[@class='fc-ch-gap']")
    assert len(bars) == 2 and len(gaps) == 3
    marks = [t.text for t in root.iter(f"{SVG}text") if t.get("class") == "fc-ch-gap-mark"]
    assert marks == ["⚫"] * 3
    words = [t.text for t in root.iter(f"{SVG}text") if t.get("class") == "fc-ch-gap-text"]
    assert words == ["데이터", "없음"] * 3


def test_not_applicable_gap_is_labelled_differently():
    s = TrendSeries(
        "debt_ratio",
        "부채비율",
        "%",
        "KRW",
        (TrendPoint(2023, None, "⊘ 해당 없음", Gap.NOT_APPLICABLE), TrendPoint(2024, 80.0, "80.00%")),
    )
    root = parse(trend_svg(s, "t"))
    words = [t.text for t in root.iter(f"{SVG}text") if t.get("class", "").startswith("fc-ch-gap")]
    assert words == ["⊘", "해당", "없음"]


def test_all_missing_still_renders_every_slot_as_a_gap():
    root = parse(trend_svg(series([None] * 5), "t"))
    assert not root.findall(f".//{SVG}path")
    assert len(root.findall(f".//{SVG}rect[@class='fc-ch-gap']")) == 5


def _bar_extent(path: str) -> tuple[float, float]:
    # "M{x},{y_zero}V{...}" — 시작 y 가 기준선, 꼭짓점 y 들 중 기준선에서 먼 쪽이 끝.
    import re

    ys = [float(n) for n in re.findall(r"[,V](-?\d+\.\d)", path)]
    return ys[0], (min(ys) if min(ys) < ys[0] else max(ys))


def test_negative_values_grow_down_from_the_zero_line():
    root = parse(trend_svg(series([3.0e11, -2.0e11]), "t"))
    zero = root.find(f".//{SVG}line[@class='fc-ch-zero']")
    y_zero = float(zero.get("y1"))
    up, down = root.findall(f".//{SVG}path[@class='fc-ch-bar']")
    assert _bar_extent(up.get("d"))[0] == pytest.approx(y_zero, abs=0.1)
    assert _bar_extent(up.get("d"))[1] < y_zero
    assert _bar_extent(down.get("d"))[1] > y_zero


def test_only_the_latest_year_gets_a_direct_value_label():
    root = parse(trend_svg(series([1.0e12, 2.0e12, 3.5e12]), "t"))
    labels = [t.text for t in root.iter(f"{SVG}text") if t.get("class") == "fc-ch-value"]
    assert labels == ["3.5조"]


def test_text_is_escaped():
    nasty = '<script>alert("x")</script> & "따옴표"'
    s = series([1.0, None], label=nasty)
    text = str(trend_svg(s, 'id"><script>'))
    assert "<script>" not in text
    root = parse(text)
    assert nasty in root.find(f"{SVG}title").text


@pytest.mark.parametrize(
    ("lo", "hi"),
    [(0, 1.0), (0, 3.1e14), (-2e11, 3e11), (-5.0, -1.0), (0, 0), (12.3, 456.7)],
)
def test_nice_ticks_cover_the_range_and_include_zero(lo, hi):
    ticks = nice_ticks(lo, hi)
    assert 0 in ticks
    assert ticks[0] <= min(lo, 0) and ticks[-1] >= max(hi, 0)
    assert 2 <= len(ticks) <= 6
    steps = {round(b - a, 6) for a, b in zip(ticks, ticks[1:], strict=False)}
    assert len(steps) == 1


# ── 페이지 ─────────────────────────────────────────────────────────


async def test_company_page_has_trend_section_with_table_fallback(cache, tmp_path):
    out = tmp_path / "out"
    await build_site(cache, out, 2024, built_on=date(2026, 11, 21))
    html = (out / "c" / SAMSUNG.stock_code / "index.html").read_text(encoding="utf-8")
    assert 'id="trend"' in html and "5개년 추이" in html
    assert html.count('class="fc-ch fc-ch-trend"') == 7  # 금액 4 + 비율 3
    assert "<details" in html and "표로 보기" in html
    assert "⚫ 데이터 없음" in html
    kb = (out / "c" / KB.stock_code / "index.html").read_text(encoding="utf-8")
    assert kb.count('class="fc-ch fc-ch-trend"') == 5  # 금융지주: 부채비율·유동비율 ⊘ 은 그리지 않는다
