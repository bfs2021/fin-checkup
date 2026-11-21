"""지표 해설 페이지 `/m/` — 엔진의 계산식·경계값, ⊘ 업종과 대신 볼 것, 색과 무관한 예시 회사."""

from __future__ import annotations

import html
import re
from datetime import date

import pytest
from hub_seed import DELISTED, HLB, KB, NO_DATA, SAMSUNG, UNLISTED, seed_site_cache, statements
from site_text import unmark

from fin_checkup.explain import banned
from fin_checkup.explain.metrics import explainers, get_explainer, threshold_text
from fin_checkup.metrics.engine import METRIC_DEFS
from fin_checkup.metrics.sector import Sector
from fin_checkup.models import AccountLine, Company, CorpCode, Market
from fin_checkup.site.build import build_site
from fin_checkup.storage import Cache

#: 삼성전자(일반, 매출 900)보다 작은 일반 업종 회사. 유형자산 취득이 공시돼 FCF 를 계산할 수 있다.
SMALL = CorpCode(corp_code="00700000", corp_name="가나설비", stock_code="300001")


def seed(cache: Cache) -> None:
    seed_site_cache(cache)
    # save_corp_codes 는 표를 통째로 바꾼다 — 시드 회사와 함께 넣는다.
    cache.save_corp_codes([SAMSUNG, KB, HLB, NO_DATA, UNLISTED, DELISTED, SMALL])
    cache.save_company(
        Company(
            corp_code=SMALL.corp_code,
            corp_name=SMALL.corp_name,
            stock_code=SMALL.stock_code,
            market=Market.KOSDAQ,
            industry_code="29120",
        )
    )
    raw = statements(SMALL.corp_code, 2024, 500.0, 50.0)
    raw.lines.append(
        AccountLine(
            sj_div="CF",
            account_id="ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
            account_nm="유형자산의 취득",
            thstrm_amount=-300.0,
            ord=13,
        )
    )
    cache.save_statements(raw)


@pytest.fixture
async def out(tmp_path):
    with Cache(tmp_path / "site.duckdb") as cache:
        seed(cache)
        target = tmp_path / "out"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    return target


def read(out, *parts) -> str:
    return unmark(html.unescape(out.joinpath(*parts).read_text(encoding="utf-8")))


def section(text: str, ident: str) -> str:
    match = re.search(rf'<section[^>]*id="{ident}".*?</section>', text, re.S)
    assert match, ident
    return match.group(0)


def visible(text: str) -> str:
    """본문만 (head 의 메타·주석 빼고) — 금지 문구 검사용."""
    body = text.split("<body>", 1)[1]
    return re.sub(r"<[^>]+>", " ", body)


async def test_one_page_per_metric_and_an_index_in_engine_order(out):
    index = read(out, "m", "index.html")
    links = re.findall(r'href="\.\./m/([a-z_]+)/"', index)
    assert links == [d.key for d in METRIC_DEFS]
    for spec in METRIC_DEFS:
        assert (out / "m" / spec.key / "index.html").exists(), spec.key


async def test_page_shows_formula_threshold_and_plain_text_from_explain(out):
    for e in explainers():
        text = read(out, "m", e.key, "index.html")
        assert e.formula in text and threshold_text(e.key) in text, e.key
        assert e.one_liner in text and e.why_look in text and e.basis in text, e.key
        for pitfall in e.pitfalls:
            assert pitfall in text, e.key


async def test_sector_bands_and_not_applicable_sectors_are_spelled_out(out):
    roa = section(read(out, "m", "roa", "index.html"), "formula")
    assert threshold_text("roa", Sector.FINANCIAL) in roa, "금융업 ROA 는 다른 경계값을 쓴다"
    debt = section(read(out, "m", "debt_ratio", "index.html"), "sectors")
    caveat = get_explainer("debt_ratio").caveat_for(Sector.FINANCIAL)
    assert "⊘" in debt and "금융업" in debt and caveat.why in debt
    assert "대신 볼 것" in debt and caveat.instead in debt


async def test_special_rules_show_symbol_and_label(out):
    text = section(read(out, "m", "interest_coverage", "index.html"), "formula")
    for rule in get_explainer("interest_coverage").special_rules:
        assert rule.when in text
        assert f"{rule.signal.emoji} {rule.signal.label}" in text


async def test_example_is_the_largest_revenue_general_company_for_every_metric(out):
    """KB금융은 매출이 더 크지만 금융업 기준이라 기본 예시가 아니다. 색은 보지 않는다."""
    for key in ("operating_margin", "roa", "debt_ratio", "revenue_growth"):
        ex = section(read(out, "m", key, "index.html"), "example")
        assert "삼성전자</a>의 2024 사업연도" in ex, key
        assert "KB금융" not in ex, key
        assert "다른 회사를 썼어요" not in ex


async def test_example_falls_back_by_revenue_when_the_default_cannot_compute(out):
    """삼성전자 시드에는 유형자산 취득이 없어 FCF 가 ⚫ — 다음으로 계산할 수 있는 회사를 쓴다."""
    ex = section(read(out, "m", "fcf", "index.html"), "example")
    assert "가나설비</a>의 2024 사업연도" in ex
    assert "다른 회사를 썼어요" in ex
    assert "900원 − 300원" in ex and "<b>600원</b>" in ex


async def test_no_example_when_nobody_discloses_the_numbers(out):
    ex = section(read(out, "m", "receivable_turnover", "index.html"), "example")
    assert "예시를 싣지 않았어요" in ex and "0으로 채우지 않아요" in ex


async def test_example_shows_arithmetic_and_the_rule_but_no_signal(out):
    ex = section(read(out, "m", "operating_margin", "index.html"), "example")
    assert "40원 ÷ 900원 × 100" in ex and f"{40 / 900 * 100:,.2f}%" in ex
    assert "손익계산서" in ex
    assert "색과 상관없는 고정 규칙" in ex and "매출액이 가장 큰" in ex
    for sig in ("🟢", "🟡", "🔴"):
        assert sig not in ex, "예시는 계산 과정만 — 판정 색은 회사 페이지에서"
    assert 'href="../../c/005930/#m-operating_margin"' in read(out, "m", "operating_margin", "index.html")


async def test_glossary_terms_for_the_metric_are_listed(out):
    from fin_checkup.explain.glossary import terms_for_metric

    terms = terms_for_metric("roe")
    assert terms
    text = read(out, "m", "roe", "index.html")
    for t in terms:
        assert t.term in text and t.definition in text


async def test_company_metric_rows_link_to_their_explainer(out):
    text = read(out, "c", "005930", "index.html")
    for spec in METRIC_DEFS:
        assert f'href="../../m/{spec.key}/"' in text, spec.key


async def test_metric_pages_have_no_banned_phrases(out):
    pages = [out / "m" / "index.html", *sorted((out / "m").glob("*/index.html"))]
    for path in pages:
        found = banned.find(visible(html.unescape(path.read_text(encoding="utf-8"))))
        assert not found, (path, found)
