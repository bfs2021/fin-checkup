"""관심종목 "지난번 이후 바뀐 것" — 기준값과 지금의 신호·사업연도, 기준일 이후 위험 공시, "확인함"."""

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
from fin_checkup.site.build import build_site
from fin_checkup.storage import Cache

WATCH_JS = Path(site_pkg.__file__).parent / "static" / "watch.js"


def node(expr: str):
    exe = shutil.which("node")
    if exe is None:
        pytest.skip("node 가 없다")
    script = f"const w = require({json.dumps(str(WATCH_JS))}); process.stdout.write(JSON.stringify({expr}));"
    done = subprocess.run([exe, "-e", script], capture_output=True, text=True, check=True, timeout=30)
    return json.loads(done.stdout)


COMPANY = {
    "fiscal_year": 2025,
    "company": {"stock_code": "005930", "name": "삼성전자"},
    "metrics": [
        {"key": "debt_ratio", "label": "부채비율", "signal": {"key": "red"}},
        {"key": "current_ratio", "label": "유동비율", "signal": {"key": "green"}},
        {"key": "new_metric", "label": "새 지표", "signal": {"key": "yellow"}},
    ],
}
ITEM = {
    "code": "005930",
    "name": "삼성전자",
    "year": 2024,
    "saved": "2026-11-19",
    "signals": {"debt_ratio": "yellow", "current_ratio": "green"},
    "seen": [],
}


def disclosure(
    no: str, day: str, code: str = "005930", url: str = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=1"
):
    return {
        "stock_code": code,
        "corp_name": "삼성전자",
        "report_nm": f"공시 {no}",
        "rcept_dt": day,
        "rcept_no": no,
        "category_label": "불성실공시법인 지정",
        "url": url,
    }


DISCLOSURES = {
    "format_version": 1,
    "bgn_de": "20261115",
    "end_de": "20261121",
    "items": [
        disclosure("20261121000003", "20261121"),
        disclosure("20261118000001", "20261118"),  # 기준일 전
        disclosure("20261119000002", "20261119"),  # 기준일 당일 — 포함
        disclosure("20261120000009", "20261120", code="000660"),  # 다른 회사
        disclosure("20261120000010", "20261120", url="javascript:alert(1)"),
    ],
}


def changes(item=ITEM, company=COMPANY, disclosures=DISCLOSURES):
    return node(f"w.changesSince({json.dumps(item)}, {json.dumps(company)}, {json.dumps(disclosures)})")


def test_lists_new_year_signal_changes_and_disclosures_since_the_saved_day():
    got = changes()
    assert got[0] == {"kind": "year", "from": 2024, "to": 2025}
    assert got[1] == {
        "kind": "signal",
        "key": "debt_ratio",
        "label": "부채비율",
        "from": "yellow",
        "to": "red",
    }
    assert [c["kind"] for c in got[2:]] == ["disclosure"] * 3
    assert [c["rcept_no"] for c in got[2:]] == ["20261121000003", "20261120000010", "20261119000002"], (
        "최신순"
    )
    assert got[2]["date"] == "2026-11-21" and got[2]["url"].startswith("https://dart.fss.or.kr/")
    assert got[3]["url"] is None, "DART 가 아닌 주소는 링크로 만들지 않는다"


def test_unchanged_signals_and_metrics_without_a_baseline_are_not_changes():
    got = changes(disclosures=None)
    assert all(c.get("key") not in ("current_ratio", "new_metric") for c in got)


def test_nothing_to_compare_without_a_baseline():
    assert changes(item={**ITEM, "signals": None, "saved": None}) == []


def test_same_year_and_same_signals_is_no_change():
    company = {**COMPANY, "fiscal_year": 2024, "metrics": COMPANY["metrics"][1:2]}
    assert changes(company=company, disclosures=None) == []


