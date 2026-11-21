"""지표 해설 페이지 `/m/<지표>/` 17개 · 목록 `/m/`.

문장은 전부 `fin_checkup.explain` 에서, 공식·경계값은 `metrics/engine.py` 에서 온다 — 여기서 새로 쓰지 않는다.
"실제 숫자로 계산해 보기" 의 회사는 `site.examples` 의 색과 무관한 규칙으로 고르고, 계산 과정만 보인다.

회사 페이지의 지표 이름이 이 페이지로 링크한다 (`metric_path`).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fin_checkup.explain.glossary import GlossaryTerm, terms_for_metric
from fin_checkup.explain.metrics import MetricExplainer, explainers, threshold_text
from fin_checkup.explain.worked import ROUNDING_NOTE
from fin_checkup.metrics.engine import NOT_APPLICABLE_BY_SECTOR, Category
from fin_checkup.metrics.sector import Sector
from fin_checkup.site.context import Site
from fin_checkup.site.examples import RULE_TEXT, Example, example_for
from fin_checkup.site.registry import Output, page
from fin_checkup.site.view import SignalView


def metric_path(key: str) -> str:
    """지표 해설 페이지의 사이트 내 경로. 링크는 `url(metric_path(key))`."""
    return f"m/{key}/"


@dataclass(frozen=True)
class ThresholdLine:
    #: 일반 기준이면 빈 문자열.
    sector_label: str
    text: str


@dataclass(frozen=True)
class CaveatLine:
    sector_label: str
    why: str
    instead: str


@dataclass(frozen=True)
class RuleLine:
    signal: SignalView
    when: str


@dataclass(frozen=True)
class MetricPage:
    e: MetricExplainer
    path: str
    thresholds: tuple[ThresholdLine, ...]
    caveats: tuple[CaveatLine, ...]
    rules: tuple[RuleLine, ...]
    terms: tuple[GlossaryTerm, ...]
    example: Example | None


def thresholds_for(e: MetricExplainer) -> tuple[ThresholdLine, ...]:
    """일반 기준 한 줄 + 업종 경계값이 따로 있는 업종마다 한 줄. ⊘ 업종은 caveats 가 말한다."""
    lines = [ThresholdLine("", threshold_text(e.key))]
    for sector in Sector:
        if sector is Sector.GENERAL or e.key in NOT_APPLICABLE_BY_SECTOR.get(sector, {}):
            continue
        if e.definition.sector_bands and sector in e.definition.sector_bands:
            lines.append(ThresholdLine(sector.label, threshold_text(e.key, sector)))
    return tuple(lines)


def caveats_for(e: MetricExplainer) -> tuple[CaveatLine, ...]:
    return tuple(CaveatLine(c.sector.label, c.why, c.instead) for c in e.sector_caveats)


def metric_page(site: Site, e: MetricExplainer) -> MetricPage:
    return MetricPage(
        e=e,
        path=metric_path(e.key),
        thresholds=thresholds_for(e),
        caveats=caveats_for(e),
        rules=tuple(RuleLine(SignalView.of(r.signal), r.when) for r in e.special_rules),
        terms=terms_for_metric(e.key),
        example=example_for(site, e.key),
    )


@dataclass(frozen=True)
class IndexGroup:
    category: str
    items: tuple[MetricExplainer, ...]


def index_groups() -> tuple[IndexGroup, ...]:
    """묶음(수익성·안정성…)마다 엔진 정의 순서 그대로."""
    all_ = explainers()
    return tuple(
        IndexGroup(cat.value, tuple(e for e in all_ if e.category is cat))
        for cat in Category
        if any(e.category is cat for e in all_)
    )


@page("metric")
def metric_pages(site: Site) -> Iterator[Output]:
    yield site.render("metric/index.html", "m/index.html", groups=index_groups(), metric_path=metric_path)
    for e in explainers():
        yield site.render(
            "metric/page.html",
            metric_path(e.key) + "index.html",
            p=metric_page(site, e),
            rule_text=RULE_TEXT,
            rounding_note=ROUNDING_NOTE,
        )
