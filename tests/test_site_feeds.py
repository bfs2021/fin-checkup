"""Atom 피드 — 회사별 `/feeds/c/<코드>.xml` · 시장 전체 `/feeds/disclosures.xml`.

XML 이 잘 짜였는지, Atom 필수 요소가 있는지, id·updated 가 빌드 날짜·주소와 무관하게 같은지 본다.
"""

from __future__ import annotations

import json
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import date

import pytest
from hub_seed import seed_site_cache

from fin_checkup.cli import main
from fin_checkup.config import settings
from fin_checkup.disclaimer import DISCLAIMER
from fin_checkup.metrics.signals import Signal
from fin_checkup.site.build import build_site
from fin_checkup.site.pages.feeds import feed_id
from fin_checkup.storage import Cache

A = {"a": "http://www.w3.org/2005/Atom"}
BASE = "https://example.github.io/fin-checkup/"
RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$")


def item(no: str, day: str, code: str = "005930", severity: str = "critical", **extra):
    return {
        "corp_code": "00126380",
        "stock_code": code,
        "corp_name": "삼성전자" if code == "005930" else "다른회사",
        "report_nm": f"공시 제목 {no}",
        "rcept_dt": day,
        "rcept_no": no,
        "category": "x",
        "category_label": "감사의견 비적정",
        "severity": severity,
        "is_correction": False,
        "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={no}",
        **extra,
    }


DISCLOSURES = {
    "format_version": 1,
    "bgn_de": "20261115",
    "end_de": "20261121",
    "items": [
        item("20261120000001", "20261120"),
        item("20261119000002", "20261119", severity="medium", report_nm="제목\x0b제어문자"),
        item("20261118000003", "20261118", code="999999"),
        item("20261117000004", "20261117", code="999999", severity="high"),
        item("20261116000005", "20261116", url="javascript:alert(1)"),
    ],
}


async def _build(tmp_path, name="out", base_url=BASE, built_on=date(2026, 11, 21), disclosures=None):
    with Cache(tmp_path / f"{name}.duckdb") as cache:
        seed_site_cache(cache)
        target = tmp_path / name
        await build_site(cache, target, 2024, base_url=base_url, built_on=built_on, disclosures=disclosures)
    return target


@pytest.fixture
async def out(tmp_path):
    return await _build(tmp_path, disclosures=DISCLOSURES)


def parse(path) -> ET.Element:
    return ET.parse(path).getroot()


def entries(root: ET.Element) -> dict[str, ET.Element]:
    return {e.find("a:title", A).text: e for e in root.findall("a:entry", A)}


def assert_valid_atom(root: ET.Element) -> None:
    assert root.tag == "{http://www.w3.org/2005/Atom}feed"
    for tag in ("id", "title", "updated"):
        assert root.find(f"a:{tag}", A) is not None and root.find(f"a:{tag}", A).text, tag
    assert RFC3339.match(root.find("a:updated", A).text)
    assert root.find("a:author/a:name", A).text == "fin-checkup"
    assert root.find("a:link[@rel='self']", A) is not None
    ids = [e.find("a:id", A).text for e in root.findall("a:entry", A)]
    assert len(ids) == len(set(ids)), "id 가 겹친다"
    for e in root.findall("a:entry", A):
        for tag in ("id", "title", "updated", "content"):
            assert e.find(f"a:{tag}", A) is not None and e.find(f"a:{tag}", A).text, tag
        assert e.find("a:id", A).text.startswith("urn:uuid:")
        assert RFC3339.match(e.find("a:updated", A).text)
        assert DISCLAIMER in e.find("a:content", A).text


async def test_every_feed_is_well_formed_atom(out):
    feeds = sorted((out / "feeds").rglob("*.xml"))
    assert {p.relative_to(out).as_posix() for p in feeds} == {
        "feeds/c/005930.xml",
        "feeds/c/105560.xml",
        "feeds/c/028300.xml",
        "feeds/disclosures.xml",
    }
    for path in feeds:
        assert_valid_atom(parse(path))


async def test_company_feed_has_one_entry_per_fiscal_year_dated_by_the_filing_deadline(out):
    root = parse(out / "feeds" / "c" / "005930.xml")
    got = entries(root)
    for year in (2022, 2023, 2024):
        e = got[f"삼성전자 {year} 사업연도 재무 신호등"]
        due = "03-30" if year == 2023 else "03-31"  # 사업연도 종료 후 90일 — 2024년은 윤년
        assert e.find("a:updated", A).text == f"{year + 1}-{due}T00:00:00+09:00"
        assert e.find("a:id", A).text == feed_id(f"c/005930/fy/{year}")
        assert e.find("a:link", A).get("href") == f"{BASE}c/005930/"
        content = e.find("a:content", A).text
        assert "지표 17개" in content and "법정 제출 기한" in content and "정상" in content
    assert root.find("a:updated", A).text == "2026-11-20T00:00:00+09:00", "가장 최근 항목 = 최근 공시"
    assert root.find("a:link[@rel='alternate']", A).get("href") == f"{BASE}c/005930/"
    assert root.find("a:link[@rel='self']", A).get("href") == f"{BASE}feeds/c/005930.xml"


