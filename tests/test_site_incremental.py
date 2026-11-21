"""증분 빌드(`--incremental`)와 병렬 계산(`--jobs`) — 결과는 보통 빌드와 바이트 단위로 같아야 한다."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
from hub_seed import SAMSUNG, seed_site_cache, statements

from fin_checkup.cli import main
from fin_checkup.clock import KST
from fin_checkup.config import settings
from fin_checkup.site import build as build_module
from fin_checkup.site import incremental
from fin_checkup.site.build import MARKER, build_site
from fin_checkup.site.buildinfo import BUILD_JSON
from fin_checkup.site.images.fonts import resolve_fonts
from fin_checkup.site.incremental import BuildCache, data_fingerprint
from fin_checkup.storage import Cache

WHEN = datetime(2026, 11, 21, 7, 0, tzinfo=KST)


def snapshot(out: Path) -> dict[str, bytes]:
    """산출물 전부 (빌드 시각·캐시 통계가 들어가는 build.json 은 뺀다)."""
    return {
        p.relative_to(out).as_posix(): p.read_bytes()
        for p in sorted(out.rglob("*"))
        if p.is_file() and p.name not in {MARKER, BUILD_JSON}
    }


@pytest.fixture
def db(tmp_path) -> Path:
    path = tmp_path / "site.duckdb"
    with Cache(path) as cache:
        seed_site_cache(cache)
    return path


async def run(db: Path, out: Path, read_only: bool = True, **kw):
    with Cache(db, read_only=read_only) as cache:
        return await build_site(
            cache, out, 2024, built_on=WHEN.date(), built_at=WHEN, images=kw.pop("images", False), **kw
        )


async def test_second_build_reuses_every_checkup_and_matches_a_plain_build(db, tmp_path):
    plain = tmp_path / "plain"
    await run(db, plain)
    cache_dir = tmp_path / "cache"

    first = await run(db, tmp_path / "one", incremental_dir=cache_dir)
    assert "재사용 0/" in first.cache_summary
    second = await run(db, tmp_path / "two", incremental_dir=cache_dir)
    # 상장사·재무가 있는 회사 전부의 건강검진을 다시 쓴다
    assert second.cache_summary.startswith("증분 캐시 재사용 ")
    hits, total = second.cache_summary.split()[3].split("/")
    assert hits == total and int(total) > 0

    assert snapshot(tmp_path / "one") == snapshot(plain)
    assert snapshot(tmp_path / "two") == snapshot(plain)


async def test_changed_data_changes_the_fingerprint_and_recomputes(db, tmp_path):
    cache_dir = tmp_path / "cache"
    await run(db, tmp_path / "one", incremental_dir=cache_dir)
    with Cache(db) as cache:
        before = data_fingerprint(cache)
        cache.save_statements(statements(SAMSUNG.corp_code, 2024, 950.0, 60.0))  # 매출·이익 정정
        assert data_fingerprint(cache) != before
    report = await run(db, tmp_path / "two", incremental_dir=cache_dir)
    assert "재사용 0/" in report.cache_summary
    plain = tmp_path / "plain"
    await run(db, plain)
    assert snapshot(tmp_path / "two") == snapshot(plain)


async def test_fetch_time_alone_does_not_change_the_fingerprint(db):
    with Cache(db) as cache:
        before = data_fingerprint(cache)
        cache.conn.execute("UPDATE statement_lines SET fetched_at = fetched_at + INTERVAL 1 DAY")
        assert data_fingerprint(cache) == before


async def test_code_change_invalidates_the_cache(db, tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    await run(db, tmp_path / "one", incremental_dir=cache_dir)
    monkeypatch.setattr(incremental, "code_version", lambda: "다른 코드")
    report = await run(db, tmp_path / "two", incremental_dir=cache_dir)
    assert "재사용 0/" in report.cache_summary
    # 옛 판의 객체는 지운다 — 폴더가 끝없이 자라지 않게
    assert "지움" in report.cache_summary and " 0개 지움" not in report.cache_summary


def test_broken_object_counts_as_missing(tmp_path):
    cache = BuildCache(tmp_path / "c")
    cache.put_bytes("ab" * 32, b"not a pickle")
    assert cache.get_object("ab" * 32) is incremental.MISSING
    assert (cache.hits, cache.misses) == (0, 1)


async def test_jobs_split_the_work_across_processes_with_the_same_result(db, tmp_path, monkeypatch):
    monkeypatch.setattr(build_module, "PARALLEL_MIN_PER_JOB", 1)
    plain = tmp_path / "plain"
    await run(db, plain)
    await run(db, tmp_path / "par", jobs=2)
    assert snapshot(tmp_path / "par") == snapshot(plain)


async def test_jobs_fall_back_to_one_process_when_the_db_is_writable(db, tmp_path, monkeypatch):
    monkeypatch.setattr(build_module, "PARALLEL_MIN_PER_JOB", 1)
    monkeypatch.setattr(build_module, "_run_parallel", lambda *a, **k: pytest.fail("쓰기 모드에서 병렬"))
    report = await run(db, tmp_path / "w", read_only=False, jobs=4)
    assert report.companies == 3


async def test_share_card_pngs_are_reused_when_the_card_is_unchanged(db, tmp_path, monkeypatch):
    if resolve_fonts() is None:
        pytest.skip("한국어 글꼴이 없다")
    cache_dir = tmp_path / "cache"
    await run(db, tmp_path / "one", incremental_dir=cache_dir, images=True)
    import fin_checkup.site.pages.og_image as og_page

    monkeypatch.setattr(og_page, "render_many", lambda cards, *a: [pytest.fail("다시 그렸다") for _ in cards])
    await run(db, tmp_path / "two", incremental_dir=cache_dir, images=True)
    assert snapshot(tmp_path / "one") == snapshot(tmp_path / "two")


def test_cli_takes_jobs_and_incremental(db, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(settings, "fin_checkup_db_path", db)
    monkeypatch.setattr(build_module, "kst_today", lambda: date(2026, 11, 21))
    args = [
        "site",
        "build",
        "--year",
        "2024",
        "--no-images",
        "--jobs",
        "2",
        "--incremental",
        str(tmp_path / "c"),
    ]
    assert main([*args, "--out", str(tmp_path / "a")]) == 0
    assert main([*args, "--out", str(tmp_path / "b")]) == 0
    assert "증분 캐시 재사용 3/3" in capsys.readouterr().out