def test_acknowledge_moves_the_baseline_and_remembers_todays_disclosures():
    snap = node(
        f"w.acknowledge({json.dumps(ITEM)}, {json.dumps(COMPANY)}, {json.dumps(DISCLOSURES)}, '2026-11-21')"
    )
    assert snap["year"] == 2025 and snap["saved"] == "2026-11-21"
    assert snap["signals"] == {"debt_ratio": "red", "current_ratio": "green", "new_metric": "yellow"}
    assert snap["seen"] == ["20261121000003"]
    assert changes(item=snap) == [], "확인한 뒤엔 같은 날 공시도 다시 뜨지 않는다"
    later = {**DISCLOSURES, "items": [*DISCLOSURES["items"], disclosure("20261121000099", "20261121")]}
    assert [c["rcept_no"] for c in changes(item=snap, disclosures=later)] == ["20261121000099"]


def test_wording_is_neutral():
    """화면에 나가는 문장(한글이 든 문자열)에 느낌표·재촉·매매 단어가 없다."""
    js = WATCH_JS.read_text(encoding="utf-8")
    shown = [t for t in re.findall(r'"([^"\\]*)"', js) if re.search(r"[가-힣]", t)]
    assert len(shown) > 10
    assert not [t for t in shown if "!" in t]
    for word in ("서두르", "놓치", "지금 바로", "급등", "급락", "매도", "매수"):
        assert word not in js


# ── 브라우저 스모크 ───────────────────────────────────────────────


@pytest.fixture
async def out(tmp_path):
    with Cache(tmp_path / "c.duckdb") as cache:
        seed_site_cache(cache)
        target = tmp_path / "out"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    (target / "data").mkdir()
    payload = {**DISCLOSURES, "items": [disclosure("20261120000001", "20261120")]}
    (target / "data" / "disclosures.json").write_text(json.dumps(payload, ensure_ascii=False))
    return target


def test_browser_shows_changes_then_acknowledge_clears_them(out):
    from site_browser import chromium, serve

    company = json.loads((out / "api" / "c" / "005930.json").read_text(encoding="utf-8"))
    signals = {m["key"]: m["signal"]["key"] for m in company["metrics"]}
    first = company["metrics"][0]
    before = "green" if first["signal"]["key"] != "green" else "red"
    stored = {
        "v": 1,
        "items": [
            {
                "code": "005930",
                "name": "삼성전자",
                "year": 2023,
                "saved": "2026-11-19",
                "signals": {**signals, first["key"]: before},
            }
        ],
    }

    with serve(out) as base, chromium() as browser:
        page = browser.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base + "watch/")
        page.evaluate(f"localStorage.setItem('fin-checkup:watch', {json.dumps(json.dumps(stored))})")
        page.reload()

        box = page.locator('.fc-watch-item[data-code="005930"] .fc-watch-changes')
        box.locator(".fc-watch-change").first.wait_for()
        lines = box.locator(".fc-watch-change").all_text_contents()
        assert lines[0].startswith("새 사업연도 숫자: 2023 → 2024 사업연도")
        assert lines[1].startswith(f"{first['label']}: ")
        assert box.locator(f'a[href$="c/005930/#m-{first["key"]}"]').count() == 1
        assert "위험 공시 2026-11-20" in lines[2]
        assert box.locator('a[href^="https://dart.fss.or.kr/"]').count() == 1
        assert "지난번 확인(2026-11-19) 이후" in box.text_content()

        page.click('.fc-watch-item[data-code="005930"] .fc-watch-ack')
        page.locator('.fc-watch-item[data-code="005930"]', has_text="바뀐 것은 없습니다.").wait_for()
        saved = json.loads(page.evaluate("localStorage.getItem('fin-checkup:watch')"))["items"][0]
        assert saved["year"] == 2024 and saved["signals"] == signals

        page.reload()
        page.locator('.fc-watch-item[data-code="005930"]', has_text="바뀐 것은 없습니다.").wait_for()
        assert errors == []
