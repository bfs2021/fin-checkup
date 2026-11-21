"""첫 화면 `/` — 검색창, 한 줄 소개, 처음 오셨나요 링크, 데이터 기준일, 시장 전체 공시(파일이 있으면)."""

from __future__ import annotations

from collections.abc import Iterator

from fin_checkup.site.context import Site
from fin_checkup.site.pages.disclosures import market_disclosures
from fin_checkup.site.registry import Output, page


@page("landing")
def landing_page(site: Site) -> Iterator[Output]:
    yield site.render("index.html", "index.html", market_disclosures=market_disclosures(site))
