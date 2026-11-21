"""'다음에 읽어볼 것' — 해설·배우기 페이지 맨 아래 2~3개 링크.

**정적 관계표다.** 어떤 회사의 지표 값이나 방문 기록으로 고르지 않는다 — 고르는 기준이 숫자면 "이걸 보라" 는
신호가 되고, 끝없이 이어지는 추천 피드가 된다. 주제가 이어지는 해설끼리만 손으로 묶었다.
관계표의 대상이 실제로 빌드되는지는 `tests/test_site_related.py` 가 본다.
"""

from __future__ import annotations

from dataclasses import dataclass

from fin_checkup.explain.metrics import METRIC_EXPLAINERS

#: 페이지 경로(사이트 내 디렉터리) → 다음에 읽어볼 페이지 경로 2~3개. 지표 해설은 `m/<key>/`.
RELATED: dict[str, tuple[str, ...]] = {
    # ── 지표 해설 ────────────────────────────────────────────────
    "m/operating_margin/": ("m/net_margin/", "m/operating_income_growth/", "m/interest_coverage/"),
    "m/net_margin/": ("m/operating_margin/", "m/roe/", "m/ocf_to_net_income/"),
    "m/roe/": ("m/roa/", "m/debt_ratio/", "m/net_margin/"),
    "m/roa/": ("m/roe/", "m/asset_turnover/", "learn/sectors/"),
    "m/debt_ratio/": ("m/equity_ratio/", "m/interest_coverage/", "learn/sectors/"),
    "m/current_ratio/": ("m/debt_ratio/", "m/inventory_turnover/", "m/receivable_turnover/"),
    "m/interest_coverage/": ("m/debt_ratio/", "m/operating_margin/", "learn/redflags/"),
    "m/equity_ratio/": ("m/debt_ratio/", "m/roe/", "learn/redflags/"),
    "m/revenue_growth/": ("m/operating_income_growth/", "m/net_income_growth/", "m/operating_margin/"),
    "m/operating_income_growth/": ("m/revenue_growth/", "m/operating_margin/", "m/net_income_growth/"),
    "m/net_income_growth/": ("m/net_margin/", "m/operating_income_growth/", "m/ocf_to_net_income/"),
    "m/operating_cash_flow/": ("m/ocf_to_net_income/", "m/fcf/", "learn/redflags/"),
    "m/ocf_to_net_income/": ("m/operating_cash_flow/", "m/net_margin/", "m/receivable_turnover/"),
    "m/fcf/": ("m/operating_cash_flow/", "m/ocf_to_net_income/", "m/current_ratio/"),
    "m/asset_turnover/": ("m/roa/", "m/inventory_turnover/", "learn/sectors/"),
    "m/inventory_turnover/": ("m/receivable_turnover/", "m/current_ratio/", "learn/sectors/"),
    "m/receivable_turnover/": ("m/inventory_turnover/", "m/ocf_to_net_income/", "m/asset_turnover/"),
    # ── 목록·배우기 ─────────────────────────────────────────────
    "m/": ("learn/first-read/", "learn/sectors/", "learn/glossary/"),
    "learn/first-read/": ("m/", "learn/sectors/", "learn/glossary/"),
    "learn/redflags/": ("learn/disclosures/", "m/interest_coverage/", "m/equity_ratio/"),
    "learn/disclosures/": ("learn/redflags/", "learn/glossary/", "learn/first-read/"),
    "learn/glossary/": ("learn/first-read/", "m/", "learn/sectors/"),
    "learn/sectors/": ("m/debt_ratio/", "m/roa/", "s/"),
}


@dataclass(frozen=True)
class NextRead:
    path: str
    title: str
    summary: str


def _describe(path: str) -> NextRead:
    if path.startswith("m/") and path != "m/":
        e = METRIC_EXPLAINERS[path[2:-1]]
        return NextRead(path, e.label, e.easy_name)
    # 배우기 페이지 모듈이 이 모듈을 쓰므로 여기서 늦게 불러온다(순환 import).
    from fin_checkup.site.pages.learn import GUIDES

    guide = next(g for g in GUIDES if g.path == path)
    return NextRead(path, guide.title, guide.summary)


def next_reads(path: str) -> tuple[NextRead, ...]:
    """이 페이지(사이트 내 디렉터리 경로) 아래에 붙일 링크. 관계표에 없으면 빈 튜플."""
    return tuple(_describe(p) for p in RELATED.get(path, ()))
