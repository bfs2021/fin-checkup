"""사이트 가드 — 픽스처로 빌드한 사이트가 통과하고, 선을 넘은 산출물은 걸린다.

같은 `check_site` 를 Pages 워크플로가 실제 빌드에 돌린다(`cli site check`).
"""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

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


def page(
    body: str = "", head: str = CSP, disclaimer: str = DISCLAIMER, lang: str = "ko", skip: bool = True
) -> bytes:
    """가드를 통과하는 최소 페이지 — 규칙 하나씩 어긋나게 만들어 본다."""
    skip_link = '<a href="#main">본문으로</a>' if skip else ""
    return (
        f'<!doctype html><html lang="{lang}"><head>{head}</head><body>{skip_link}'
        '<header><a href="./">fin-checkup</a>'
        '<nav aria-label="사이트"><a href="./learn/">읽는 법</a></nav></header>'
        f'<main id="main">{body}</main><footer><p>{disclaimer}</p></footer></body></html>'
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


SIGN = {"red": "🔴 위험", "yellow": "🟡 주의", "green": "🟢 정상", "neutral": "⚪ 측정값"}


def card(signal: str, basis: str, ident: str = "m-a") -> str:
    """회사 페이지 지표 카드 꼴 — 신호 기호·글자 + 계산식·경계값 목록."""
    return (
        f'<li class="fc-metric sig-{signal}" id="{ident}"><span class="fc-sig">{SIGN[signal]}</span>'
        f"<dl>{basis}</dl></li>"
    )


def test_judged_metric_needs_formula_and_thresholds():
    ok = card("red", "<dt>계산식</dt><dd>부채 ÷ 자본</dd><dt>경계값</dt><dd>정상 100% 이하</dd>")
    assert rules("x.html", page(ok)) == []
    no_band = card("yellow", "<dt>계산식</dt><dd>a ÷ b</dd>")
    assert rules("x.html", page(no_band)) == ["basis"]
    empty_formula = card("green", "<dt>계산식</dt><dd> </dd><dt>경계값</dt><dd>x</dd>")
    assert rules("x.html", page(empty_formula)) == ["basis"]


def test_unjudged_metric_needs_formula_only():
    assert rules("x.html", page(card("neutral", "<dt>계산식</dt><dd>매출 ÷ 자산</dd>"))) == []
    distribution = '<li class="fc-metric"><dl><dt>중앙값</dt><dd>3%</dd></dl></li>'
    assert rules("x.html", page(distribution)) == ["basis"]


def test_sector_label_on_threshold_term_still_counts():
    sector_card = card("red", "<dt>계산식</dt><dd>a</dd><dt>경계값 (금융업)</dt><dd>b</dd>")
    assert rules("x.html", page(sector_card)) == []


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


def test_page_language_skip_link_and_landmarks():
    assert rules("x.html", page(lang="en")) == ["a11y"]
    assert rules("x.html", page(skip=False)) == ["a11y"]
    no_nav = page().replace(b'<nav aria-label="\xec\x82\xac\xec\x9d\xb4\xed\x8a\xb8">', b"<div>")
    no_nav = no_nav.replace(b"</nav>", b"</div>")
    assert rules("x.html", no_nav) == ["a11y"]
    two_mains = page('<main id="other">x</main>')
    assert rules("x.html", two_mains) == ["a11y"]
    # 본문 안 article 의 header·footer 는 페이지 머리·꼬리가 아니다.
    only_inner = (
        page().replace(b"<header>", b"<article><header>").replace(b"</header>", b"</header></article>")
    )
    assert rules("x.html", only_inner) == ["a11y"]


def test_signals_are_never_color_only():
    ok = '<ul><li class="fc-chip sig-red"><span aria-hidden="true">🔴</span> 위험 <b>2</b></li></ul>'
    assert rules("x.html", page(ok)) == []
    symbol_only = '<ul><li class="sig-red"><span aria-hidden="true">🔴</span> <b>자본잠식</b></li></ul>'
    assert rules("x.html", page(symbol_only)) == [], "기호가 있으면 색만은 아니다"
    color_only = '<ul><li class="fc-chip sig-yellow"><b>3</b></li></ul>'
    assert rules("x.html", page(color_only)) == ["a11y"]


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


def test_cli_site_check_fails_when_too_few_company_pages(out, capsys):
    # 데이터에 없는 사업연도로 빌드하면 회사 몇 곳짜리 사이트가 다른 가드를 다 통과한 채 나갔다.
    assert main(["site", "check", str(out), "--min-companies", "100000"]) == 1
    assert "[coverage]" in capsys.readouterr().out


def test_cli_site_check_coverage_passes_at_or_below_page_count(out):
    pages = len(list((out / "c").glob("*/index.html")))
    assert pages > 0
    assert main(["site", "check", str(out), "--min-companies", str(pages)]) == 0


def test_pages_workflow_guards_coverage():
    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pages.yml"
    assert "site check site-out --min-companies" in workflow.read_text(encoding="utf-8")
