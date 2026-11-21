"""공개 스냅샷 export/import — 허용목록 밖의 테이블은 절대 밖으로 나가지 않는다."""

from __future__ import annotations

import json

import duckdb
import pytest

from fin_checkup import snapshot
from fin_checkup.cli import main
from fin_checkup.config import settings
from fin_checkup.models import (
    AccountLine,
    Company,
    CorpCode,
    FsDiv,
    Market,
    RawStatements,
    ReportCode,
)
from fin_checkup.snapshot import (
    EXCLUDED_TABLES,
    EXPORT_TABLES,
    SENSITIVE_TABLES,
    SnapshotError,
    export_snapshot,
    import_snapshot,
)
from fin_checkup.storage import Cache

#: 설계서가 개인정보·운영 테이블로 못박은 것. 스키마에 없더라도(usage_daily) 이름으로 막는다.
MUST_NEVER_EXPORT = {
    "accounts",
    "api_keys",
    "subscriptions",
    "watchlist",
    "notified",
    "usage_daily",
    "dart_call_log",
}


def _schema_tables(path) -> set[str]:
    con = duckdb.connect(str(path), read_only=True)
    try:
        return {row[0] for row in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
    finally:
        con.close()


def seed(path, secret: str) -> None:
    """허용·차단 테이블 모두에 한 줄 이상 넣는다. 차단 테이블엔 비밀값을 심는다."""
    with Cache(path) as cache:
        cache.save_corp_codes(
            [
                CorpCode(corp_code="00126380", corp_name="삼성전자", stock_code="005930"),
                CorpCode(corp_code="00164779", corp_name="SK하이닉스", stock_code="000660"),
                CorpCode(corp_code="99999999", corp_name="비상장회사", stock_code=""),
            ]
        )
        cache.save_company(
            Company(
                corp_code="00126380",
                corp_name="삼성전자",
                stock_code="005930",
                market=Market.KOSPI,
                industry_code="264",
            )
        )
        cache.save_statements(
            RawStatements(
                corp_code="00126380",
                bsns_year=2024,
                reprt_code=ReportCode.ANNUAL,
                fs_div=FsDiv.CFS,
                lines=[
                    AccountLine(
                        sj_div="BS",
                        account_id="ifrs-full_Assets",
                        account_nm="자산총계",
                        thstrm_amount=100.0,
                        ord=1,
                    ),
                    AccountLine(
                        sj_div="IS",
                        account_id="ifrs-full_Revenue",
                        account_nm="매출액",
                        thstrm_amount=None,
                        ord=2,
                    ),
                ],
            )
        )
        cache.save_metric_values("00126380", 2024, {"debt_ratio": 25.5, "roe": 8.1})
        cache.record_miss("00164779", 2024, ReportCode.ANNUAL, FsDiv.CFS)
        cache.save_sec_tickers([("AAPL", "0000320193", "Apple Inc.")])
        # 아래는 전부 밖으로 나가면 안 되는 것 — 비밀값을 섞어 둔다.
        cache.add_watch(f"chat-{secret}", CorpCode(corp_code="00126380", corp_name="삼성전자"))
        cache.mark_notified(f"chat-{secret}", "20241101000001")
        cache.create_account("user-1", f"{secret}@example.com")
        cache.save_api_key(f"hash-{secret}", "user-1", "fck_abcd")
        cache.set_meta("alerts.last_poll", secret)
        cache.record_dart_call(f"list.json?{secret}", "2026-11-21")


@pytest.fixture
def source(tmp_path, test_settings):
    path = tmp_path / "source.duckdb"
    seed(path, test_settings.dart_api_key)
    return path


# ── (a) 허용목록 ─────────────────────────────────────────────────


def test_every_schema_table_is_classified(tmp_path):
    """스키마에 새 테이블이 생기면 공개할지 말지 정해야 이 테스트가 통과한다.

    분류를 빠뜨린 채 '전부 export' 로 바뀌면 개인정보가 공개 릴리스로 나간다.
    """
    path = tmp_path / "fresh.duckdb"
    Cache(path).close()
    tables = _schema_tables(path)
    unclassified = tables - set(EXPORT_TABLES) - set(EXCLUDED_TABLES)
    assert not unclassified, f"공개 여부를 정하지 않은 테이블: {sorted(unclassified)}"
    assert not set(EXPORT_TABLES) & set(EXCLUDED_TABLES)


def test_sensitive_tables_are_never_in_the_allowlist():
    assert MUST_NEVER_EXPORT <= SENSITIVE_TABLES
    assert SENSITIVE_TABLES <= set(EXCLUDED_TABLES)
    assert not set(EXPORT_TABLES) & MUST_NEVER_EXPORT


def test_export_writes_only_allowlisted_tables(source, tmp_path, test_settings):
    out = tmp_path / "snap"
    manifest = export_snapshot(source, out, secrets=[test_settings.dart_api_key])

    files = {p.name for p in out.iterdir()}
    assert files == {f"{t}.parquet" for t in EXPORT_TABLES} | {"manifest.json"}
    assert set(manifest["tables"]) == set(EXPORT_TABLES)
    for name in MUST_NEVER_EXPORT:
        assert f"{name}.parquet" not in files


def test_export_refuses_a_database_with_an_unclassified_table(source, tmp_path):
    """런타임에도 막는다 — 테스트를 안 돌린 포크가 새 테이블을 더해도 export 가 멈춘다."""
    con = duckdb.connect(str(source))
    con.execute("CREATE TABLE user_emails (email VARCHAR)")
    con.close()

    out = tmp_path / "snap"
    with pytest.raises(SnapshotError, match="user_emails"):
        export_snapshot(source, out)
    assert not out.exists() or not any(out.iterdir())


def test_corp_codes_export_keeps_only_listed_companies(source, tmp_path):
    out = tmp_path / "snap"
    manifest = export_snapshot(source, out)
    con = duckdb.connect()
    rows = con.execute(
        "SELECT corp_code FROM read_parquet(?) ORDER BY corp_code",
        [str(out / "corp_codes.parquet")],
    ).fetchall()
    assert [r[0] for r in rows] == ["00126380", "00164779"]
    assert manifest["tables"]["corp_codes"]["rows"] == 2


def test_manifest_describes_the_snapshot(source, tmp_path):
    out = tmp_path / "snap"
    export_snapshot(source, out)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == snapshot.SNAPSHOT_SCHEMA_VERSION
    assert len(manifest["built_on"]) == 10  # YYYY-MM-DD, KST
    assert manifest["bsns_years"] == [2024]
    assert manifest["tables"]["statement_lines"] == {"file": "statement_lines.parquet", "rows": 2}
    assert manifest["tables"]["metric_values"]["rows"] == 2


def test_export_refuses_a_non_empty_output_dir(source, tmp_path):
    out = tmp_path / "snap"
    out.mkdir()
    (out / "stale.parquet").write_text("x")
    with pytest.raises(SnapshotError):
        export_snapshot(source, out)


# ── (b) 왕복 ─────────────────────────────────────────────────────


def _rows(path, table: str, where: str = "") -> list[tuple]:
    con = duckdb.connect(str(path), read_only=True)
    try:
        return sorted(con.execute(f"SELECT * FROM {table} {where}").fetchall(), key=repr)
    finally:
        con.close()


def test_round_trip_reproduces_the_same_rows(source, tmp_path):
    out = tmp_path / "snap"
    export_snapshot(source, out)
    rebuilt = tmp_path / "rebuilt.duckdb"
    import_snapshot(out, rebuilt)

    for table in EXPORT_TABLES:
        where = "WHERE stock_code IS NOT NULL AND trim(stock_code) <> ''" if table == "corp_codes" else ""
        assert _rows(rebuilt, table) == _rows(source, table, where), table
    # 차단 테이블은 스키마로만 있고 비어 있다.
    for table in ("watchlist", "notified", "accounts", "api_keys", "dart_call_log"):
        assert _rows(rebuilt, table) == [], table


def test_rebuilt_cache_is_readable_by_the_cache_layer(source, tmp_path):
    out = tmp_path / "snap"
    export_snapshot(source, out)
    rebuilt = tmp_path / "rebuilt.duckdb"
    import_snapshot(out, rebuilt)
    with Cache(rebuilt, read_only=True) as cache:
        assert cache.find_by_stock_code("005930").corp_name == "삼성전자"
        assert cache.get_statements("00126380", 2024) is not None
        assert cache.metric_values_count(2024) == 1


def test_import_refuses_to_overwrite_an_existing_database(source, tmp_path):
    out = tmp_path / "snap"
    export_snapshot(source, out)
    with pytest.raises(SnapshotError):
        import_snapshot(out, source)


def test_import_rejects_an_unknown_schema_version(source, tmp_path):
    out = tmp_path / "snap"
    export_snapshot(source, out)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["schema_version"] = 999
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    target = tmp_path / "rebuilt.duckdb"
    with pytest.raises(SnapshotError, match="999"):
        import_snapshot(out, target)
    assert not target.exists()


def test_import_rejects_a_table_outside_the_allowlist(source, tmp_path):
    """누가 릴리스 자산에 accounts.parquet 을 끼워 넣어도 들여오지 않는다."""
    out = tmp_path / "snap"
    export_snapshot(source, out)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["tables"]["accounts"] = {"file": "accounts.parquet", "rows": 0}
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    target = tmp_path / "rebuilt.duckdb"
    with pytest.raises(SnapshotError, match="accounts"):
        import_snapshot(out, target)
    assert not target.exists()


def test_import_detects_a_row_count_mismatch(source, tmp_path):
    out = tmp_path / "snap"
    export_snapshot(source, out)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["tables"]["metric_values"]["rows"] = 5
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    target = tmp_path / "rebuilt.duckdb"
    with pytest.raises(SnapshotError, match="metric_values"):
        import_snapshot(out, target)
    assert not target.exists()


# ── (c) 인증키 ───────────────────────────────────────────────────


def _all_strings(path) -> list[str]:
    con = duckdb.connect()
    try:
        rel = con.execute("SELECT * FROM read_parquet(?)", [str(path)])
        return [str(v) for row in rel.fetchall() for v in row if isinstance(v, str)]
    finally:
        con.close()


def test_no_exported_file_contains_the_dart_key(source, tmp_path, test_settings):
    key = test_settings.dart_api_key
    out = tmp_path / "snap"
    export_snapshot(source, out, secrets=[key])

    for path in out.iterdir():
        assert key.encode() not in path.read_bytes(), path.name
        if path.suffix == ".parquet":
            assert not any(key in s for s in _all_strings(path)), path.name


def test_export_aborts_when_the_key_leaks_into_an_allowlisted_table(tmp_path, test_settings):
    """허용 테이블에 키가 섞여 들어갔다면(예: 홈페이지 칸) 산출물을 지우고 멈춘다."""
    key = test_settings.dart_api_key
    path = tmp_path / "leaky.duckdb"
    with Cache(path) as cache:
        cache.save_company(Company(corp_code="1", corp_name="회사", homepage=f"https://x/?crtfc_key={key}"))
    out = tmp_path / "snap"
    with pytest.raises(SnapshotError) as excinfo:
        export_snapshot(path, out, secrets=[key])
    assert key not in str(excinfo.value)
    assert not out.exists() or not any(out.iterdir())


# ── CLI ──────────────────────────────────────────────────────────


def test_cli_export_then_import(source, tmp_path, monkeypatch, capsys, test_settings):
    monkeypatch.setattr(settings, "fin_checkup_db_path", source)
    monkeypatch.setattr(settings, "dart_api_key", test_settings.dart_api_key)
    out = tmp_path / "snap"
    assert main(["snapshot", "export", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "statement_lines" in printed
    assert test_settings.dart_api_key not in printed

    rebuilt = tmp_path / "rebuilt.duckdb"
    assert main(["snapshot", "import", str(out), "--db", str(rebuilt)]) == 0
    assert _rows(rebuilt, "metric_values") == _rows(source, "metric_values")


def test_cli_reports_snapshot_errors_without_a_traceback(source, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(settings, "fin_checkup_db_path", source)
    out = tmp_path / "snap"
    export_snapshot(source, out)
    assert main(["snapshot", "import", str(out), "--db", str(source)]) == 1
    assert "이미 있습니다" in capsys.readouterr().out
