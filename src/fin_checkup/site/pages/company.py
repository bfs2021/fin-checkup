"""회사 페이지 `/c/<종목코드>/`.

템플릿은 `templates/company/index.html` 이 섹션 부분 템플릿(`_summary.html` …)을 include 한다.
섹션을 더하려면 부분 템플릿 하나 + include 한 줄, 데이터가 더 필요하면
`@company_context("이름")` 함수 하나(registry.py 참고).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fin_checkup.site.context import CompanyEntry, Site
from fin_checkup.site.registry import COMPANY_CONTEXTS, Output, page
from fin_checkup.site.view import company_view


def company_page_context(entry: CompanyEntry, site: Site) -> dict[str, Any]:
    context: dict[str, Any] = {"entry": entry, "c": company_view(entry.checkup)}
    for name, provider in COMPANY_CONTEXTS.items():
        extra = provider(entry, site)
        clash = set(extra) & set(context)
        if clash:
            raise ValueError(f"company_context '{name}' 가 이미 있는 키를 덮는다: {sorted(clash)}")
        context.update(extra)
    return context


@page("company")
def company_pages(site: Site) -> Iterator[Output]:
    for entry in site.companies:
        yield site.render(
            "company/index.html", entry.path + "index.html", **company_page_context(entry, site)
        )
