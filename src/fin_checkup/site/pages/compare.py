"""비교 페이지 `/compare/?c=005930,000660` — 2~4곳을 나란히. 표는 브라우저가 `/api/c/<코드>.json` 으로 채운다.

빌드가 쓰는 건 표의 뼈대뿐이다: 지표마다 한 줄(이름 → `/m/<지표>/`, 계산식), 엔진 정의 순서 그대로.
회사 칸(신호·값·경계값·동종 중앙값)은 `static/compare.js` 가 JSON 의 문자열을 그대로 옮겨 적는다 —
판정·형식은 `pages/api.py` 가 이미 한 것이라 JS 에서 다시 계산하지 않는다.

순서: 회사는 사용자가 고른 순서, 지표는 고정. 값으로 줄 세우거나 '나은 쪽' 을 칠하지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fin_checkup.metrics import engine
from fin_checkup.site.context import Site
from fin_checkup.site.pages.metric import metric_path
from fin_checkup.site.registry import Output, page

PATH = "compare/index.html"
#: 한 번에 놓는 회사 수의 상한. `static/compare.js` 의 MAX 와 같아야 한다 (테스트가 본다).
MAX_COMPANIES = 4


@dataclass(frozen=True)
class CompareRow:
    key: str
    label: str
    formula: str
    path: str


@dataclass(frozen=True)
class CompareGroup:
    category: str
    rows: tuple[CompareRow, ...]


def compare_groups() -> tuple[CompareGroup, ...]:
    """묶음(수익성·안정성…)마다 엔진 정의 순서 그대로 — 회사 페이지처럼 위험한 것부터 올리지 않는다."""
    groups: list[CompareGroup] = []
    for cat in engine.Category:
        rows = tuple(
            CompareRow(d.key, d.label, d.formula, metric_path(d.key))
            for d in engine.METRIC_DEFS
            if d.category is cat
        )
        if rows:
            groups.append(CompareGroup(cat.value, rows))
    return tuple(groups)


@page("compare")
def compare_page(site: Site) -> Iterator[Output]:
    yield site.render("compare/index.html", PATH, groups=compare_groups(), max_companies=MAX_COMPANIES)
