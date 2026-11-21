"""링크 공유 버튼 — navigator.share → 클립보드 → 주소 칸. 쿼리·해시(추적 파라미터)는 떼고 공유한다."""

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

SHARE_JS = Path(site_pkg.__file__).parent / "static" / "share.js"


@pytest.fixture
async def out(tmp_path):
    with Cache(tmp_path / "s.duckdb") as cache:
        seed_site_cache(cache)
        target = tmp_path / "out"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    return target


async def test_company_page_has_a_share_button_hidden_until_the_script_runs(out):
    text = (out / "c" / "005930" / "index.html").read_text(encoding="utf-8")
    assert re.search(r'<button type="button" class="[^"]*fc-share-button[^"]*" hidden>', text)
    assert 'role="status"' in text
    assert '<script src="../../assets/share.js" defer></script>' in text
    assert (out / "assets" / "share.js").exists()


async def test_no_inline_handlers_or_inline_scripts(out):
    """CSP script-src 'self' — 인라인 스크립트·on* 핸들러는 막힌다."""
    for path in out.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\son[a-z]+=", text), path
        for tag in re.findall(r"<script\b[^>]*>", text):
            assert "src=" in tag, f"{path}: 인라인 스크립트 {tag}"


def test_share_script_sends_nothing_and_adds_no_parameters():
    js = SHARE_JS.read_text(encoding="utf-8")
    for banned in ("fetch(", "XMLHttpRequest", "sendBeacon", "utm_", "localStorage", "document.cookie"):
        assert banned not in js.replace("utm_*", ""), banned


def node_eval(expr: str):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 가 없다")
    script = f"const s = require({json.dumps(str(SHARE_JS))}); process.stdout.write(JSON.stringify({expr}));"
    done = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True, timeout=30)
    return json.loads(done.stdout)


@pytest.mark.parametrize(
    ("canonical", "location", "expected"),
    [
        (
            "https://x.io/fc/c/005930/",
            "https://x.io/fc/c/005930/?utm_source=a#m",
            "https://x.io/fc/c/005930/",
        ),
        (None, "http://localhost:8000/c/005930/?q=1#metrics", "http://localhost:8000/c/005930/"),
        ("", "http://localhost:8000/c/005930/#x", "http://localhost:8000/c/005930/"),
        (None, "https://x.io/c/005930/", "https://x.io/c/005930/"),
    ],
)
def test_share_url_strips_query_and_hash(canonical, location, expected):
    assert node_eval(f"s.shareUrl({json.dumps(canonical)}, {json.dumps(location)})") == expected


# ── 브라우저 스모크 ───────────────────────────────────────────────


def test_browser_copies_a_clean_link(out):
    from site_browser import chromium, serve

    with serve(out) as base, chromium() as browser:
        context = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base + "c/005930/?utm_source=x#metrics")
        button = page.locator(".fc-share-button")
        button.wait_for(state="visible")
        assert button.text_content() == "링크 복사"  # headless Chromium 에는 navigator.share 가 없다
        button.click()
        page.locator(".fc-share-status", has_text="링크를 복사했습니다.").wait_for()
        assert page.evaluate("navigator.clipboard.readText()") == base + "c/005930/"
        assert errors == []
