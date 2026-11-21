"""정기 공시 시즌 안내 — 지금 보이는 숫자가 몇 년도 것이고, 새 숫자는 보통 언제 나오나.

법정 제출 기한(12월 결산 회사 기준):
- 사업보고서: 사업연도 경과 후 90일 이내 (자본시장법 제159조) → 보통 3월 말
- 반기·분기보고서: 그 기간 경과 후 45일 이내 (자본시장법 제160조) → 1분기 5/15 · 반기 8/14 · 3분기 11/14

기한이 주말·공휴일이면 다음 날로 늘어난다(민법 제161조) — 그래서 화면엔 "보통 이때" 로만 적는다.
날짜는 빌드 날짜(`Site.built_on`, 기본 `clock.kst_today()`) 기준이다. 카운트다운은 두지 않는다 —
정적 사이트에서 남은 일수는 빌드 뒤로 갈수록 틀려지고, 재촉하는 장치일 뿐이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

ANNUAL_DAYS = 90
INTERIM_DAYS = 45


@dataclass(frozen=True)
class Filing:
    """정기 보고서 하나의 법정 제출 기한."""

    report: str
    #: 어느 기간의 숫자인가. 예: "2025 사업연도", "2026년 1분기".
    period: str
    due: date
    #: 이 사이트의 신호등이 쓰는 보고서인가 (지금은 사업보고서만).
    used_here: bool


@dataclass(frozen=True)
class SeasonView:
    #: 지금 보이는 사업연도.
    year: int
    built_on: date
    #: 빌드 날짜 이후(당일 포함) 다가오는 기한, 이른 순.
    upcoming: list[Filing]
    #: 제출 기한이 지났는데 이 사이트에 아직 없는 사업연도. 없으면 None.
    pending_year: int | None

    @property
    def pending_due(self) -> date | None:
        return None if self.pending_year is None else filings_of(self.pending_year)[-1].due

    @property
    def next_annual(self) -> Filing:
        return next(f for f in self.upcoming if f.used_here)


def filings_of(year: int) -> list[Filing]:
    """`year` 년의 숫자가 담기는 정기 보고서 넷 (1분기·반기·3분기 → 사업보고서)."""
    return [
        Filing("분기보고서", f"{year}년 1분기", date(year, 3, 31) + timedelta(INTERIM_DAYS), False),
        Filing("반기보고서", f"{year}년 상반기", date(year, 6, 30) + timedelta(INTERIM_DAYS), False),
        Filing("분기보고서", f"{year}년 3분기", date(year, 9, 30) + timedelta(INTERIM_DAYS), False),
        Filing("사업보고서", f"{year} 사업연도", date(year, 12, 31) + timedelta(ANNUAL_DAYS), True),
    ]


def upcoming_filings(today: date, count: int = 4) -> list[Filing]:
    candidates = [f for y in (today.year - 1, today.year, today.year + 1) for f in filings_of(y)]
    return sorted((f for f in candidates if f.due >= today), key=lambda f: f.due)[:count]


def latest_annual_due(today: date) -> int:
    """제출 기한이 지난 가장 최근 사업연도. 2026-03-31 까지는 2024, 그 다음 날부터 2025."""
    year = today.year - 1
    return year if filings_of(year)[-1].due < today else year - 1


def season_view(year: int, built_on: date) -> SeasonView:
    due = latest_annual_due(built_on)
    return SeasonView(
        year=year,
        built_on=built_on,
        upcoming=upcoming_filings(built_on),
        pending_year=due if due > year else None,
    )
