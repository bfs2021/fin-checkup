"""회사 페이지 '최근 위험 공시' · 첫 화면 '최근 상장 지위·존속 관련 공시' — 공시 JSON 을 읽어 사실만.

파일이 없으면 두 섹션 모두 아예 없다 (빈 상자를 그리지 않는다).
"""

from __future__ import annotations

import json
import re
from datetime import date

import pytest
from hub_seed import seed_site_cache

from fin_checkup.alerts.classify import RiskKind, is_market_wide
from fin_checkup.cli import main
from fin_checkup.config import settings
from fin_checkup.disclaimer import DISCLAIMER
from fin_checkup.disclosures import FORMAT_VERSION
from fin_checkup.site.build import build_site
from fin_checkup.site.disclosures import DisclosureFormatError, load_disclosures
from fin_checkup.site.guard import check_site
from fin_checkup.storage import Cache


def entry(rcept_no, report_nm, category, stock_code="005930", corp_name="삼성전자", rcept_dt=None, **kw):
    return {
        "corp_code": kw.get("corp_code", "00126380"),
        "stock_code": stock_code,
        "corp_name": corp_name,
        "report_nm": report_nm,
        "rcept_dt": rcept_dt or rcept_no[:8],
        "rcept_no": rcept_no,
        "category": category,
        "category_label": RiskKind(category).label if category in RiskKind._value2member_map_ else "",
        "severity": "high",
        "is_correction": report_nm.startswith("["),
        "url": kw.get("url", f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"),
    }


ITEMS = [
    entry("20261120000001", "주요사항보고서(유상증자결정)", "capital_raise"),
    entry("20261118000002", "임원ㆍ주요주주특정증권등소유상황보고서", "insider_trading"),
    # 같은 회사·같은 날·같은 종류 둘 → 첫 화면에선 하나로 (알림 채널과 같은 규칙)
    entry(
        "20261119000010",
        "주권매매거래정지(지정자문인 선임계약 해지)",
        "listing_status",
        stock_code="028300",
        corp_name="에이치엘비",
        corp_code="00400000",
    ),
    entry(
        "20261119000011",
        "기타시장안내(상장폐지절차 안내)",
        "listing_status",
        stock_code="028300",
        corp_name="에이치엘비",
        corp_code="00400000",
    ),
    # 사이트에 페이지가 없는 회사 → 이름만 (링크 없음)
    entry(
        "20261121000020",
        "회생절차개시신청",
        "distress",
        stock_code="999990",
        corp_name="없는회사",
        corp_code="00999990",
    ),
    entry(
        "20261117000030",
        "감사보고서제출",
        "audit_opinion",
        stock_code="105560",
        corp_name="KB금융",
        corp_code="00688996",
    ),
]


def payload(items=ITEMS, **over):
    doc = {
        "format_version": FORMAT_VERSION,
        "generated_at": "2026-11-21T07:00:00+09:00",
        "source": "DART 공시검색(list.json) · opendart.fss.or.kr",
        "scope": "유가증권·코스닥·코넥스 상장사",
        "bgn_de": "20261115",
        "end_de": "20261121",
        "days": 7,
        "truncated_types": [],
        "count": len(items),
        "items": items,
    }
    doc.update(over)
    return doc


def write(tmp_path, doc, name="disclosures.json"):
    path = tmp_path / name
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


async def build(tmp_path, feed=None, name="out"):
    with Cache(tmp_path / f"{name}.duckdb") as cache:
        seed_site_cache(cache)
        target = tmp_path / name
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21), disclosures=feed)
    return target


@pytest.fixture
async def out(tmp_path):
    return await build(tmp_path, load_disclosures(write(tmp_path, payload())))


def read(out, *parts):
    return (out.joinpath(*parts)).read_text(encoding="utf-8")


def section(html: str, ident: str) -> str:
    m = re.search(rf'<section[^>]*id="{ident}".*?</section>', html, re.S)
    return m.group(0) if m else ""


# ── 회사 페이지 ─────────────────────────────────────────────────────


async def test_company_page_lists_its_recent_risk_disclosures_as_facts(out):
    block = section(read(out, "c", "005930", "index.html"), "disclosures")
    assert block, "섹션이 없다"
    assert "최근 위험 공시" in block
    # 최근 것부터: 유상증자(11-20) → 임원 소유(11-18)
    assert block.index("유상증자결정") < block.index("소유상황보고서")
    assert '<time datetime="2026-11-20">2026-11-20</time>' in block
    assert 'href="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261120000001"' in block
    assert 'href="../../learn/disclosures/#capital_raise"' in block
    assert RiskKind.CAPITAL_RAISE.label in block
    assert "2026-11-15" in block and "2026-11-21" in block  # 조회 기간을 적는다
    assert "🚨" not in block  # 긴급하게 읽히는 표시는 쓰지 않는다
    assert 'href="../../feeds/c/005930.xml"' in block  # 같은 공시의 피드


