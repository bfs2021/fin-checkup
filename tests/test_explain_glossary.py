"""용어집 — 링크 대상이 실제로 있고, 정의는 한 줄이고, 금지 문구가 없다."""

from __future__ import annotations

import re

from fin_checkup.alerts.classify import RiskKind
from fin_checkup.explain import banned
from fin_checkup.explain.glossary import (
    GLOSSARY,
    GLOSSARY_BY_SLUG,
    find_term,
    get_term,
    terms_for_metric,
)
from fin_checkup.explain.metrics import METRIC_EXPLAINERS
from fin_checkup.explain.redflags import RED_FLAG_EXPLAINERS
from fin_checkup.metrics.peers import MIN_PEERS


def test_size_is_within_40_to_60():
    assert 40 <= len(GLOSSARY) <= 60


def test_slugs_and_terms_are_unique_and_url_safe():
    slugs = [t.slug for t in GLOSSARY]
    assert len(slugs) == len(set(slugs)) == len(GLOSSARY_BY_SLUG)
    assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s) for s in slugs)
    names = ["".join(n.split()) for t in GLOSSARY for n in (t.term, *t.aliases)]
    assert len(names) == len(set(names)), "같은 이름이 두 용어에 걸려 있다"


def test_every_link_target_exists():
    for t in GLOSSARY:
        for key in t.metrics:
            assert key in METRIC_EXPLAINERS, (t.slug, key)
        for key in t.red_flags:
            assert key in RED_FLAG_EXPLAINERS, (t.slug, key)
        for kind in t.disclosures:
            assert isinstance(kind, RiskKind), (t.slug, kind)
        for slug in t.see_also:
            assert slug in GLOSSARY_BY_SLUG and slug != t.slug, (t.slug, slug)


def test_every_metric_and_red_flag_is_reachable_from_the_glossary():
    linked_metrics = {k for t in GLOSSARY for k in t.metrics}
    assert linked_metrics == set(METRIC_EXPLAINERS)
    linked_flags = {k for t in GLOSSARY for k in t.red_flags}
    assert linked_flags == set(RED_FLAG_EXPLAINERS)
    assert {k for t in GLOSSARY for k in t.disclosures} == set(RiskKind)


def test_definitions_are_one_plain_line():
    for t in GLOSSARY:
        assert "\n" not in t.definition, t.slug
        assert re.search(r"요(\([^)]*\))?\.$", t.definition), t.slug


def test_lookups():
    assert get_term("fcf").term == "잉여현금흐름"
    assert find_term("FCF") is get_term("fcf")
    assert find_term("판관비") is get_term("sga")
    assert find_term("자본 총계") is get_term("equity")
    assert find_term("없는 말") is None
    assert get_term("interest-expense") in terms_for_metric("interest_coverage")


def test_numbers_come_from_code():
    assert f"{MIN_PEERS}곳" in get_term("peer-group").definition


def test_no_banned_phrase():
    texts = list(banned.iter_strings(GLOSSARY))
    assert [(t, p) for t in texts for p in banned.find(t)] == []
