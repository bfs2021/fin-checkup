"""사업보고서 시즌 안내 · 데이터 기준일 — 법정 기한(자본시장법 159·160조)과 빌드 날짜로 계산한다."""

from __future__ import annotations

import re
from datetime import date

import pytest
from hub_seed import seed_site_cache

from fin_checkup.site.build import build_site
from fin_checkup.site.season import filings_of, latest_annual_due, season_view, upcoming_filings
from fin_checkup.storage import Cache


def test_statutory_deadlines_for_a_december_fiscal_year():
    q1, half, q3, annual = filings_of(2026)
    assert q1.due == date(2026, 5, 15)
    assert half.due == date(2026, 8, 14)
    assert q3.due == date(2026, 11, 14)
    assert annual.due == date(2027, 3, 31) and annual.report == "사업보고서" and annual.used_here
    assert not (q1.used_here or half.used_here or q3.used_here)


def test_annual_deadline_is_ninety_days_so_a_leap_year_ends_on_march_30():
    assert filings_of(2027)[-1].due == date(2028, 3, 30)


def test_upcoming_filings_start_from_the_build_day_inclusive():
    got = upcoming_filings(date(2026, 11, 14))
    assert [f.due for f in got] == [
        date(2026, 11, 14),
        date(2027, 3, 31),
        date(2027, 5, 15),
        date(2027, 8, 14),
    ]
    got = upcoming_filings(date(2026, 11, 21))
    assert [f.period for f in got] == ["2026 사업연도", "2027년 1분기", "2027년 상반기", "2027년 3분기"]


@pytest.mark.parametrize(
    ("today", "year"),
    [
        (date(2026, 3, 31), 2024),
        (date(2026, 4, 1), 2025),
        (date(2026, 11, 21), 2025),
        (date(2027, 1, 2), 2025),
    ],
)
def test_latest_annual_due(today, year):
    assert latest_annual_due(today) == year


def test_pending_year_only_when_the_site_is_behind_the_deadline():
    assert season_view(2024, date(2026, 11, 21)).pending_year == 2025
    assert season_view(2025, date(2026, 11, 21)).pending_year is None
    assert season_view(2024, date(2026, 2, 1)).pending_year is None
    assert season_view(2025, date(2026, 11, 21)).next_annual.period == "2026 사업연도"


@pytest.fixture
async def out(tmp_path):
    with Cache(tmp_path / "s.duckdb") as cache:
        seed_site_cache(cache)
        target = tmp_path / "out"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    return target


def section(text: str) -> str:
    m = re.search(r'<aside class="fc-season[^"]*".*?</aside>', text, re.S)
    assert m, "시즌 안내가 없다"
    return m.group(0)


@pytest.mark.parametrize("path", ["index.html", "c/005930/index.html"])
async def test_landing_and_company_pages_state_year_build_date_and_next_filings(out, path):
    box = section((out / path).read_text(encoding="utf-8"))
    assert "2024 사업연도" in box and "2026-11-21" in box
    assert "보통 이때 새 숫자가 나와요" in box
    assert "2027-03-31" in box and "2026 사업연도 사업보고서" in box
    assert "2027-05-15" in box and "2027-08-14" in box
    assert "2025 사업연도 사업보고서는 제출 기한(2026-03-31)이 지났지만" in box
    assert "12월 결산" in box


async def test_season_box_has_no_countdown_or_urgency(out):
    box = section((out / "index.html").read_text(encoding="utf-8"))
    assert "!" not in box
    for word in ("남았", "D-", "서두르", "놓치", "곧 마감", "지금 바로"):
        assert word not in box
