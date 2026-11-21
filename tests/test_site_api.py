"""정적 JSON `/api/c/<코드>.json` · `/api/index.json` — 스키마 모양·면책·⚫/⊘ 를 그대로 싣는지."""

from __future__ import annotations

import json
from datetime import date

import pytest
from hub_seed import HLB, KB, SAMSUNG, seed_site_cache

from fin_checkup.disclaimer import DISCLAIMER
from fin_checkup.metrics import engine
from fin_checkup.site.build import build_site
from fin_checkup.site.pages.api import SCHEMA_VERSION
from fin_checkup.storage import Cache

METRIC_FIELDS = {
    "key",
    "label",
    "category",
    "value",
    "unit",
    "signal",
    "formula",
    "thresholds",
    "threshold_text",
    "note",
    "peer",
    "delta",
}


@pytest.fixture
async def out(tmp_path):
    with Cache(tmp_path / "site.duckdb") as cache:
        seed_site_cache(cache)
        target = tmp_path / "out"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    return target


def load(out, *parts):
    return json.loads((out / "api" / "/".join(parts)).read_text(encoding="utf-8"))


async def test_one_json_per_company_with_the_documented_top_level_shape(out):
    for corp in (SAMSUNG, KB, HLB):
        doc = load(out, "c", f"{corp.stock_code}.json")
        assert doc["schema_version"] == SCHEMA_VERSION
        assert doc["disclaimer"] == DISCLAIMER
        assert doc["fiscal_year"] == 2024
        assert doc["built_on"] == "2026-11-21"
        assert doc["company"]["stock_code"] == corp.stock_code
        assert doc["company"]["name"] == corp.corp_name
        assert doc["company"]["page"] == f"c/{corp.stock_code}/"
        assert set(doc) >= {"report", "metrics", "red_flags", "sources", "currency"}


async def test_every_metric_carries_formula_signal_and_thresholds(out):
    doc = load(out, "c", "005930.json")
    assert [m["key"] for m in doc["metrics"]] == [d.key for d in engine.METRIC_DEFS]
    for m in doc["metrics"]:
        assert set(m) == METRIC_FIELDS, m["key"]
        assert m["formula"], m["key"]
        assert m["threshold_text"], m["key"]
        assert set(m["signal"]) == {"key", "emoji", "label"}
    roe = next(m for m in doc["metrics"] if m["key"] == "roe")
    band = next(d for d in engine.METRIC_DEFS if d.key == "roe").band
    assert roe["thresholds"] == {
        "good": band.good,
        "warn": band.warn,
        "higher_is_better": band.higher_is_better,
    }


async def test_missing_value_is_null_and_black_never_zero(out):
    doc = load(out, "c", "005930.json")
    fcf = next(m for m in doc["metrics"] if m["key"] == "fcf")
    assert fcf["value"] is None
    assert fcf["signal"]["key"] == "unknown"
    assert fcf["note"]


async def test_not_applicable_metric_keeps_what_to_look_at_instead(out):
    doc = load(out, "c", "105560.json")
    debt = next(m for m in doc["metrics"] if m["key"] == "debt_ratio")
    assert debt["signal"]["key"] == "not_applicable"
    assert debt["thresholds"] is None
    assert "BIS" in debt["note"]


async def test_delta_and_peer_are_null_or_structured(out):
    doc = load(out, "c", "005930.json")
    opm = next(m for m in doc["metrics"] if m["key"] == "operating_margin")
    assert opm["delta"] == {
        "previous": pytest.approx(12.5),
        "current": pytest.approx(40 / 900 * 100, rel=1e-3),
        "improved": False,
        "summary": opm["delta"]["summary"],
    }
    # 시드 캐시는 대조군이 5개사 미만이라 분포를 내지 않는다 — 지어내지 않고 null.
    assert all(m["peer"] is None for m in doc["metrics"])
    hlb = load(out, "c", "028300.json")
    assert all(m["delta"] is None for m in hlb["metrics"]), "1개년뿐이면 작년 비교 없음"


async def test_sources_name_the_dart_request_without_any_key(out):
    doc = load(out, "c", "005930.json")
    text = json.dumps(doc, ensure_ascii=False)
    assert "crtfc_key" not in text
    api = next(s for s in doc["sources"] if s.get("params"))
    assert api["params"] == {
        "corp_code": SAMSUNG.corp_code,
        "bsns_year": "2024",
        "reprt_code": "11011",
        "fs_div": "CFS",
    }


async def test_index_lists_every_company_with_links(out):
    index = load(out, "index.json")
    assert index["schema_version"] == SCHEMA_VERSION
    assert index["disclaimer"] == DISCLAIMER
    assert index["fiscal_year"] == 2024
    codes = [c["stock_code"] for c in index["companies"]]
    assert codes == sorted(codes) == ["005930", "028300", "105560"]
    first = index["companies"][0]
    assert first == {
        "stock_code": "005930",
        "name": "삼성전자",
        "market": "KOSPI",
        "json": "api/c/005930.json",
        "page": "c/005930/",
    }


async def test_json_is_strict_no_nan(out):
    for path in (out / "api").rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"), parse_constant=pytest.fail)
