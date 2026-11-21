"""돌아온 사람의 길 — 첫 화면의 '이어 보기' 와, 메뉴로 들어간 나란히 보기가 고른 회사를 지키는지.

라이브 사이트에서 회사 두 곳의 "비교에 추가" 를 누른 뒤 상단 메뉴 "나란히 보기"(`/compare/`)로 가면
고른 회사가 지워졌다 — 주소에 `?c=` 가 없으면 빈 목록을 그리고 저장소까지 비웠다. 또 관심종목을 담고
첫 화면으로 돌아와도 처음 방문과 똑같아, 담아 둔 것으로 가는 길이 메뉴 한 단어뿐이었다.
"""

from __future__ import annotations

import re
from datetime import date

import pytest
from hub_seed import HLB, SAMSUNG, seed_site_cache

from fin_checkup.site.build import build_site
from fin_checkup.site.guard import check_site
from fin_checkup.storage import Cache


@pytest.fixture
async def out(tmp_path):
    with Cache(tmp_path / "s.duckdb") as cache:
        seed_site_cache(cache)
        target = tmp_path / "out"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    return target


def test_landing_has_a_hidden_resume_line_and_loads_its_script(out):
    text = (out / "index.html").read_text(encoding="utf-8")
    line = re.search(r'<p class="fc-resume" id="fc-resume" hidden>.*?</p>', text, re.S)
    assert line, "이어 보기 줄은 처음엔 숨어 있다"
    assert 'href="./watch/"' in line.group(0) and 'href="./compare/"' in line.group(0)
    assert '<script src="./assets/resume.js" defer></script>' in text
    assert (out / "assets" / "resume.js").exists()


def test_resume_passes_the_site_guard(out):
    assert check_site(out) == []


def test_browser_menu_compare_keeps_the_picked_companies_and_landing_offers_the_way_back(out):
    from site_browser import chromium, serve

    with serve(out) as base, chromium() as browser:
        page = browser.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(base)
        assert not page.locator("#fc-resume").is_visible(), "담은 것이 없으면 보이지 않는다"

        heads = page.locator("thead .fc-compare-company a")
        for code in (SAMSUNG.stock_code, HLB.stock_code):
            page.goto(base + f"c/{code}/")
            page.get_by_role("link", name="비교에 추가").click()
            heads.first.wait_for()

        # 상단 메뉴로 들어가도 고른 두 곳이 그대로다.
        page.goto(base + "compare/")
        heads.nth(1).wait_for()
        assert heads.all_text_contents() == ["삼성전자", "에이치엘비"]
        assert page.url.endswith("compare/?c=005930,028300")

        page.goto(base)
        resume = page.locator("#fc-resume")
        resume.wait_for(state="visible")
        assert page.locator('[data-resume="compare"]').is_visible()
        assert not page.locator('[data-resume="watch"]').is_visible()

        page.goto(base + f"c/{SAMSUNG.stock_code}/")
        toggle = page.locator(".fc-watch-toggle")
        toggle.wait_for(state="visible")
        toggle.click()
        page.goto(base)
        page.locator('[data-resume="watch"]').wait_for(state="visible")
        page.locator('[data-resume="watch"]').click()
        page.wait_for_url("**/watch/")
        assert errors == []
