"""배우기 `/learn/` — 허브, 재무제표 처음 읽기, 위험 신호·위험 공시 유형·용어집 페이지."""

from __future__ import annotations

import html
import re
from datetime import date
from pathlib import Path

import pytest
from hub_seed import seed_site_cache

from fin_checkup.explain import banned
from fin_checkup.explain.disclosures import HOW_TO_READ_ON_DART, disclosure_explainers
from fin_checkup.explain.glossary import GLOSSARY, GLOSSARY_BY_SLUG
from fin_checkup.explain.redflags import red_flag_explainers
from fin_checkup.metrics.signals import Signal
from fin_checkup.site.build import build_site
from fin_checkup.site.pages.learn import GLOSSARY_SECTIONS, GUIDES, KEY_NUMBERS
from fin_checkup.storage import Cache

LEARN_PAGES = ("learn", "learn/first-read", "learn/redflags", "learn/disclosures", "learn/glossary")


@pytest.fixture
async def out(tmp_path):
    with Cache(tmp_path / "site.duckdb") as cache:
        seed_site_cache(cache)
        target = tmp_path / "out"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    return target


def read(out: Path, page: str) -> str:
    return html.unescape((out / page / "index.html").read_text(encoding="utf-8"))


def body_text(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text.split("<body>", 1)[1])


def section(text: str, ident: str) -> str:
    match = re.search(rf'<section[^>]*id="{ident}".*?</section>', text, re.S)
    assert match, ident
    return match.group(0)


async def test_hub_links_every_guide_and_every_target_exists(out):
    hub = read(out, "learn")
    for g in GUIDES:
        assert f'href="../{g.path}"' in hub, g.path
        assert (out / g.path / "index.html").exists(), g.path


async def test_hub_keeps_the_signal_legend(out):
    hub = read(out, "learn")
    for signal in Signal:
        assert signal.emoji in hub and signal.label in hub


async def test_first_read_walks_the_default_example_company(out):
    """삼성전자 — 시드에서 일반 업종 중 매출액 최대. 지표 해설 페이지와 같은 회사다."""
    text = read(out, "learn/first-read")
    assert "오늘 같이 읽을 회사: 삼성전자" in text
    for anchor in ("summary", "metrics", "trend", "red-flags", "changes"):
        assert f'href="../../c/005930/#{anchor}"' in text, anchor
    assert (out / "c" / "005930" / "index.html").exists()
    assert "색과 상관없는 고정 규칙" in text


async def test_first_read_shows_where_numbers_come_from(out):
    text = section(read(out, "learn/first-read"), "source")
    assert "DART" in text and "사업보고서" in text
    for _field, label, statement, _slug in KEY_NUMBERS:
        assert label in text and statement in text
    assert "매출액</a></dt><dd>900원" in text, "시드의 삼성전자 2024 매출액"


async def test_first_read_uses_the_right_particle_for_the_name(out):
    text = read(out, "learn/first-read")
    assert "삼성전자는" in text and "삼성전자은" not in text


async def test_first_read_says_what_the_tool_cannot_tell(out):
    limits = section(read(out, "learn/first-read"), "limits")
    for phrase in ("주가", "앞으로의 실적", "사업의 내용", "사고팔 때"):
        assert phrase in limits


async def test_first_read_without_companies_still_renders(tmp_path):
    with Cache(tmp_path / "empty.duckdb") as cache:
        target = tmp_path / "out"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    assert "예시로 쓸 회사가 없어요" in read(target, "learn/first-read")


async def test_redflags_page_renders_every_explainer_with_anchor(out):
    text = read(out, "learn/redflags")
    for e in red_flag_explainers():
        block = section(text, e.key)
        assert e.title in block and e.what in block and e.why_matters in block and e.detection in block


async def test_disclosures_page_renders_kinds_and_how_to_read_on_dart(out):
    text = read(out, "learn/disclosures")
    for line in HOW_TO_READ_ON_DART:
        assert line in section(text, "how-to-read")
    for e in disclosure_explainers():
        block = section(text, e.kind.value)
        assert e.label in block and e.what in block and e.where_to_look in block
        for title in e.example_titles:
            assert title in block
    assert "🚨" not in text, "긴급하게 읽히는 알림 강도 표시는 싣지 않는다"


async def test_glossary_has_every_term_with_anchor_and_working_links(out):
    text = read(out, "learn/glossary")
    for t in GLOSSARY:
        assert f'<dt id="{t.slug}">' in text and t.definition in text, t.slug
        for key in t.metrics:
            assert f'href="../../m/{key}/"' in text
        for s in t.see_also:
            assert f'href="#{s}"' in text
    for path in re.findall(r'href="\.\./\.\./([^"#]*/)["#]', text):
        assert (out / path / "index.html").exists(), path


def test_glossary_sections_start_at_real_terms():
    assert set(GLOSSARY_SECTIONS) <= set(GLOSSARY_BY_SLUG)
    assert GLOSSARY[0].slug in GLOSSARY_SECTIONS


async def test_metric_page_terms_link_to_the_glossary(out):
    text = read(out, "m/roe")
    assert 'href="../../learn/glossary/#equity"' in text


async def test_learn_pages_use_haeyo_style_and_no_banned_phrases(out):
    for page in LEARN_PAGES:
        text = read(out, page)
        assert not banned.find(body_text(text)), (page, banned.find(body_text(text)))
        main = re.sub(r"<[^>]+>", " ", text.split("<main", 1)[1].split("</main>", 1)[0])
        assert "습니다" not in main, f"{page}: 해요체로 쓴다"
