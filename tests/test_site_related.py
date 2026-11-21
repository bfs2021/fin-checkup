"""상호 링크 — 지표 해설 ↔ 회사 지표 카드 ↔ 업종·시장 분포 ↔ 용어집, '다음에 읽어볼 것' 정적 관계표."""

from __future__ import annotations

import html
import re
from datetime import date

import pytest
from hub_seed import seed_site_cache

from fin_checkup.metrics.engine import METRIC_DEFS
from fin_checkup.site.build import build_site
from fin_checkup.site.related import RELATED, next_reads
from fin_checkup.storage import Cache

#: 맨 아래 상자가 붙어야 하는 페이지 — 지표 해설 17개 + 목록 + 배우기 가이드(허브 제외).
EXPECTED = {f"m/{d.key}/" for d in METRIC_DEFS} | {
    "m/",
    "learn/first-read/",
    "learn/redflags/",
    "learn/disclosures/",
    "learn/glossary/",
    "learn/sectors/",
}


@pytest.fixture
async def out(tmp_path):
    with Cache(tmp_path / "site.duckdb") as cache:
        seed_site_cache(cache)
        target = tmp_path / "out"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    return target


def read(out, path: str) -> str:
    return html.unescape((out / path / "index.html").read_text(encoding="utf-8"))


def next_box(text: str) -> str:
    match = re.search(r'<nav class="fc-section fc-next".*?</nav>', text, re.S)
    assert match
    return match.group(0)


def test_relation_map_covers_every_explainer_page_with_two_or_three_others():
    assert set(RELATED) == EXPECTED
    for path, targets in RELATED.items():
        assert 2 <= len(targets) <= 3, path
        assert path not in targets, path
        assert len(set(targets)) == len(targets), path


def test_relation_map_is_static_not_computed_from_company_values():
    """같은 입력이면 같은 답 — 빌드·회사와 무관하다 (함수 인자에 사이트가 없다)."""
    assert next_reads("m/roe/") == next_reads("m/roe/")
    assert [n.path for n in next_reads("m/roe/")] == list(RELATED["m/roe/"])


async def test_every_page_shows_its_box_and_every_link_resolves(out):
    for path in EXPECTED:
        box = next_box(read(out, path))
        targets = re.findall(r'href="([^"]+)"', box)
        assert len(targets) == len(RELATED[path]), path
        for href in targets:
            resolved = (out / path / href).resolve()
            assert (resolved / "index.html").exists(), (path, href)


async def test_company_metric_card_links_to_explainer_and_distribution(out):
    """삼성전자 업종(26)은 시드에 1곳뿐이라 업종 분포가 없다 → 시장 전체 분포로."""
    text = read(out, "c/005930")
    for spec in METRIC_DEFS:
        assert f'href="../../m/{spec.key}/"' in text, spec.key
        assert f'href="../../market/#d-{spec.key}"' in text, spec.key
    market = read(out, "market")
    for spec in METRIC_DEFS:
        assert f'id="d-{spec.key}"' in market


async def test_metric_page_links_to_market_distribution_card(out):
    text = read(out, "m/debt_ratio")
    assert 'href="../../market/#d-debt_ratio"' in text


async def test_sector_distribution_cards_link_back_to_explainers(out):
    text = read(out, "market")
    for spec in METRIC_DEFS:
        assert f'href="../m/{spec.key}/"' in text, spec.key


async def test_company_and_metric_pages_link_to_the_sector_distribution_when_it_exists(tmp_path):
    """업종 26 에 6곳(≥ MIN_PEERS) — 회사 카드와 해설 페이지가 업종 분포 카드로 간다."""
    from test_site_sector import seed_group

    with Cache(tmp_path / "site.duckdb") as cache:
        seed_group(cache)
        target = tmp_path / "out"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    company = read(target, "c/005930")
    assert 'href="../../s/26/#d-operating_margin"' in company
    explainer = read(target, "m/operating_margin")
    assert 'href="../../s/26/#d-operating_margin"' in explainer
    assert 'id="d-operating_margin"' in read(target, "s/26")


async def test_glossary_terms_link_to_the_pages_that_use_them(out):
    from fin_checkup.explain.glossary import GLOSSARY_BY_SLUG
    from fin_checkup.site.pages.learn import GLOSSARY_PAGE_LINKS

    assert set(GLOSSARY_PAGE_LINKS) <= set(GLOSSARY_BY_SLUG)
    text = read(out, "learn/glossary")
    median = re.search(r'<dt id="median">.*?</dd>', text, re.S).group(0)
    assert 'href="../../market/"' in median
    peer = re.search(r'<dt id="peer-group">.*?</dd>', text, re.S).group(0)
    assert 'href="../../s/"' in peer
