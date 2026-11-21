"""비교 페이지 `/compare/?c=005930,000660` — 정적 JSON 을 브라우저에서 나란히 놓는다.

회사 순서는 사용자가 고른 순서, 지표 순서는 엔진 정의 순서로 고정 —
값으로 줄 세우거나 '이긴 쪽' 을 칠하지 않는다.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
from hub_seed import seed_site_cache

import fin_checkup.site as site_pkg
from fin_checkup.disclaimer import DISCLAIMER
from fin_checkup.metrics import engine
from fin_checkup.site.build import build_site
from fin_checkup.storage import Cache

COMPARE_JS = Path(site_pkg.__file__).parent / "static" / "compare.js"
SEARCH_JS = Path(site_pkg.__file__).parent / "static" / "search.js"


@pytest.fixture
async def out(tmp_path):
    with Cache(tmp_path / "s.duckdb") as cache:
        seed_site_cache(cache)
        target = tmp_path / "out"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    return target


def compare_html(out: Path) -> str:
    return (out / "compare" / "index.html").read_text(encoding="utf-8")


async def test_compare_page_lists_every_metric_in_engine_order_with_formula_and_link(out):
    html = compare_html(out)
    assert DISCLAIMER in html
    keys = re.findall(r'<tr class="fc-compare-row" data-key="([a-z_]+)"', html)
    assert keys == [d.key for d in engine.METRIC_DEFS]
    for d in engine.METRIC_DEFS:
        assert f'href="../m/{d.key}/"' in html
        assert d.formula in html


async def test_compare_page_loads_its_script_and_a_pick_mode_search_box(out):
    html = compare_html(out)
    assert '<script src="../assets/compare.js" defer></script>' in html
    assert (out / "assets" / "compare.js").exists()
    assert re.search(r'<form class="fc-search fc-compare-add"[^>]*data-fc-pick', html)
    # 스크립트 없이도 무엇이 안 되는지 말한다.
    assert "<noscript>" in html


async def test_company_page_links_to_add_it_to_the_comparison(out):
    text = (out / "c" / "005930" / "index.html").read_text(encoding="utf-8")
    assert '<a class="fc-button" href="../../compare/?add=005930">비교에 추가</a>' in text


async def test_company_json_carries_display_texts_the_compare_table_needs(out):
    doc = json.loads((out / "api" / "c" / "005930.json").read_text(encoding="utf-8"))
    by_key = {m["key"]: m for m in doc["metrics"]}
    assert by_key["debt_ratio"]["value_text"] == "66.67%"
    # 값이 없으면 화면과 같은 '—' — 0 으로 채우지 않는다.
    assert by_key["fcf"]["value"] is None
    assert by_key["fcf"]["value_text"] == "—"


def test_compare_script_never_sorts_or_builds_html_from_strings():
    js = COMPARE_JS.read_text(encoding="utf-8")
    assert ".sort(" not in js  # 회사·지표 순서를 값으로 바꾸지 않는다
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js  # 회사명은 DB 에서 온다
    for banned in ("XMLHttpRequest", "sendBeacon", "document.cookie", "sessionStorage"):
        assert banned not in js


def node_eval(expr: str):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 가 없다")
    js = json.dumps(str(COMPARE_JS))
    script = f"const s = require({js}); process.stdout.write(JSON.stringify({expr}));"
    done = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True, timeout=30)
    return json.loads(done.stdout)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("005930,000660", ["005930", "000660"]),
        ("000660,005930", ["000660", "005930"]),  # 고른 순서 그대로
        ("005930, 005930 ,000660", ["005930", "000660"]),  # 중복은 한 번
        ("005930,../x,12345,0006600,<b>", ["005930"]),  # 종목코드 꼴이 아니면 버린다
        ("a1b2c3", ["A1B2C3"]),
        ("1,2", []),
        ("000001,000002,000003,000004,000005", ["000001", "000002", "000003", "000004"]),  # 최대 4곳
        (None, []),
    ],
)
def test_parse_codes_keeps_user_order_dedupes_and_caps(raw, expected):
    assert node_eval(f"s.parseCodes({json.dumps(raw)})") == expected


@pytest.mark.parametrize(
    ("current", "code", "expected"),
    [
        ([], "005930", ["005930"]),
        (["005930"], "000660", ["005930", "000660"]),
        (["005930", "000660"], "005930", ["005930", "000660"]),
        (["000001", "000002", "000003", "000004"], "000005", ["000001", "000002", "000003", "000004"]),
    ],
)
def test_add_code_appends_at_the_end_without_reordering(current, code, expected):
    assert node_eval(f"s.addCode({json.dumps(current)}, {json.dumps(code)})") == expected


def test_js_cap_matches_the_page():
    from fin_checkup.site.pages.compare import MAX_COMPANIES

    assert node_eval("s.MAX") == MAX_COMPANIES


def test_compare_url_lists_codes_in_order():
    assert node_eval('s.queryFor(["000660", "005930"])') == "?c=000660,005930"
    assert node_eval("s.queryFor([])") == ""


def test_search_script_still_exports_search_for_reuse():
    js = SEARCH_JS.read_text(encoding="utf-8")
    assert "data-fc-pick" in js


# ── 브라우저 스모크 ───────────────────────────────────────────────


def test_browser_compares_adds_and_removes_in_the_order_chosen(out):
    from site_browser import chromium, serve

    with serve(out) as base, chromium() as browser:
        page = browser.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base + "compare/?c=105560,005930")
        heads = page.locator("thead .fc-compare-company a")
        heads.nth(1).wait_for()
        assert heads.all_text_contents() == ["KB금융", "삼성전자"]

        # 금융지주의 부채비율은 ⊘ — 판정하지 않고 대신 볼 것을 적는다.
        kb_debt = page.locator('tr[data-key="debt_ratio"] td.fc-compare-value').nth(0)
        # 신호는 이모지가 아니라 CSS 모양 + 이름 (test_site_signal_marks).
        assert kb_debt.locator(".fc-mark.mark-not_applicable").count() == 1
        assert "해당 없음" in kb_debt.text_content()
        assert "대신 볼 것" in kb_debt.text_content()
        samsung_debt = page.locator('tr[data-key="debt_ratio"] td.fc-compare-value').nth(1)
        assert "66.67%" in samsung_debt.text_content()
        assert "경계값" in samsung_debt.text_content()
        # 지표 순서는 페이지에 고정된 그대로.
        rows = page.locator("tbody tr.fc-compare-row").evaluate_all("rs => rs.map(r => r.dataset.key)")
        assert rows == [d.key for d in engine.METRIC_DEFS]

        # 검색으로 더하면 끝에 붙고 주소가 바뀐다 (이동하지 않는다).
        box = page.locator("form.fc-compare-add input[type=search]")
        box.fill("에이치엘비")
        page.locator("form.fc-compare-add .fc-results li").first.wait_for()
        box.press("Enter")
        heads.nth(2).wait_for()
        assert heads.all_text_contents() == ["KB금융", "삼성전자", "에이치엘비"]
        assert page.url.endswith("compare/?c=105560,005930,028300")

        # 빼기
        page.locator('button.fc-compare-remove[data-code="005930"]').click()
        page.wait_for_function("document.querySelectorAll('thead .fc-compare-company').length === 2")
        assert heads.all_text_contents() == ["KB금융", "에이치엘비"]
        assert page.url.endswith("compare/?c=105560,028300")

        # 회사 페이지의 '비교에 추가' 는 지난 비교 끝에 붙인다.
        page.goto(base + "c/005930/")
        page.get_by_role("link", name="비교에 추가").click()
        heads.nth(2).wait_for()
        assert heads.all_text_contents() == ["KB금융", "에이치엘비", "삼성전자"]
        assert page.url.endswith("compare/?c=105560,028300,005930")

        # 없는 회사는 알리고 뺀다.
        page.goto(base + "compare/?c=999999,005930")
        heads.nth(0).wait_for()
        page.locator(".fc-compare-status", has_text="999999").wait_for()
        assert heads.all_text_contents() == ["삼성전자"]
        assert errors == []
