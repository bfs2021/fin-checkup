"""링크 검사 — 픽스처 빌드는 깨진 내부 링크가 없고, 일부러 깨뜨린 링크는 잡힌다. 외부 링크는 보고만."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import pytest
from hub_seed import seed_site_cache

from fin_checkup.cli import main
from fin_checkup.site.build import build_site
from fin_checkup.site.links import check_links
from fin_checkup.storage import Cache

BASE = "https://younghwan91.github.io/fin-checkup/"


def _build(tmp_path: Path, base_url: str) -> Path:
    # 동기 — CLI(main)가 asyncio.run 을 부르므로 테스트가 이벤트 루프 안에 있으면 안 된다.
    with Cache(tmp_path / "site.duckdb") as cache:
        seed_site_cache(cache)
        out = tmp_path / "out"
        asyncio.run(build_site(cache, out, 2024, base_url=base_url, built_on=date(2026, 11, 21)))
    return out


@pytest.fixture
def out(tmp_path):
    return _build(tmp_path, BASE)


def write(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"<!doctype html><html><body>{body}</body></html>", encoding="utf-8")


def broken(root: Path, base_url: str = "/") -> list[tuple[str, str]]:
    return [(b.source, b.url) for b in check_links(root, base_url).broken]


# ── 실제 빌드 ─────────────────────────────────────────────────────


@pytest.mark.parametrize("base_url", ["/", BASE])
def test_fixture_build_has_no_broken_internal_links(tmp_path, base_url):
    report = check_links(_build(tmp_path, base_url), base_url)
    assert report.broken == []
    assert report.pages > 5 and report.internal > 100


def test_a_deliberately_broken_link_in_a_build_is_caught(out):
    page = out / "c" / "005930" / "index.html"
    text = page.read_text(encoding="utf-8")
    page.write_text(text.replace("</main>", '<a href="../999999/">없는 회사</a></main>', 1), encoding="utf-8")
    assert broken(out, BASE) == [("c/005930/index.html", "../999999/")]


def test_canonical_under_the_base_url_is_checked_like_a_link(out):
    page = out / "c" / "005930" / "index.html"
    text = page.read_text(encoding="utf-8")
    canonical = f'<link rel="canonical" href="{BASE}c/005930/">'
    wrong = text.replace(canonical, f'<link rel="canonical" href="{BASE}c/5930/">')
    assert wrong != text
    page.write_text(wrong, encoding="utf-8")
    assert ("c/005930/index.html", f"{BASE}c/5930/") in broken(out, BASE)


# ── 규칙 ─────────────────────────────────────────────────────────


def test_relative_links_resolve_to_files_and_directory_indexes(tmp_path):
    write(
        tmp_path,
        "index.html",
        '<a href="c/005930/">회사</a><a href="assets/site.css">css</a><a href="m/">m</a>',
    )
    write(tmp_path, "c/005930/index.html", '<a href="../../">홈</a><a href="../../index.html">홈</a>')
    write(tmp_path, "m/index.html", "")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "site.css").write_text("")
    assert broken(tmp_path) == []


def test_missing_file_and_escaping_the_site_are_broken(tmp_path):
    body = '<a href="nope/">x</a><img src="img/a.svg" alt=""><a href="../../etc/">x</a>'
    write(tmp_path, "index.html", body)
    assert broken(tmp_path) == [
        ("index.html", "nope/"),
        ("index.html", "img/a.svg"),
        ("index.html", "../../etc/"),
    ]


def test_fragments_must_exist_on_the_target_page(tmp_path):
    body = '<a href="#top">ok</a><a href="#gone">x</a><a href="g/#term">ok</a><a href="g/#no">x</a>'
    write(tmp_path, "index.html", body)
    write(tmp_path, "g/index.html", '<h2 id="term">용어</h2><span id="top"></span>')
    (tmp_path / "index.html").write_text(
        (tmp_path / "index.html").read_text().replace("<body>", '<body><a name="top"></a>'), encoding="utf-8"
    )
    assert broken(tmp_path) == [("index.html", "#gone"), ("index.html", "g/#no")]


def test_query_strings_are_ignored_when_resolving(tmp_path):
    write(tmp_path, "index.html", '<a href="watch/?codes=005930">관심</a>')
    write(tmp_path, "watch/index.html", "")
    assert broken(tmp_path) == []


def test_root_relative_links_must_stay_under_the_project_path(tmp_path):
    write(tmp_path, "index.html", '<a href="/fin-checkup/m/">ok</a><a href="/m/">x</a>')
    write(tmp_path, "m/index.html", "")
    assert broken(tmp_path, BASE) == [("index.html", "/m/")]


def test_external_links_are_reported_not_failed(tmp_path):
    write(
        tmp_path,
        "index.html",
        '<a href="https://dart.fss.or.kr/x">DART</a><a href="https://dart.fss.or.kr/x">again</a>'
        '<a href="mailto:a@example.com">mail</a><img src="data:image/png;base64,AA" alt="">',
    )
    write(tmp_path, "b/index.html", '<a href="https://dart.fss.or.kr/x">DART</a>')
    report = check_links(tmp_path, BASE)
    assert report.ok
    assert report.external == {"https://dart.fss.or.kr/x": 2}


def test_absolute_links_to_another_path_on_the_same_host_are_external(tmp_path):
    write(tmp_path, "index.html", '<a href="https://younghwan91.github.io/other-repo/">x</a>')
    report = check_links(tmp_path, BASE)
    assert report.ok and list(report.external) == ["https://younghwan91.github.io/other-repo/"]


# ── CLI ──────────────────────────────────────────────────────────


def test_cli_site_links_passes_a_clean_build(out, capsys):
    assert main(["site", "links", str(out), "--base-url", BASE]) == 0
    assert "깨진 내부 링크 없음" in capsys.readouterr().out


def test_cli_site_links_fails_and_lists_broken_links(tmp_path, capsys):
    write(tmp_path, "index.html", '<a href="nope/">x</a><a href="https://example.com/">ext</a>')
    assert main(["site", "links", str(tmp_path)]) == 1
    text = capsys.readouterr().out
    assert "index.html: nope/" in text
    assert "https://example.com/" in text  # 외부 링크는 목록으로 보고


def test_cli_site_links_rejects_a_missing_folder(tmp_path, capsys):
    assert main(["site", "links", str(tmp_path / "none")]) == 1
