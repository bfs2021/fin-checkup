"""회사 페이지 "한눈에 보기" — 첫 화면에서 어느 지표가 어떤 신호인지, 위험 신호가 있는지를 사실만으로.

휴대폰에서 지표 카드 17장은 10화면이 넘는다. 첫 화면에 신호 개수만 있으면 "위험 5" 가 무엇인지 모른 채
스크롤해야 하고, 맨 아래 "위험 신호 없음" 과 모순돼 보인다. 그래서 카드 순서 그대로 지표 이름·신호를 묶음별로
미리 보여 주고, 위험 신호 유무와 둘의 차이를 한 줄로 적는다. 새 점수·판단은 만들지 않는다.
"""

from __future__ import annotations

import html
import re
from datetime import date
from types import SimpleNamespace

import pytest
from hub_seed import HLB, KB, SAMSUNG, seed_site_cache

from fin_checkup.metrics.redflags import RedFlag
from fin_checkup.site.build import build_site
from fin_checkup.site.guard import check_site
from fin_checkup.site.render import make_env
from fin_checkup.storage import Cache

CODES = [SAMSUNG.stock_code, KB.stock_code, HLB.stock_code]


@pytest.fixture
async def out(tmp_path):
    with Cache(tmp_path / "site.duckdb") as cache:
        seed_site_cache(cache)
        target = tmp_path / "out"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    return target


def page(out, code: str) -> str:
    return html.unescape((out / "c" / code / "index.html").read_text(encoding="utf-8"))


def section(text: str, ident: str) -> str:
    match = re.search(rf'<section[^>]*id="{ident}".*?</section>', text, re.S)
    assert match, f"#{ident} 절이 없다"
    return match.group(0)


@pytest.mark.parametrize("code", CODES)
def test_glance_comes_first_before_actions_and_metric_cards(out, code):
    text = page(out, code)
    assert text.index('id="glance"') < text.index('id="actions"') < text.index('id="metrics"')


@pytest.mark.parametrize("code", CODES)
def test_glance_lists_every_metric_card_in_card_order_with_its_signal(out, code):
    text = page(out, code)
    cards = re.findall(r'<li class="fc-metric sig-(\w+)" id="m-(\w+)"', text)
    assert cards, "지표 카드가 없다"
    glance = section(text, "glance")
    links = re.findall(r'<li class="sig-(\w+)"><a href="#m-(\w+)">', glance)
    assert links == cards, "한눈에 보기는 카드와 같은 지표·같은 신호·같은 순서여야 한다"


@pytest.mark.parametrize("code", CODES)
def test_glance_states_red_flags_as_they_are(out, code):
    text = page(out, code)
    flags = re.findall(r"<b>([^<]+)</b> —", section(text, "red-flags"))
    glance = section(text, "glance")
    assert 'href="#red-flags"' in glance
    if flags:
        for label in flags:
            assert label in glance
    else:
        assert "위험 신호" in glance and "없음" in glance


def test_glance_says_a_signal_is_a_measurement_and_links_how_to_read(out):
    glance = section(page(out, SAMSUNG.stock_code), "glance")
    assert "경계값" in glance
    assert "투자 판단이 아닙니다" in glance
    assert 'learn/#legend"' in glance


def test_glance_passes_the_site_guard(out):
    assert check_site(out) == []


def test_glance_names_each_red_flag_when_there_are_some():
    """시드에는 위험 신호가 있는 회사가 없어 부분 템플릿을 직접 그린다."""
    flags = [
        RedFlag("partial_capital_impairment", "자본잠식률 50% 이상", "2024년 자본잠식률이 62.0%다."),
        RedFlag("consecutive_operating_loss", "4년 연속 영업손실", "2021~2024년 영업이익이 연속 음수다."),
    ]
    c = SimpleNamespace(groups=[], red_flags=flags)
    out = make_env().get_template("company/_glance.html").render(c=c, root="../../")
    assert out.count('<li class="sig-red"><a href="#red-flags">') == 2
    for flag in flags:
        assert flag.label in out
    assert ">없음<" not in out
