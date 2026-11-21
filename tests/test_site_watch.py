"""관심종목 — 회사 페이지 토글(localStorage 기준값) · /watch/ 틀 · 내보내기/가져오기 · 브라우저 스모크."""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
from hub_seed import seed_site_cache

import fin_checkup.site as site_pkg
from fin_checkup.site.build import build_site
from fin_checkup.storage import Cache

WATCH_JS = Path(site_pkg.__file__).parent / "static" / "watch.js"


@pytest.fixture
async def out(tmp_path):
    with Cache(tmp_path / "w.duckdb") as cache:
        seed_site_cache(cache)
        target = tmp_path / "out"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    return target


def read(out, path: str) -> str:
    return (out / path).read_text(encoding="utf-8")


def toggle_entry(text: str) -> dict:
    m = re.search(r"data-watch='([^']*)'", text)
    assert m, "관심종목 버튼이 없다"
    return json.loads(html.unescape(m.group(1)))


async def test_company_page_toggle_carries_the_snapshot_to_save(out):
    text = read(out, "c/005930/index.html")
    entry = toggle_entry(text)
    assert entry["code"] == "005930" and entry["name"] == "삼성전자" and entry["year"] == 2024
    assert len(entry["signals"]) == 17
    assert entry["signals"]["fcf"] == "unknown", "없는 값은 ⚫ 그대로 — 0 이 아니다"
    assert set(entry["signals"].values()) <= {
        "green",
        "yellow",
        "red",
        "neutral",
        "not_applicable",
        "unknown",
    }
    assert re.search(r'class="[^"]*fc-watch-toggle[^"]*"[^>]*hidden>', text), "스크립트 없이는 숨김"
    assert '<script src="../../assets/watch.js" defer></script>' in text


async def test_toggle_attribute_is_safe_with_quotes_in_the_name(tmp_path):
    from fin_checkup.models import CorpCode

    with Cache(tmp_path / "q.duckdb") as cache:
        seed_site_cache(cache)
        cache.save_corp_codes(
            [CorpCode(corp_code="00126380", corp_name="삼성'전자\"<b>", stock_code="005930")]
        )
        target = tmp_path / "q"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    entry = toggle_entry((target / "c" / "005930" / "index.html").read_text(encoding="utf-8"))
    assert entry["name"] == "삼성'전자\"<b>"


async def test_watch_page_is_a_noindex_shell_without_personal_data(out):
    text = read(out, "watch/index.html")
    assert '<meta name="robots" content="noindex">' in text
    assert 'id="fc-watch-app"' in text and '<script src="../assets/watch.js" defer></script>' in text
    assert "이 브라우저" in text and "서버로 보내지 않습니다" in text
    assert "watch/" not in read(out, "sitemap.xml")


async def test_every_page_links_to_the_watchlist_without_a_count(out):
    for path in ("index.html", "c/005930/index.html", "learn/index.html"):
        text = read(out, path)
        m = re.search(r'<nav class="fc-nav"[^>]*>(.*?)</nav>', text, re.S)
        assert m and ">관심종목</a>" in m.group(1), path
        assert not re.search(r"\d", re.sub(r"<[^>]+>", "", m.group(1))), "숫자 배지 없음"


def test_watch_script_stays_in_the_browser():
    js = WATCH_JS.read_text(encoding="utf-8")
    assert '"fin-checkup:watch"' in js
    for banned in ("document.cookie", "sendBeacon", "XMLHttpRequest", "http://", "https://", "streak"):
        assert banned not in js, banned
    # fetch 는 같은 사이트의 정적 JSON 만.
    assert re.findall(r"fetch\(([^)]*)\)", js) == ['root + "api/c/" + code + ".json"']


# ── 순수 로직 (node) ──────────────────────────────────────────────


def node(expr: str):
    exe = shutil.which("node")
    if exe is None:
        pytest.skip("node 가 없다")
    script = f"const w = require({json.dumps(str(WATCH_JS))}); process.stdout.write(JSON.stringify({expr}));"
    done = subprocess.run([exe, "-e", script], capture_output=True, text=True, check=True, timeout=30)
    return json.loads(done.stdout)


SAM = {
    "code": "005930",
    "name": "삼성전자",
    "year": 2024,
    "saved": "2026-11-21",
    "signals": {"debt_ratio": "yellow"},
}
KB = {"code": "105560", "name": "KB금융", "year": 2024, "saved": "2026-11-20", "signals": {}}


def test_add_remove_and_round_trip():
    state = node(
        f"(() => {{ let s = w.parse(''); s = w.add(s, {json.dumps(SAM)}); s = w.add(s, {json.dumps(KB)});"
        f" s = w.add(s, {json.dumps(SAM)}); return w.parse(w.serialize(s)); }})()"
    )
    assert [i["code"] for i in state["items"]] == ["105560", "005930"], "다시 담으면 하나만 (최신 기준)"
    assert state["items"][1] == SAM
    assert node(f"w.remove(w.add(w.parse(''), {json.dumps(SAM)}), '005930').items") == []


