"""첫 화면 `/` — 검색창, 한 줄 소개, 결과가 어떻게 보이는지 예시 하나, 데이터 기준일 한 줄, 시장 전체 공시.

예시 회사는 '재무제표 처음 읽기' 와 같은 고정 규칙(`examples.default_example` — 매출액 최대 일반 업종
회사)이다. 색이나 지표 값으로 고르지 않고, 순위·인기 목록을 만들지 않는다.
예시는 그 회사 한눈에 보기의 첫 묶음 그대로.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fin_checkup.site.context import CompanyEntry, Site
from fin_checkup.site.examples import default_example
from fin_checkup.site.pages.disclosures import market_disclosures
from fin_checkup.site.registry import Output, page
from fin_checkup.site.view import CompanyView, MetricGroup, company_view


@dataclass(frozen=True)
class LandingExample:
    entry: CompanyEntry
    c: CompanyView
    #: 한눈에 보기의 첫 묶음 — 카드 순서·신호 그대로.
    group: MetricGroup
    #: 첫 화면에 싣지 않은 나머지 지표 수.
    rest: int


def landing_example(site: Site) -> LandingExample | None:
    entry = default_example(site)
    if entry is None:
        return None
    c = company_view(entry.checkup)
    if not c.groups:
        return None
    total = sum(len(g.rows) for g in c.groups)
    return LandingExample(entry, c, c.groups[0], total - len(c.groups[0].rows))


@page("landing")
def landing_page(site: Site) -> Iterator[Output]:
    yield site.render(
        "index.html",
        "index.html",
        market_disclosures=market_disclosures(site),
        example=landing_example(site),
    )
