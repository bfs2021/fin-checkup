"""시장 전체 최근 위험 공시 수집 (`disclosures fetch`) — 사실만, 한도 안에서, 키 없이."""

from __future__ import annotations

import json
import logging
from datetime import date

import httpx
import pytest
import respx

from fin_checkup import disclosures
from fin_checkup.alerts.worker import WATCH_TYPES
from fin_checkup.cli import main
from fin_checkup.config import settings
from fin_checkup.dart.client import DartClient, RateLimitExceeded
from fin_checkup.disclosures import FORMAT_VERSION, fetch_recent_risks
from fin_checkup.storage import Cache, today_key

BASE = "https://opendart.fss.or.kr/api"
TODAY = date(2026, 11, 21)


def item(rcept_no: str, report_nm: str, corp_cls: str = "Y", rcept_dt: str = "20261120", **kw) -> dict:
    return {
        "rcept_no": rcept_no,
        "corp_code": kw.get("corp_code", "00126380"),
        "corp_name": kw.get("corp_name", "삼성전자"),
        "stock_code": kw.get("stock_code", "005930" if corp_cls in "YKN" else ""),
        "corp_cls": corp_cls,
        "report_nm": report_nm,
        "flr_nm": "삼성전자",
        "rcept_dt": rcept_dt,
    }


def page(items: list[dict], total_page: int = 1, page_no: int = 1) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "status": "000",
            "message": "정상",
            "page_no": page_no,
            "total_page": total_page,
            "list": items,
        },
    )


EMPTY = httpx.Response(200, json={"status": "013", "message": "조회된 데이타가 없습니다."})

#: 공시유형별 응답. B(주요사항)와 I(거래소)에 같은 공시가 겹쳐 잡히는 경우를 넣는다.
BY_TYPE = {
    "B": [
        item("20261120000001", "주요사항보고서(유상증자결정)"),
        item(
            "20261119000002",
            "주요사항보고서(전환사채권발행결정)",
            rcept_dt="20261119",
            corp_cls="K",
            corp_code="00164779",
            corp_name="에스케이하이닉스",
            stock_code="000660",
        ),
        item(
            "20261120000009",
            "주요사항보고서(유상증자결정)",
            corp_cls="E",
            corp_code="77777777",
            corp_name="비상장회사",
        ),
    ],
    "I": [
        item("20261121000003", "관리종목지정(감사의견거절)", rcept_dt="20261121"),
        item("20261121000004", "주권매매거래정지해제", rcept_dt="20261121"),  # 해제는 위험 공시가 아니다
        item("20261120000001", "주요사항보고서(유상증자결정)"),  # B 와 겹침
    ],
    "D": [item("20261118000005", "임원ㆍ주요주주특정증권등소유상황보고서", rcept_dt="20261118")],
}


def mock_list(by_type: dict[str, list[dict]] = BY_TYPE):
    def handler(request: httpx.Request) -> httpx.Response:
        found = by_type.get(request.url.params["pblntf_ty"])
        return page(found) if found else EMPTY

    return respx.get(f"{BASE}/list.json").mock(side_effect=handler)


@pytest.fixture
def client(test_settings):
    return DartClient(settings=test_settings)


# ── 수집 ─────────────────────────────────────────────────────────


@respx.mock
async def test_keeps_only_listed_risk_disclosures_once_each(client):
    route = mock_list()
    payload = await fetch_recent_risks(client, days=7, today=TODAY)
    await client.aclose()

    assert route.call_count == len(WATCH_TYPES)
    params = route.calls.last.request.url.params
    assert params["bgn_de"] == "20261115" and params["end_de"] == "20261121"

    nos = [i["rcept_no"] for i in payload["items"]]
    # 날짜 내림차순(같은 날이면 접수번호 내림차순) — 심각도·지표 순 정렬이 아니다.
    assert nos == ["20261121000003", "20261120000001", "20261119000002", "20261118000005"]
    assert payload["count"] == 4
    assert payload["bgn_de"] == "20261115" and payload["end_de"] == "20261121"
    assert payload["format_version"] == FORMAT_VERSION
    assert payload["truncated_types"] == []


@respx.mock
async def test_items_carry_facts_only(client):
    mock_list()
    payload = await fetch_recent_risks(client, days=7, today=TODAY)
    await client.aclose()

    first = payload["items"][0]
    assert first == {
        "corp_code": "00126380",
        "stock_code": "005930",
        "corp_name": "삼성전자",
        "report_nm": "관리종목지정(감사의견거절)",
        "rcept_dt": "20261121",
        "rcept_no": "20261121000003",
        "category": "listing_status",
        "category_label": "관리종목·상장폐지 관련",
        "severity": "critical",
        "is_correction": False,
        "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261121000003",
    }