async def test_signal_changes_vs_the_previous_year_are_listed_in_both_directions(out):
    from fin_checkup.site.pages.feeds import year_results

    with Cache(out.parent / "out.duckdb") as cache:
        from fin_checkup.site.build import collect_companies

        companies, _ = await collect_companies(cache, 2024)
    samsung = next(c for c in companies if c.stock_code == "005930")
    results = {f.bsns_year: r for f, r in year_results(samsung)}
    before = {m.key: m.signal for m in results[2023].metrics}
    expected = [
        m
        for m in results[2024].metrics
        if before[m.key] is not m.signal and Signal.UNKNOWN not in (before[m.key], m.signal)
    ]
    assert expected, "시드 데이터에 2023→2024 신호 변화가 있어야 이 테스트가 뜻이 있다"

    got = entries(parse(out / "feeds" / "c" / "005930.xml"))
    e = got[f"삼성전자 2023→2024 사업연도 신호가 바뀐 지표 {len(expected)}개"]
    content = e.find("a:content", A).text
    for m in expected:
        assert (
            f"{m.label}: {before[m.key].emoji} {before[m.key].label} → {m.signal.emoji} {m.signal.label}"
            in content
        )
    assert e.find("a:id", A).text == feed_id("c/005930/fy/2024/signals")
    assert "⚫ 데이터 없음 →" not in content and "→ ⚫" not in content


async def test_a_single_year_company_has_no_change_entry(out):
    titles = list(entries(parse(out / "feeds" / "c" / "028300.xml")))
    assert titles == ["에이치엘비 2024 사업연도 재무 신호등"]


async def test_company_feed_carries_its_own_risk_disclosures(out):
    got = entries(parse(out / "feeds" / "c" / "005930.xml"))
    dart = {t: e for t, e in got.items() if t.startswith("[")}
    assert set(dart) == {
        "[감사의견 비적정] 공시 제목 20261120000001",
        "[감사의견 비적정] 제목제어문자",
        "[감사의견 비적정] 공시 제목 20261116000005",
    }
    first = dart["[감사의견 비적정] 공시 제목 20261120000001"]
    assert first.find("a:id", A).text == feed_id("dart/20261120000001")
    assert first.find("a:updated", A).text == "2026-11-20T00:00:00+09:00"
    assert first.find("a:link", A).get("href").startswith("https://dart.fss.or.kr/")
    assert dart["[감사의견 비적정] 공시 제목 20261116000005"].find("a:link", A) is None, (
        "DART 아닌 주소는 링크 안 함"
    )


async def test_market_feed_has_critical_disclosures_only(out):
    root = parse(out / "feeds" / "disclosures.xml")
    titles = list(entries(root))
    assert titles == [
        "[감사의견 비적정] 삼성전자 — 공시 제목 20261120000001",
        "[감사의견 비적정] 다른회사 — 공시 제목 20261118000003",
        "[감사의견 비적정] 삼성전자 — 공시 제목 20261116000005",
    ]
    assert "20261115~20261121" in root.find("a:subtitle", A).text


async def test_ids_and_dates_do_not_depend_on_build_date_or_base_url(tmp_path):
    one = await _build(tmp_path, "one", disclosures=DISCLOSURES)
    two = await _build(tmp_path, "two", base_url="/", built_on=date(2027, 1, 5), disclosures=DISCLOSURES)

    def stamp(path):
        root = parse(path)
        return root.find("a:id", A).text, [
            (e.find("a:id", A).text, e.find("a:updated", A).text) for e in root.findall("a:entry", A)
        ]

    for rel in ("feeds/c/005930.xml", "feeds/c/105560.xml", "feeds/disclosures.xml"):
        assert stamp(one / rel) == stamp(two / rel), rel
    assert feed_id("c/005930/fy/2024") == "urn:uuid:" + str(
        uuid.uuid5(uuid.NAMESPACE_URL, "fin-checkup:c/005930/fy/2024")
    )


async def test_relative_links_without_an_absolute_base(tmp_path):
    out = await _build(tmp_path, "rel", base_url="/")
    root = parse(out / "feeds" / "c" / "005930.xml")
    assert root.find("a:link[@rel='self']", A).get("href") == "../../feeds/c/005930.xml"
    assert root.find("a:link[@rel='alternate']", A).get("href") == "../../c/005930/"


async def test_without_disclosures_the_market_feed_is_empty_but_valid(tmp_path):
    out = await _build(tmp_path, "nodisc")
    root = parse(out / "feeds" / "disclosures.xml")
    assert_valid_atom(root)
    assert root.findall("a:entry", A) == []
    assert root.find("a:updated", A).text == "2026-11-21T00:00:00+09:00"
    assert not any(t.startswith("[") for t in entries(parse(out / "feeds" / "c" / "005930.xml")))


async def test_pages_advertise_the_feeds(out):
    company = (out / "c" / "005930" / "index.html").read_text(encoding="utf-8")
    assert (
        '<link rel="alternate" type="application/atom+xml" title="삼성전자 재무 신호등 피드" '
        'href="../../feeds/c/005930.xml">'
    ) in company
    watch = (out / "watch" / "index.html").read_text(encoding="utf-8")
    assert 'id="feeds"' in watch and "/feed subscribe" in watch and "RSS 리더" in watch
    assert 'href="../feeds/disclosures.xml"' in watch


def test_cli_passes_the_disclosures_json_to_the_build(tmp_path, monkeypatch, capsys):
    db = tmp_path / "cli.duckdb"
    with Cache(db) as c:
        seed_site_cache(c)
    monkeypatch.setattr(settings, "fin_checkup_db_path", db)
    path = tmp_path / "disclosures.json"
    path.write_text(json.dumps(DISCLOSURES, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "site-out"
    args = ["site", "build", "--year", "2024", "--out", str(out), "--limit", "1"]
    assert main([*args, "--disclosures", str(path)]) == 0
    assert "20261120000001" in (out / "feeds" / "c" / "005930.xml").read_text(encoding="utf-8")

    path.write_text('{"format_version": 99, "items": []}', encoding="utf-8")
    assert main([*args, "--disclosures", str(path)]) == 0
    assert "공시 없이 만듭니다" in capsys.readouterr().out
