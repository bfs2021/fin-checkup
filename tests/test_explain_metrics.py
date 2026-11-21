"""지표 해설 데이터가 엔진과 어긋나지 않는지.

해설은 사람이 쓰지만 공식·경계값·⊘ 업종은 엔진에서 가져와야 한다. 엔진의 경계값을
바꿨는데 해설이 옛 숫자를 말하면, 화면의 색과 설명이 서로 다른 말을 하게 된다.
"""

from __future__ import annotations

import dataclasses

import pytest

from fin_checkup.explain import banned
from fin_checkup.explain.metrics import (
    METRIC_EXPLAINERS,
    band_ranges,
    explainers,
    get_explainer,
    threshold_text,
)
from fin_checkup.metrics.engine import METRIC_DEFS, NOT_APPLICABLE_BY_SECTOR, checkup
from fin_checkup.metrics.sector import Sector
from fin_checkup.metrics.signals import Band, Signal
from fin_checkup.models import Financials, FsDiv, InterestSource, ReportCode

ENGINE_KEYS = [d.key for d in METRIC_DEFS]


def fin(**kwargs) -> Financials:
    base = dict(corp_code="00000000", bsns_year=2024, reprt_code=ReportCode.ANNUAL, fs_div=FsDiv.CFS)
    return Financials(**{**base, **kwargs})


# ── 엔진과 1:1 ─────────────────────────────────────────────────────


def test_every_engine_metric_has_an_explainer_and_vice_versa():
    assert set(METRIC_EXPLAINERS) == set(ENGINE_KEYS)


def test_explainers_follow_engine_order():
    assert [e.key for e in explainers()] == ENGINE_KEYS


def test_formula_label_unit_come_from_engine():
    for spec in METRIC_DEFS:
        e = get_explainer(spec.key)
        assert e.formula == spec.formula
        assert e.label == spec.label
        assert e.unit == spec.unit
        assert e.category is spec.category


def test_unknown_key_raises():
    with pytest.raises(KeyError):
        get_explainer("nope")


def test_every_text_field_is_filled():
    for e in explainers():
        for name in ("easy_name", "one_liner", "why_look", "basis"):
            assert getattr(e, name).strip(), f"{e.key}.{name} 이 비었다"
        assert e.pitfalls, f"{e.key} 에 한계/함정이 없다"
        for rule in e.special_rules:
            assert rule.when.strip() and rule.fact.strip(), (e.key, rule)


# ── 경계값 문장은 엔진 값에서 만든다 ────────────────────────────────


def _fmt(x: float) -> str:
    return f"{x:g}"


@pytest.mark.parametrize("key", ENGINE_KEYS)
def test_threshold_text_quotes_engine_band(key):
    spec = next(d for d in METRIC_DEFS if d.key == key)
    text = threshold_text(key)
    band = spec.band_for(Sector.GENERAL)
    if band is None:
        assert "⚪" in text
        return
    assert _fmt(band.good) in text
    assert _fmt(band.warn) in text
    assert "🟢" in text and "🔴" in text
    if band.good == band.warn:
        assert "🟡 주의 구간은 없어요" in text


def test_threshold_text_follows_a_changed_band(monkeypatch):
    """하드코딩이면 엔진 값을 바꿔도 문장이 그대로다."""
    from fin_checkup.metrics import engine

    spec = next(d for d in engine.METRIC_DEFS if d.key == "operating_margin")
    patched = tuple(
        dataclasses.replace(d, band=Band(good=12.5, warn=3)) if d is spec else d for d in engine.METRIC_DEFS
    )
    monkeypatch.setattr(engine, "METRIC_DEFS", patched)
    text = threshold_text("operating_margin")
    assert "12.5%" in text and "3%" in text and "7%" not in text


def test_threshold_text_uses_sector_band_for_financial_roa():
    text = threshold_text("roa", Sector.FINANCIAL)
    assert "1%" in text and "0.5%" in text


def test_threshold_text_says_not_applicable_for_sector():
    text = threshold_text("debt_ratio", Sector.FINANCIAL)
    assert "⊘" in text and "금융업" in text


def test_band_ranges_cover_lower_is_better():
    ranges = band_ranges(Band(good=100, warn=200, higher_is_better=False), "%")
    assert ranges == {
        Signal.GREEN: "100% 이하",
        Signal.YELLOW: "100% 초과 200% 이하",
        Signal.RED: "200% 초과",
    }


