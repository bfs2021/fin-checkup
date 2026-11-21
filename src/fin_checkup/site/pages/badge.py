"""임베드 배지 `/badge/<종목코드>.svg` 와 회사 페이지의 '블로그에 붙이기' 코드.

배지는 신호 개수와 사업연도만 싣는다 — 종합 점수·등급이 아니다 (`charts.badge_svg`).
붙이는 코드는 늘 회사 페이지로 돌아오는 링크를 감싼다: 배지만 보고는 계산식·경계값을 알 수 없으니까.
"""

from __future__ import annotations

from collections.abc import Iterator
from html import escape
from typing import Any

from fin_checkup.site.charts import badge_svg
from fin_checkup.site.context import CompanyEntry, Site
from fin_checkup.site.registry import Output, company_context, page


def badge_path(entry: CompanyEntry) -> str:
    return f"badge/{entry.stock_code}.svg"


def _svg(entry: CompanyEntry) -> str:
    result = entry.checkup.result
    return badge_svg(dict(result.counts), result.bsns_year, company=entry.name)


@page("badge")
def badge_files(site: Site) -> Iterator[Output]:
    for entry in site.companies:
        yield Output(badge_path(entry), _svg(entry))


def _markdown_text(text: str) -> str:
    return "".join("\\" + ch if ch in "[]()\\*_`" else ch for ch in text)


@company_context("embed")
def embed_context(entry: CompanyEntry, site: Site) -> dict[str, Any]:
    year = entry.checkup.result.bsns_year
    alt = f"fin-checkup {entry.name} {year} 재무 신호등"
    page_url = site.absolute_url(entry.path)
    image_url = site.absolute_url(badge_path(entry))
    return {
        "badge_path": badge_path(entry),
        "badge_alt": alt,
        "embed_markdown": f"[![{_markdown_text(alt)}]({image_url})]({page_url})",
        "embed_html": (
            f'<a href="{escape(page_url)}"><img src="{escape(image_url)}" alt="{escape(alt)}"></a>'
        ),
    }
