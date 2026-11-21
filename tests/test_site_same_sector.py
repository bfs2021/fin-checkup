"""회사 페이지 "같은 업종 회사" — 이름순 이웃만, 값으로 고르지 않음, 업종 페이지 전체 보기 링크."""

from __future__ import annotations

import html
import re
from datetime import date

import pytest
from test_site_sector import EXTRA_26, seed_group

from fin_checkup.site.build import build_site
from fin_checkup.site.pages.same_sector import LIMIT, neighbours
from fin_checkup.storage import Cache


@pytest.fixture
async def out(tmp_path):
    with Cache(tmp_path / "site.duckdb") as cache:
        seed_group(cache)
        target = tmp_path / "out"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    return target


def same_sector(out, code: str) -> str | None:
    text = html.unescape((out / "c" / code / "index.html").read_text(encoding="utf-8"))
    match = re.search(r'<section[^>]*id="same-sector".*?</section>', text, re.S)
    return match.group(0) if match else None


@pytest.mark.parametrize(
    ("index", "expected"),
    [
        (0, list(range(1, 13))),
        (2, [0, 1, *range(3, 13)]),
        (10, [*range(4, 10), *range(11, 17)]),
        (29, list(range(17, 29))),
        (27, [*range(17, 27), 28, 29]),  # 끝에 닿으면 앞에서 더 가져온다
    ],
)
def test_neighbours_are_a_name_order_window_around_the_company(index, expected):
    members = list(range(30))
    got = neighbours(members, index)
    assert len(got) == LIMIT
    assert index not in got
    assert got == sorted(got), "이름순 그대로"
    assert got == expected


def test_small_group_lists_everyone_else():
    assert neighbours(["가", "나", "다"], 1) == ["가", "다"]


async def test_company_page_lists_same_sector_companies_in_name_order(out):
    block = same_sector(out, "005930")
    assert block is not None
    names = re.findall(r'<li><a href="[^"]+">([^<]+)</a>', block)
    assert names == sorted(n for n, *_ in EXTRA_26), "삼성전자 자신은 빠지고 나머지 5곳이 이름순"
    assert "지표 값으로 고르지 않았습니다" in block
    assert 'href="../../s/26/#members"' in block and "전체 6곳 보기" in block


async def test_no_section_without_a_peer_group_or_peers(out):
    assert same_sector(out, "028300") is None, "업종코드 없음"


async def test_two_company_group_lists_the_other_one(out):
    block = same_sector(out, "105560")
    assert block is not None and "가나지주" in block
