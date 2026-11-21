"""관심종목 `/watch/` — 빈 틀만 정적으로 만들고, 목록은 브라우저(static/watch.js)가 localStorage 로 채운다.

회사 페이지의 "관심종목에 담기" 버튼은 `@company_context("watch")` 가 넘기는 `watch_entry`
(종목코드·이름·사업연도·지표별 신호)를 담을 때의 기준으로 저장한다. 서버에는 아무것도 가지 않는다 —
캐시 DB 의 `watchlist` 테이블(텔레그램 봇용)과 무관하고, 그 테이블은 산출물에 들어가지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fin_checkup.site.context import CompanyEntry, Site
from fin_checkup.site.registry import Output, company_context, page

PATH = "watch/index.html"


def watch_entry(entry: CompanyEntry) -> dict[str, Any]:
    """localStorage 항목 하나의 기준값 (watch.js 상단의 형식과 같다). `saved` 는 브라우저가 붙인다."""
    data = entry.checkup
    return {
        "code": entry.stock_code,
        "name": entry.name,
        "year": data.history[-1].bsns_year,
        "signals": {m.key: m.signal.value for m in data.result.metrics},
    }


@company_context("watch")
def watch_context(entry: CompanyEntry, site: Site) -> dict[str, Any]:
    return {"watch_entry": watch_entry(entry)}


@page("watch")
def watch_page(site: Site) -> Iterator[Output]:
    yield site.render("watch/index.html", PATH)