@respx.mock
async def test_reports_types_that_hit_the_page_cap(client):
    """페이지 상한에 걸린 유형은 빠진 공시가 있을 수 있다 — 없는 걸 없다고 적는다."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["pblntf_ty"] == "D":
            return page([item("20261118000005", "대량보유상황보고서(일반)")], total_page=3)
        return EMPTY

    respx.get(f"{BASE}/list.json").mock(side_effect=handler)
    payload = await fetch_recent_risks(client, days=7, today=TODAY, max_pages=1)
    await client.aclose()
    assert payload["truncated_types"] == ["D"]


@pytest.mark.parametrize("days", [0, 91])
async def test_rejects_a_range_dart_will_not_serve(client, days):
    """corp_code 없이 조회하면 DART 는 3개월까지만 준다."""
    with pytest.raises(ValueError):
        await fetch_recent_risks(client, days=days, today=TODAY)
    await client.aclose()


@respx.mock
async def test_rate_limit_is_not_retried(client):
    route = respx.get(f"{BASE}/list.json").mock(
        return_value=httpx.Response(200, json={"status": "020", "message": "요청 제한을 초과하였습니다."})
    )
    with pytest.raises(RateLimitExceeded):
        await fetch_recent_risks(client, days=7, today=TODAY)
    await client.aclose()
    assert route.call_count == 1


# ── CLI ──────────────────────────────────────────────────────────


@pytest.fixture
def cli_env(tmp_path, monkeypatch, test_settings):
    db = tmp_path / "cli.duckdb"
    monkeypatch.setattr(settings, "fin_checkup_db_path", db)
    monkeypatch.setattr(settings, "dart_api_key", test_settings.dart_api_key)
    monkeypatch.setattr(settings, "dart_min_delay", 0.0)
    monkeypatch.setattr(disclosures, "kst_today", lambda: TODAY)
    return db


@respx.mock
def test_cli_writes_the_json_file_and_counts_calls(cli_env, tmp_path, capsys, caplog):
    mock_list()
    out = tmp_path / "site-data" / "disclosures.json"
    with caplog.at_level(logging.DEBUG):
        assert main(["disclosures", "fetch", "--days", "7", "--out", str(out)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["count"] == 4
    key = settings.dart_api_key
    assert key not in out.read_text(encoding="utf-8")
    captured = capsys.readouterr()
    assert key not in captured.out + captured.err
    assert key not in caplog.text

    with Cache(cli_env) as cache:
        assert cache.dart_calls_today(today_key()) == len(WATCH_TYPES)


@respx.mock
def test_cli_stops_on_rate_limit_and_keeps_the_previous_file(cli_env, tmp_path, capsys, caplog):
    route = respx.get(f"{BASE}/list.json").mock(
        return_value=httpx.Response(200, json={"status": "020", "message": "요청 제한을 초과하였습니다."})
    )
    out = tmp_path / "disclosures.json"
    out.write_text('{"previous": true}', encoding="utf-8")
    with caplog.at_level(logging.DEBUG):
        assert main(["disclosures", "fetch", "--days", "7", "--out", str(out)]) == 1

    assert route.call_count == 1
    assert json.loads(out.read_text(encoding="utf-8")) == {"previous": True}
    captured = capsys.readouterr()
    assert "허용량" in captured.out
    assert settings.dart_api_key not in captured.out + captured.err + caplog.text


@respx.mock
def test_cli_refuses_when_the_daily_budget_cannot_cover_the_run(cli_env, tmp_path, capsys):
    route = mock_list()
    with Cache(cli_env) as cache:
        cache.record_dart_call("fnlttSinglAcntAll.json", today_key(), count=settings.dart_daily_quota - 3)

    out = tmp_path / "disclosures.json"
    assert main(["disclosures", "fetch", "--days", "7", "--out", str(out)]) == 1
    assert route.call_count == 0
    assert not out.exists()
    assert "허용량" in capsys.readouterr().out


def test_cli_without_a_key_says_so(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(settings, "dart_api_key", "")
    monkeypatch.setattr(settings, "fin_checkup_db_path", tmp_path / "x.duckdb")
    assert main(["disclosures", "fetch", "--out", str(tmp_path / "d.json")]) == 1
    assert "DART_API_KEY" in capsys.readouterr().out
