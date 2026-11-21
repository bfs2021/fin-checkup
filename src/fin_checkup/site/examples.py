"""예시 회사 고르기 — 색과 무관한 고정 규칙.

지표 해설 페이지의 "실제 숫자로 계산해 보기" 와 '재무제표 처음 읽기' 가 같은 회사를 쓴다.
신호 색이나 지표 값으로 고르면 "이 회사를 보라" 는 말이 되므로, **최근 사업연도 매출액**만 본다:

1. 기본 예시 회사 = 일반 업종 기준으로 판정되는 회사(17개 지표가 모두 판정 대상) 중 매출액이 가장 큰 회사.
2. 지표마다 그 회사를 먼저 쓴다. 그 회사로 계산할 수 없으면(값이 없거나 그 업종엔 ⊘), 이 지표를 판정하는
   업종의 회사를 매출액 큰 순서로 보며 계산할 수 있는 첫 회사를 쓴다.

매출액이 같으면 종목코드순. 원화가 아닌 회사는 빼서 금액 자릿수를 맞춘다.
모집단은 이 빌드의 회사(`site.companies`).
"""

from __future__ import annotations

from dataclasses import dataclass

from fin_checkup.explain.worked import WorkedExample, worked_example
from fin_checkup.metrics.engine import NOT_APPLICABLE_BY_SECTOR
from fin_checkup.metrics.sector import Sector
from fin_checkup.site.context import CompanyEntry, Site

#: 화면에 그대로 싣는 규칙 문장.
RULE_TEXT = (
    "예시 회사는 색과 상관없는 고정 규칙으로 골라요. "
    "이 사이트에 있는 상장사 중 일반 업종 기준으로 판정되는 회사 가운데 "
    "최근 사업연도 매출액이 가장 큰 회사를 모든 지표에 먼저 써요. 그 회사로 계산할 수 없는 지표만, "
    "그 지표를 판정하는 업종의 회사 중 매출액이 큰 순서로 계산할 수 있는 첫 회사를 써요. "
    "신호등 색이나 지표 값은 고르는 데 쓰지 않아요."
)


@dataclass(frozen=True)
class Example:
    entry: CompanyEntry
    worked: WorkedExample
    #: 기본 예시 회사인가 (아니면 화면에 "이 지표는 다른 회사로" 를 밝힌다).
    is_default: bool


def _revenue(entry: CompanyEntry) -> float | None:
    return entry.checkup.history[-1].revenue


_MEMO: tuple[Site, list[CompanyEntry]] | None = None


def by_revenue(site: Site) -> list[CompanyEntry]:
    """원화 회사, 최근 사업연도 매출액 큰 순(같으면 종목코드순). 매출액이 없는 회사는 빠진다."""
    global _MEMO
    if _MEMO is not None and _MEMO[0] is site:
        return _MEMO[1]
    ranked = sorted(
        (e for e in site.companies if e.checkup.result.currency == "KRW" and _revenue(e) is not None),
        key=lambda e: (-(_revenue(e) or 0.0), e.stock_code),
    )
    _MEMO = (site, ranked)
    return ranked


def default_example(site: Site) -> CompanyEntry | None:
    """기본 예시 회사 — 일반 업종 중 매출액 최대. 없으면 None."""
    return next((e for e in by_revenue(site) if e.checkup.result.sector is Sector.GENERAL), None)


def _applies(entry: CompanyEntry, key: str) -> bool:
    return key not in NOT_APPLICABLE_BY_SECTOR.get(entry.checkup.result.sector, {})


def _worked(entry: CompanyEntry, key: str) -> WorkedExample | None:
    metric = entry.checkup.result.by_key(key)
    if metric is None:
        return None
    return worked_example(metric, entry.checkup.history, entry.checkup.result.currency)


def example_for(site: Site, key: str) -> Example | None:
    """지표 key 의 예시. 계산할 수 있는 회사가 하나도 없으면 None."""
    default = default_example(site)
    # 기본 예시 회사는 일반 업종이라 17개 지표가 모두 판정 대상이다 — 늘 맨 앞.
    rest = [e for e in by_revenue(site) if e is not default and _applies(e, key)]
    candidates = ([default] if default is not None else []) + rest
    for entry in candidates:
        worked = _worked(entry, key)
        if worked is not None:
            return Example(entry, worked, entry is default)
    return None
