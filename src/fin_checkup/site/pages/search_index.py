"""검색 인덱스 `/search-index.json` — 찾기용 최소 필드만 (지표 값은 넣지 않는다).

회사는 이름순(코드포인트 순, JS 와 같은 비교)이다. 지표 값을 넣으면 인덱스가 순위표 재료가 된다.
`chosung` 은 빌드 때 미리 계산한 초성 문자열 (`site/hangul.py`).
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from fin_checkup.site.context import CompanyEntry, Site
from fin_checkup.site.hangul import chosung, normalize_name
from fin_checkup.site.registry import Output, page

PATH = "search-index.json"


def index_entry(entry: CompanyEntry) -> dict[str, str]:
    company = entry.checkup.company
    return {
        "name": entry.name,
        "code": entry.stock_code,
        "market": company.market.value if company and company.market else "",
        "sector": entry.checkup.result.sector.label,
        "chosung": chosung(normalize_name(entry.name)),
    }


@page("search-index")
def search_index(site: Site) -> Iterator[Output]:
    companies = sorted((index_entry(e) for e in site.companies), key=lambda c: (c["name"], c["code"]))
    payload = {"year": site.year, "built_on": site.built_on.isoformat(), "companies": companies}
    yield Output(PATH, json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
