"""'최근 위험 공시' — 회사 페이지 섹션 · 첫 화면 시장 전체 목록 · `/data/disclosures.json`.

재료는 `site build --disclosures <파일>` (`site/disclosures.py`). 파일이 없으면 셋 다 생기지 않는다.
회사 페이지는 그 회사의 공시가 한 건도 없을 때도 섹션을 그리지 않는다 — '없음' 상자는 '안전' 으로 읽히기 쉽고,
목록은 제목 기준 분류라 빠진 공시가 있을 수 있다.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

from fin_checkup.site.context import CompanyEntry, Site
from fin_checkup.site.disclosures import COMPANY_LIMIT, MARKET_LIMIT, DisclosureItem
from fin_checkup.site.pages.feeds import MARKET_FEED, company_feed_path
from fin_checkup.site.registry import Output, company_context, page

DATA_PATH = "data/disclosures.json"


@dataclass(frozen=True)
class DisclosureSection:
    items: list[DisclosureItem]
    #: 목록 상한 밖에 더 있는 건수.
    more: int
    begin: date
    end: date
    truncated: bool
    #: 같은 공시를 받아 보는 Atom 피드 (pages/feeds.py).
    feed_path: str


def _section(site: Site, items: list[DisclosureItem], limit: int, feed_path: str) -> DisclosureSection | None:
    feed = site.disclosures
    if feed is None or not items:
        return None
    return DisclosureSection(
        items=items[:limit],
        more=max(len(items) - limit, 0),
        begin=feed.begin,
        end=feed.end,
        truncated=feed.truncated,
        feed_path=feed_path,
    )


@company_context("disclosures")
def company_disclosures(entry: CompanyEntry, site: Site) -> dict:
    items = site.disclosures.for_company(entry.stock_code) if site.disclosures else []
    section = _section(site, items, COMPANY_LIMIT, company_feed_path(entry.stock_code))
    return {"recent_disclosures": section}


def market_disclosures(site: Site) -> DisclosureSection | None:
    """첫 화면 목록 — 알림 채널과 같은 '시장 전체' 유형만 (`alerts.classify.is_market_wide`)."""
    items = site.disclosures.market_wide() if site.disclosures else []
    return _section(site, items, MARKET_LIMIT, MARKET_FEED)


@page("disclosures-data")
def disclosures_data(site: Site) -> Iterator[Output]:
    if site.disclosures is not None:
        text = json.dumps(site.disclosures.public, ensure_ascii=False, separators=(",", ":"))
        yield Output(DATA_PATH, text + "\n")
