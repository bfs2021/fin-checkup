"""위험 공시 유형 해설이 분류 코드(alerts/classify.py)와 어긋나지 않는지."""

from __future__ import annotations

import pytest

from fin_checkup.alerts.classify import PATTERNS, RiskKind, classify
from fin_checkup.explain import banned
from fin_checkup.explain.disclosures import (
    DISCLOSURE_EXPLAINERS,
    HOW_TO_READ_ON_DART,
    disclosure_explainers,
    get_disclosure_explainer,
)
from fin_checkup.models import Disclosure


def test_every_risk_kind_has_an_explainer_and_vice_versa():
    assert set(DISCLOSURE_EXPLAINERS) == set(RiskKind)
    assert [e.kind for e in disclosure_explainers()] == list(RiskKind)


def test_lookup_by_value():
    assert get_disclosure_explainer("capital_raise").kind is RiskKind.CAPITAL_RAISE


def test_label_and_severity_come_from_classify():
    for e in disclosure_explainers():
        assert e.label == e.kind.label
        assert e.severity is e.kind.severity


def test_matched_phrases_are_exactly_the_classify_patterns():
    union = [p for e in disclosure_explainers() for p in e.matched_phrases]
    assert sorted(union) == sorted(p for _k, p in PATTERNS)
    for e in disclosure_explainers():
        assert e.matched_phrases, e.kind


@pytest.mark.parametrize("e", disclosure_explainers(), ids=lambda e: e.kind.value)
def test_example_titles_classify_into_their_kind(e):
    assert e.example_titles
    for title in e.example_titles:
        d = Disclosure(rcept_no="20240101000001", corp_code="00000000", corp_name="예시", report_nm=title)
        result = classify(d)
        assert result is not None and result.kind is e.kind, title


def test_every_field_is_filled():
    for e in disclosure_explainers():
        for text in (e.what, e.shareholder_meaning, e.where_to_look):
            assert text.strip(), e.kind
    assert HOW_TO_READ_ON_DART


def test_dilution_mechanism_is_stated_for_new_shares():
    """유상증자·CB 는 '주식 수 증가 → 지분 희석' 구조를 말해야 한다."""
    for kind in (RiskKind.CAPITAL_RAISE, RiskKind.CONVERTIBLE_BOND):
        meaning = get_disclosure_explainer(kind).shareholder_meaning
        assert "주식 수" in meaning and "희석" in meaning


def test_no_banned_or_action_phrase():
    texts = list(banned.iter_strings(disclosure_explainers())) + list(HOW_TO_READ_ON_DART)
    assert [(t, p) for t in texts for p in banned.find(t)] == []
    # 행동 지시 — 알림은 사실 + 원문 링크까지다.
    for t in texts:
        for word in ("그러니", "팔아", "사야", "손절", "익절", "서두르"):
            assert word not in t, (word, t)