async def test_without_a_file_both_sections_are_omitted(tmp_path):
    out = await build(tmp_path, None, "plain")
    for path in out.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert 'id="disclosures"' not in text, path
        assert 'id="market-disclosures"' not in text, path
    assert not (out / "data" / "disclosures.json").exists()


async def test_file_with_no_items_for_a_company_omits_its_section(tmp_path):
    out = await build(tmp_path, load_disclosures(write(tmp_path, payload(items=[ITEMS[0]]))), "one")
    assert section(read(out, "c", "005930", "index.html"), "disclosures")
    assert not section(read(out, "c", "105560", "index.html"), "disclosures")
    # CRITICAL 이 하나도 없으면 첫 화면 섹션도 없다
    assert not section(read(out, "index.html"), "market-disclosures")


# ── 첫 화면 ─────────────────────────────────────────────────────────


async def test_landing_lists_only_market_wide_kinds_newest_first_collapsed(out):
    block = section(read(out, "index.html"), "market-disclosures")
    assert block
    assert "회생절차개시신청" in block
    # 같은 사건은 접수번호가 빠른 것 하나만
    assert "주권매매거래정지" in block
    assert "기타시장안내" not in block
    # CRITICAL 이 아닌 유형은 없다
    for title in ("유상증자결정", "소유상황보고서", "감사보고서제출"):
        assert title not in block
    # 날짜 내림차순
    assert block.index("회생절차개시신청") < block.index("주권매매거래정지")
    # 페이지가 있는 회사는 링크, 없는 회사는 이름만
    assert 'href="./c/028300/"' in block
    assert "없는회사" in block and 'href="./c/999990/"' not in block
    assert 'href="./learn/disclosures/#listing_status"' in block
    assert 'href="./feeds/disclosures.xml"' in block


def test_market_wide_definition_is_the_alert_channels():
    assert {k for k in RiskKind if is_market_wide(k)} == {RiskKind.DISTRESS, RiskKind.LISTING_STATUS}


# ── 읽기·검증 ───────────────────────────────────────────────────────


def test_loader_rejects_another_format_version(tmp_path):
    with pytest.raises(DisclosureFormatError):
        load_disclosures(write(tmp_path, payload(format_version=FORMAT_VERSION + 1)))


def test_loader_drops_malformed_items_and_never_trusts_the_url_field(tmp_path):
    bad = [
        entry("20261120000001", "주요사항보고서(유상증자결정)", "capital_raise", url="javascript:alert(1)"),
        entry("2026112", "짧은 접수번호", "capital_raise"),
        entry("20261120000003", "형식 밖 종목코드", "capital_raise", stock_code="../x"),
        entry("20261120000004", "모르는 유형", "no_such_kind"),
    ]
    feed = load_disclosures(write(tmp_path, payload(items=bad)))
    assert [i.rcept_no for i in feed.items] == ["20261120000001"]
    assert feed.items[0].url == "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261120000001"
    assert feed.dropped == 3


async def test_truncated_types_are_disclosed(tmp_path):
    feed = load_disclosures(write(tmp_path, payload(truncated_types=["D"])))
    out = await build(tmp_path, feed, "trunc")
    assert "빠진 공시가 있을 수 있습니다" in section(read(out, "c", "005930", "index.html"), "disclosures")


async def test_raw_list_is_published_for_scripts_and_the_site_passes_every_guard(out):
    doc = json.loads(read(out, "data", "disclosures.json"))
    assert doc["format_version"] == FORMAT_VERSION
    assert doc["disclaimer"] == DISCLAIMER
    assert [i["rcept_no"] for i in doc["items"]][0] == "20261121000020"
    assert check_site(out) == []


def test_cli_build_takes_a_disclosures_file(tmp_path, monkeypatch, capsys):
    db = tmp_path / "cli.duckdb"
    with Cache(db) as c:
        seed_site_cache(c)
    monkeypatch.setattr(settings, "fin_checkup_db_path", db)
    src = write(tmp_path, payload())
    out = tmp_path / "site-out"
    assert main(["site", "build", "--year", "2024", "--out", str(out), "--disclosures", str(src)]) == 0
    assert 'id="disclosures"' in read(out, "c", "005930", "index.html")
    assert "공시" in capsys.readouterr().out


def test_cli_build_goes_on_without_disclosures_when_the_file_is_missing_or_broken(
    tmp_path, monkeypatch, capsys
):
    """공시는 덤이다 — 못 읽으면 알리고 공시 섹션 없이 만든다 (피드 레인과 같은 약속)."""
    db = tmp_path / "cli.duckdb"
    with Cache(db) as c:
        seed_site_cache(c)
    monkeypatch.setattr(settings, "fin_checkup_db_path", db)
    out = tmp_path / "site-out"
    args = ["site", "build", "--year", "2024", "--out", str(out), "--no-images", "--disclosures"]
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    for path in (tmp_path / "nope.json", broken):
        assert main([*args, str(path)]) == 0
        assert "공시 없이 만듭니다" in capsys.readouterr().out
        assert 'id="disclosures"' not in read(out, "c", "005930", "index.html")
