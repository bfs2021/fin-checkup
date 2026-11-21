"""업종 이름이 실제 구성을 말한다 — KSIC 64 에는 은행만이 아니라 비금융 지주회사가 더 많다.

라이브 사이트에서 에코프로(배터리 소재 지주회사, 64992)는 "일반 기준" 으로 판정되는데 첫 화면 업종 줄과
지표마다 "금융업 업종 분포" 가 붙어, 처음 보는 사람이 "에코프로가 금융회사?" 에서 멈췄다.
대조군(KSIC 두 자리)은 그대로 두고, 이름만 구성대로 고친다.
"""

from __future__ import annotations

import html
from datetime import date

import pytest
from test_site_sector import HOLDING, seed_group

from fin_checkup.explain.sectors import peer_group_info
from fin_checkup.site.build import build_site
from fin_checkup.storage import Cache


@pytest.fixture
async def out(tmp_path):
    with Cache(tmp_path / "s.duckdb") as cache:
        seed_group(cache)
        target = tmp_path / "out"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    return target


def test_ksic_64_name_says_it_holds_holding_companies():
    info = peer_group_info("64")
    assert "지주회사" in info.name
    assert "비금융 지주" in info.plain


def test_non_financial_holding_page_names_its_group_with_holding_companies(out):
    text = html.unescape((out / "c" / HOLDING.stock_code / "index.html").read_text(encoding="utf-8"))
    assert "일반 기준" in text, "비금융 지주는 일반 기준으로 판정한다(이름만 바꾼다)"
    assert "금융업·지주회사</a> (KSIC 64" in text
