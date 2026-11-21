"""사이트 가드 — 픽스처로 빌드한 사이트가 통과하고, 선을 넘은 산출물은 걸린다.

같은 `check_site` 를 Pages 워크플로가 실제 빌드에 돌린다(`cli site check`).
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from hub_seed import seed_site_cache

from fin_checkup.cli import main
from fin_checkup.disclaimer import DISCLAIMER
from fin_checkup.site.build import build_site
from fin_checkup.site.guard import check_file, check_site
from fin_checkup.storage import Cache

CSP = (
    "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'self'; script-src 'self'; "
    "style-src 'self'; img-src 'self' data:\">"
)


def csp(content: str) -> str:
    return f'<meta http-equiv="Content-Security-Policy" content="{content}">'


@pytest.fixture
def out(tmp_path):
    # 동기 픽스처 — CLI(main)가 asyncio.run 을 부르므로 테스트가 이벤트 루프 안에 있으면 안 된다.
    with Cache(tmp_path / "site.duckdb") as cache:
        seed_site_cache(cache)
        target = tmp_path / "out"
        asyncio.run(build_site(cache, target, 2024, built_on=date(2026, 11, 21)))
    return target


def page(body: str = "", head: str = CSP, disclaimer: str = DISCLAIMER) -> bytes:
    return (
        f'<!doctype html><html lang="ko"><head>{head}</head>'
        f"<body><main>{body}</main><footer><p>{disclaimer}</p></footer></body></html>"
    ).encode()


def rules(path: str, data: bytes) -> list[str]:
    return [v.rule for v in check_file(path, data)]


# ── 실제 빌드 ─────────────────────────────────────────────────────


def test_fixture_build_passes_every_guard(out):
    assert check_site(out) == []


def test_build_with_an_absolute_base_url_passes_every_guard(tmp_path):
    """Pages 는 `--base-url https://…` 로 빌드한다 — canonical·og:url 이 절대주소가 된다.

    canonical 을 '다른 사이트 자원' 으로 읽으면 실제 배포 빌드의 거의 모든 페이지가 걸린다.
    """
    with Cache(tmp_path / "site.duckdb") as cache:
        seed_site_cache(cache)
        target = tmp_path / "abs"
        base = "https://younghwan91.github.io/fin-checkup/"
        asyncio.run(build_site(cache, target, 2024, base_url=base, built_on=date(2026, 11, 21)))
    assert check_site(target) == []


def test_guard_sees_every_company_metric(out):
    """가드가 지표 카드를 실제로 읽는지 — 경계값을 지우면 걸려야 한다."""
    path = out / "c" / "005930" / "index.html"
    text = path.read_text(encoding="utf-8")
    assert "<dt>경계값</dt>" in text
    path.write_text(text.replace("<dt>경계값</dt>", "<dt>비고</dt>"), encoding="utf-8")
    found = [v for v in check_site(out) if v.rule == "basis"]
    assert found and all(v.path == "c/005930/index.html" for v in found)


def test_empty_or_missing_output_does_not_pass(tmp_path):
    assert [v.rule for v in check_site(tmp_path / "nope")] == ["site"]
    (tmp_path / "empty").mkdir()
    assert [v.rule for v in check_site(tmp_path / "empty")] == ["site"]


# ── 규칙마다 ───────────────────────────────────────────────────────


def test_clean_page_passes():
    assert rules("x.html", page("<p>안녕</p>")) == []


def test_disclaimer_is_required_verbatim():
    assert rules("x.html", page(disclaimer="투자권유 아님")) == ["disclaimer"]


def test_judged_metric_needs_formula_and_thresholds():
    ok = (
        '<li class="fc-metric sig-red" id="m-a"><dl><dt>계산식</dt><dd>부채 ÷ 자본</dd>'
        "<dt>경계값</dt><dd>정상 100% 이하</dd></dl></li>"
    )
    assert rules("x.html", page(ok)) == []
    no_band = '<li class="fc-metric sig-yellow" id="m-b"><dl><dt>계산식</dt><dd>a ÷ b</dd></dl></li>'
    assert rules("x.html", page(no_band)) == ["basis"]
    empty_formula = (
        '<li class="fc-metric sig-green"><dl><dt>계산식</dt><dd> </dd><dt>경계값</dt><dd>x</dd></dl></li>'
    )
    assert rules("x.html", page(empty_formula)) == ["basis"]


def test_unjudged_metric_needs_formula_only():
    neutral = '<li class="fc-metric sig-neutral"><dl><dt>계산식</dt><dd>매출 ÷ 자산</dd></dl></li>'
    assert rules("x.html", page(neutral)) == []
    card = '<li class="fc-metric"><dl><dt>중앙값</dt><dd>3%</dd></dl></li>'
    assert rules("x.html", page(card)) == ["basis"]


def test_sector_label_on_threshold_term_still_counts():
    card = (
        '<li class="fc-metric sig-red"><dl><dt>계산식</dt><dd>a</dd>'
        "<dt>경계값 (금융업)</dt><dd>b</dd></dl></li>"
    )
    assert rules("x.html", page(card)) == []


@pytest.mark.parametrize(
    "head",
    [
        "",
        CSP + CSP,
        csp("default-src *"),
        csp("default-src 'self'; script-src 'self' 'unsafe-eval'"),
        csp("default-src 'self'; script-src 'self' 'unsafe-inline'"),
        csp("default-src 'self'; script-src https://cdn.example"),
        csp("default-src 'self'; style-src 'self' 'unsafe-inline'"),
    ],
    ids=["missing", "twice", "wildcard", "unsafe-eval", "inline-script", "cdn", "unneeded-inline-style"],
)
def test_csp_must_be_strict(head):
    assert "csp" in rules("x.html", page(head=head))


def test_inline_style_needs_csp_permission():
    assert rules("x.html", page('<p style="color:red">x</p>')) == ["csp"]
    allow = csp("default-src 'self'; style-src 'self' 'unsafe-inline'")
    assert rules("x.html", page('<p style="color:red">x</p>', head=allow)) == []


@pytest.mark.parametrize(
    "body",
    [
        '<script src="https://cdn.example/x.js"></script>',
        '<script src="//cdn.example/x.js"></script>',
        '<link rel="stylesheet" href="https://fonts.example/css">',
        '<img src="http://tracker.example/p.gif" alt="">',
        "<script>alert(1)</script>",
    ],
)
def test_no_offsite_or_inline_scripts(body):
    assert rules("x.html", page(body)) == ["script"]


@pytest.mark.parametrize(
    "head",
    [
        '<link rel="canonical" href="https://example.github.io/fin-checkup/c/005930/">',
        '<link rel="alternate" type="application/atom+xml" href="https://example.github.io/feed.xml">',
    ],
)
def test_navigation_links_are_not_resource_loads(head):
    assert rules("x.html", page(head=CSP + head)) == []


@pytest.mark.parametrize(
    "head",
    [
        '<link rel="icon" href="https://cdn.example/favicon.ico">',
        '<link rel="alternate stylesheet" href="https://cdn.example/x.css">',
        '<link rel="preload" as="font" href="https://cdn.example/f.woff2">',
        '<link href="https://cdn.example/x.css">',
    ],
)
def test_resource_links_to_other_sites_are_still_blocked(head):
    assert rules("x.html", page(head=CSP + head)) == ["script"]


def test_local_and_data_scripts_are_fine():
    body = (
        '<script src="../../assets/search.js" defer></script>'
        '<script type="application/ld+json">{"@type": "Organization"}</script>'
        '<img src="data:image/png;base64,AAAA" alt="">'
        '<a href="https://dart.fss.or.kr/">DART 원문</a>'
    )
    assert rules("x.html", page(body)) == []


def test_no_inline_event_handlers_or_javascript_urls():
    assert rules("x.html", page('<button onclick="go()">x</button>')) == ["handler"]
    assert rules("x.html", page('<a href="javascript:void(0)">x</a>')) == ["handler"]


@pytest.mark.parametrize(
    "js",
    [
        "document.cookie = 'a=1';",
        "sessionStorage.setItem('fin-checkup:x', 1);",
        "indexedDB.open('x');",
        "localStorage.setItem('watch', '[]');",
        "localStorage.clear();",
        "localStorage['fin-checkup:x'] = 1;",
    ],
)
def test_storage_is_limited_to_the_namespaced_local_storage(js):
    assert rules("assets/app.js", js.encode()) == ["storage"]


def test_namespaced_local_storage_is_allowed():
    js = 'localStorage.getItem("fin-checkup:watch"); localStorage.setItem(`fin-checkup:seen`, "1");'
    assert rules("assets/app.js", js.encode()) == []


@pytest.mark.parametrize("path", ["c/1/index.html", "api/c/1.json", "assets/x.js", "favicon.ico"])
def test_no_dart_key_like_strings_anywhere(path):
    key = "0123456789abcdef0123456789abcdef01234567"
    data = page(f"<p>{key}</p>") if path.endswith(".html") else key.encode()
    assert rules(path, data) == ["secret"]
    assert rules("api/x.json", b'{"u": "https://opendart.fss.or.kr/api/x.json?crtfc_key=abc"}') == ["secret"]


def test_longer_hex_runs_are_not_keys():
    """SHA-256(64자리)은 인증키 꼴이 아니다 — 40자리 경계로만 본다."""
    assert rules("x.json", ("a" * 64).encode()) == []


# ── CLI ────────────────────────────────────────────────────────────


def test_cli_site_check_exits_zero_on_a_clean_build(out, capsys):
    assert main(["site", "check", str(out)]) == 0
    assert "위반 없음" in capsys.readouterr().out


def test_cli_site_check_fails_and_lists_violations(out, capsys):
    (out / "c" / "005930" / "index.html").write_text("<html></html>", encoding="utf-8")
    assert main(["site", "check", str(out)]) == 1
    printed = capsys.readouterr().out
    assert "c/005930/index.html: [disclaimer]" in printed
    assert "c/005930/index.html: [csp]" in printed
