"""첫 화면 `/` — 검색창 하나, 무엇인지 한 줄, 처음 오셨나요 링크, 데이터 기준일."""

from __future__ import annotations

from collections.abc import Iterator

from fin_checkup.site.context import Site
from fin_checkup.site.registry import Output, page


@page("landing")
def landing_page(site: Site) -> Iterator[Output]:
    yield site.render("index.html", "index.html")
