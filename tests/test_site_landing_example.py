"""첫 화면 — 검색·한 줄 소개·결과가 어떻게 보이는지 예시 하나, 데이터 기준일은 한 줄(자세히는 한 번 눌러).

사용성 조사(2026-11-21): 휴대폰 첫 화면 대부분을 '데이터 기준일' 상자가 차지하고, 회사를 검색하면 무엇이
나오는지 보여 주는 것이 없었다. 예시 회사는 '재무제표 처음 읽기' 와 같은 고정 규칙(`examples.default_example`,
매출액 최대 일반 업종 회사)으로 고른다 — 색으로 고르지 않고, 순위·인기 목록을 만들지 않는다.
"""

from __future__ import annotations

import html
import re
from datetime import date

import pytest
from hub_seed import seed_site_cache

from fin_checkup.site.build import build_site
from fin_checkup.storage import Cache


@pytest.fixture
async def out(tmp_path):
    with Cache(tmp_path / "site.duckdb") as cache:
        seed_site_cache(cache)
        target = tmp_path / "out"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    return target


def landing(out) -> str:
    return html.unescape((out / "index.html").read_text(encoding="utf-8"))


def example_card(text: str) -> str:
    match = re.search(r'<section class="fc-example".*?</section>', text, re.S)
    assert match, "첫 화면에 결과 예시가 없다"
    return match.group(0)


def test_example_card_shows_the_fixed_example_company_and_links_to_it(out):
    card = example_card(landing(out))
    # 일반 업종 중 매출액 최대 — 시드에서는 삼성전자(KB금융은 금융지주라 빠진다).
    assert "삼성전자" in card and "KB금융" not in card
    assert 'href="./c/005930/"' in card
    assert 'href="./learn/first-read/"' in card
    assert "매출액" in card and "색" in card, "고르는 규칙을 한 줄로 밝힌다"


def test_example_card_is_the_real_glance_of_that_company(out):
    """회사 페이지 한눈에 보기의 첫 묶음과 같은 지표·같은 신호·같은 순서 — 꾸민 예시가 아니다."""
    text = landing(out)
    card = example_card(text)
    company = html.unescape((out / "c" / "005930" / "index.html").read_text(encoding="utf-8"))
    glance = re.search(r'<section[^>]*id="glance".*?</section>', company, re.S).group(0)
    first_group = re.search(r"<dd><ul class=\"fc-glance-list\">(.*?)</ul></dd>", glance, re.S).group(1)
    expected = re.findall(r'<li class="sig-(\w+)"><a href="#m-(\w+)">', first_group)
    shown = re.findall(r'<li class="sig-(\w+)"><a href="\./c/005930/#m-(\w+)">', card)
    assert expected and shown == expected
    # 신호 개수 요약도 회사 페이지와 같다.
    chips = re.findall(r'class="fc-chip sig-(\w+)".*?<b>(\d+)</b>', company)
    assert re.findall(r'class="fc-chip sig-(\w+)".*?<b>(\d+)</b>', card) == chips


def test_example_comes_right_after_search_before_market_disclosures(out):
    text = landing(out)
    assert text.index('type="search"') < text.index('class="fc-example"')


def test_as_of_is_one_line_with_details_one_tap_away(out):
    text = landing(out)
    box = re.search(r'<aside class="fc-season[^"]*".*?</aside>', text, re.S).group(0)
    summary = re.search(r"<summary>(.*?)</summary>", box, re.S)
    assert summary, "기준일 상자는 접혀 있어야 한다"
    line = re.sub(r"<[^>]+>", "", summary.group(1))
    assert "2024 사업연도 사업보고서" in line and "상장사 3곳" in line and "2026-11-21" in line
    # 반영 전인 사업연도는 접힌 한 줄에서도 밝힌다.
    assert "2025 사업연도" in line
    assert "<details" in box and "<details open" not in box
    # 첫 화면에 기준일을 두 번 쓰지 않는다.
    assert text.count("데이터 기준: 2024 사업연도 사업보고서") == 1


def test_company_page_keeps_the_full_season_box(out):
    text = html.unescape((out / "c" / "005930" / "index.html").read_text(encoding="utf-8"))
    box = re.search(r'<aside class="fc-season[^"]*".*?</aside>', text, re.S).group(0)
    assert "<details" not in box and "보통 이때 새 숫자가 나와요" in box


def test_landing_has_no_rankings_or_popular_lists(out):
    text = landing(out)
    for word in ("순위", "인기", "많이 본", "TOP", "상위", "추천"):
        assert word not in text, word