@pytest.mark.parametrize(
    "raw",
    ["", "not json", "null", '{"items": "x"}', '{"items": [1, null, {"code": "../x"}, {"code": "12"}]}'],
)
def test_parse_survives_broken_storage(raw):
    assert node(f"w.parse({json.dumps(raw)})") == {"v": 1, "items": []}


def test_list_is_by_name_not_by_signal():
    items = [SAM, KB, {**KB, "code": "028300", "name": "에이치엘비"}]
    assert [i["code"] for i in node(f"w.byName({json.dumps(items)})")] == ["105560", "005930", "028300"]


def test_export_and_import_codes():
    text = node(f"w.exportText(w.add(w.add(w.parse(''), {json.dumps(SAM)}), {json.dumps(KB)}))")
    assert text == "105560 KB금융\n005930 삼성전자"
    assert node(f"w.parseCodes({json.dumps(text)})") == ["105560", "005930"]
    assert node("w.parseCodes('005930, 000660;005930\\n abc 12345 0126z0')") == ["005930", "000660", "0126Z0"]
    imported = node(f"w.importCodes(w.add(w.parse(''), {json.dumps(SAM)}), ['005930', '000660']).items")
    assert imported[0] == SAM, "이미 담긴 회사의 기준은 덮지 않는다"
    assert imported[1] == {"code": "000660", "name": "000660", "year": None, "saved": None, "signals": None}


def test_kst_today_is_not_utc():
    # 2026-11-20T16:00Z = 2026-11-21 01:00 KST
    assert node("w.kstToday(new Date(Date.UTC(2026, 10, 20, 16, 0)))") == "2026-11-21"


async def test_snapshot_of_the_company_json_matches_the_page_toggle(out):
    company = json.loads(read(out, "api/c/005930.json"))
    snap = node(f"w.snapshotOf({json.dumps(company)}, '2026-11-21')")
    entry = toggle_entry(read(out, "c/005930/index.html"))
    assert snap == {**entry, "saved": "2026-11-21"}


# ── 브라우저 스모크 ───────────────────────────────────────────────


def test_browser_add_on_company_page_then_watch_page_shows_it(out):
    from site_browser import chromium, serve

    with serve(out) as base, chromium() as browser:
        page = browser.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(base + "c/005930/")
        toggle = page.locator(".fc-watch-toggle")
        toggle.wait_for(state="visible")
        assert toggle.get_attribute("aria-pressed") == "false"
        toggle.click()
        assert toggle.get_attribute("aria-pressed") == "true"
        page.locator(".fc-watch-status", has_text="이 브라우저에만 저장됩니다").wait_for()
        saved = json.loads(page.evaluate("localStorage.getItem('fin-checkup:watch')"))
        assert saved["items"][0]["code"] == "005930" and saved["items"][0]["signals"]["fcf"] == "unknown"

        page.goto(base + "watch/")
        item = page.locator('.fc-watch-item[data-code="005930"]')
        item.wait_for()
        assert "삼성전자" in item.text_content() and "2024년 사업보고서 기준" in item.text_content()
        assert item.locator("a").get_attribute("href").endswith("c/005930/")

        # 가져오기 → 이름순 목록, 기준이 없던 항목은 지금 상태로 채워진다.
        page.fill(".fc-watch-import", "105560\n999999")
        page.click(".fc-watch-import-button")
        page.locator('.fc-watch-item[data-code="105560"]').wait_for()
        page.locator('.fc-watch-item[data-code="999999"]', has_text="이번 빌드에는").wait_for()
        names = page.locator(".fc-watch-head a").all_text_contents()
        assert names == ["999999", "KB금융", "삼성전자"], "이름(없으면 코드) 코드포인트 순"
        assert "105560 KB금융" in page.input_value(".fc-watch-export")

        page.click('.fc-watch-item[data-code="005930"] .fc-watch-remove')
        page.goto(base + "c/005930/")
        page.locator(".fc-watch-toggle").wait_for(state="visible")
        assert page.locator(".fc-watch-toggle").get_attribute("aria-pressed") == "false"
        assert errors == []


def test_js_signal_table_matches_the_engine():
    from fin_checkup.metrics.signals import Signal

    table = node("w.SIGNALS")
    assert table == {s.value: {"emoji": s.emoji, "label": s.label} for s in Signal}


async def test_js_chip_counts_match_the_company_page(out):
    """watch.js 의 칩 순서·개수는 presentation.summary_chips 와 같다 (회사 페이지와 비교)."""
    for code in ("005930", "105560"):
        company = json.loads(read(out, f"api/c/{code}.json"))
        page_chips = re.findall(
            r'<li class="fc-chip sig-([a-z_]+)">.*?<b>(\d+)</b></li>', read(out, f"c/{code}/index.html")
        )
        assert node(f"w.chipCounts({json.dumps(company)})") == [[k, int(n)] for k, n in page_chips]