def test_band_ranges_without_yellow():
    ranges = band_ranges(Band(good=0, warn=0), "money")
    assert Signal.YELLOW not in ranges
    assert ranges[Signal.GREEN] == "0 이상"


# ── ⊘ 업종은 sector 규칙과 같다 ────────────────────────────────────


def test_sector_caveats_match_engine_not_applicable_table():
    from_engine = {(sector, key) for sector, table in NOT_APPLICABLE_BY_SECTOR.items() for key in table}
    from_explain = {(c.sector, e.key) for e in explainers() for c in e.sector_caveats}
    assert from_explain == from_engine


def test_every_sector_caveat_says_what_to_look_at_instead():
    for e in explainers():
        for c in e.sector_caveats:
            assert c.why.strip() and c.instead.strip(), (e.key, c.sector)
            assert e.caveat_for(c.sector) is c


# ── 특수 규칙은 엔진이 실제로 그렇게 판정한다 ─────────────────────────

#: (지표, 당해, 전년, 엔진이 내야 하는 신호). 해설의 special_rules 와 짝을 맞춘다.
SPECIAL_CASES = [
    ("roe", dict(net_income=10, total_equity=-5), None, Signal.UNKNOWN),
    ("debt_ratio", dict(total_liabilities=100, total_equity=0), None, Signal.RED),
    ("interest_coverage", dict(operating_income=10, interest_expense=0), None, Signal.GREEN),
    ("interest_coverage", dict(operating_income=10, interest_expense=4,
                               interest_expense_source=InterestSource.FINANCE_COSTS), None, Signal.NEUTRAL),
    ("interest_coverage", dict(operating_income=10, interest_expense=4,
                               interest_expense_source=InterestSource.NET_INTEREST), None, Signal.NEUTRAL),
    ("revenue_growth", dict(revenue=100), dict(revenue=0), Signal.UNKNOWN),
    ("operating_income_growth", dict(operating_income=10), dict(operating_income=-5), Signal.GREEN),
    ("operating_income_growth", dict(operating_income=-3), dict(operating_income=-5), Signal.RED),
    ("operating_income_growth", dict(operating_income=5), dict(operating_income=0), Signal.UNKNOWN),
    ("net_income_growth", dict(net_income=10), dict(net_income=-5), Signal.GREEN),
    ("net_income_growth", dict(net_income=-8), dict(net_income=-5), Signal.RED),
    ("net_income_growth", dict(net_income=5), dict(net_income=0), Signal.UNKNOWN),
    ("operating_cash_flow", dict(operating_cash_flow=-1, net_income=5), None, Signal.RED),
    ("ocf_to_net_income", dict(operating_cash_flow=5, net_income=-1), None, Signal.NOT_APPLICABLE),
    ("inventory_turnover", dict(revenue=100, inventories=0), None, Signal.NOT_APPLICABLE),
    ("receivable_turnover", dict(revenue=100, trade_receivables=0), None, Signal.NOT_APPLICABLE),
]


@pytest.mark.parametrize("key,cur,prior,expected", SPECIAL_CASES)
def test_special_rule_matches_engine(key, cur, prior, expected):
    result = checkup(fin(**cur), fin(bsns_year=2023, **prior) if prior else None)
    assert result.by_key(key).signal is expected
    assert expected in {r.signal for r in get_explainer(key).special_rules}


def test_every_special_rule_is_backed_by_an_engine_case():
    cases: dict[str, list[Signal]] = {}
    for key, _c, _p, sig in SPECIAL_CASES:
        cases.setdefault(key, []).append(sig)
    for e in explainers():
        assert sorted(r.signal.value for r in e.special_rules) == sorted(
            s.value for s in cases.get(e.key, [])
        ), e.key


# ── 금지 문구 ──────────────────────────────────────────────────────


def test_no_banned_phrase_in_metric_explanations():
    texts = list(banned.iter_strings(explainers()))
    texts += [threshold_text(k, s) for k in ENGINE_KEYS for s in Sector]
    assert texts
    hits = [(t, p) for t in texts for p in banned.find(t)]
    assert hits == []


def test_banned_lint_catches_examples():
    assert banned.find("이 종목 매수 추천") == ["추천", "매수"]
    assert banned.find("재무 우량주 TOP 10") == ["TOP", "우량"]
    assert banned.find("영업이익률은 영업이익 ÷ 매출액") == []
