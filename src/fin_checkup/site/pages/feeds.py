"""Atom 피드 — `/feeds/c/<종목코드>.xml` (회사별) · `/feeds/disclosures.xml` (시장 전체, 심각 공시만).

텔레그램 없이 받아 보는 길이다. RSS 리더·Slack/Discord 의 RSS 앱이 이 주소를 구독한다(/watch/ 에 안내).

회사 피드의 항목
- 사업연도마다 하나: 그해 신호 개수. 날짜는 **사업보고서 법정 제출 기한**(사업연도 종료 후 90일, `season`) —
  캐시에 실제 공시일이 없어서다. 본문에 그 사실을 적는다.
- 직전 사업연도와 신호가 달라진 지표가 있으면 하나: "부채비율: 🟡 주의 → 🔴 위험" (방향과 무관하게 전부,
  ⚫ 가 낀 변화는 뺀다 — 비교할 해·계정이 없어서 생긴 것이지 값이 바뀐 게 아니다).
- `--disclosures` JSON 에 그 회사의 위험 공시가 있으면 공시마다 하나 (날짜 = 접수일, 링크 = DART 원문).

id 는 `urn:uuid:` + uuid5(URL 이름공간, `fin-checkup:<이름>`) 다. 이름은 내용의 정체(`c/005930/fy/2024`,
`dart/<접수번호>`)라 빌드 날짜·`--base-url` 이 바뀌어도 같다 — 리더가 같은 항목을 두 번 보여 주지 않는다.
`updated` 도 데이터에서만 온다(빌드 날짜 아님). 공시가 없는 시장 피드만 예외로 빌드 날짜를 쓴다.
"""

from __future__ import annotations

import re
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

from fin_checkup.disclaimer import DISCLAIMER
from fin_checkup.metrics.engine import CheckupResult, checkup
from fin_checkup.metrics.signals import Signal
from fin_checkup.models import Financials, FsDiv
from fin_checkup.presentation import summary_chips
from fin_checkup.site.context import CompanyEntry, Site, root_for
from fin_checkup.site.registry import Output, page
from fin_checkup.site.season import filings_of

ATOM = "http://www.w3.org/2005/Atom"
ET.register_namespace("", ATOM)

MARKET_FEED = "feeds/disclosures.xml"
#: 시장 전체 피드에 싣는 공시 강도 (`alerts.classify.Severity`).
MARKET_SEVERITY = "critical"
DART_URL = re.compile(r"^https://dart\.fss\.or\.kr/")
#: XML 1.0 에 들어갈 수 없는 제어 문자. 공시 제목에 섞여 오면 피드 전체가 깨진다.
_XML_INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
SOURCE = "출처: 금융감독원 전자공시시스템(DART)."


def company_feed_path(stock_code: str) -> str:
    return f"feeds/c/{stock_code}.xml"


def feed_id(name: str) -> str:
    """내용의 정체에서 만든 안정된 id. 주소·빌드 날짜와 무관하다."""
    return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, 'fin-checkup:' + name)}"


def _clean(text: str) -> str:
    return _XML_INVALID.sub("", text)


def _stamp(day: date) -> str:
    return f"{day.isoformat()}T00:00:00+09:00"


@dataclass(frozen=True)
class FeedEntry:
    name: str
    title: str
    updated: date
    content: str
    link: str | None = None

    @property
    def id(self) -> str:
        return feed_id(self.name)


def _href(site: Site, feed_path: str, target: str) -> str:
    """피드 안의 링크. 절대 base 가 없으면 피드 파일 기준 상대경로 — `/c/…` 는 하위 경로 사이트에서 틀린다."""
    if site.has_absolute_base:
        return site.absolute_url(target)
    return root_for(feed_path) + target


def _dart_day(rcept_dt: str) -> date | None:
    try:
        return date(int(rcept_dt[:4]), int(rcept_dt[4:6]), int(rcept_dt[6:8]))
    except (TypeError, ValueError):
        return None


# ── 회사 ──────────────────────────────────────────────────────────


def year_results(entry: CompanyEntry) -> list[tuple[Financials, CheckupResult]]:
    """캐시에 있는 사업연도마다 판정 결과. 최신 해는 페이지와 같은 결과, 그 앞은 같은 업종으로 다시 계산."""
    data = entry.checkup
    by_year = {f.bsns_year: f for f in data.history}
    sector = data.result.sector
    out: list[tuple[Financials, CheckupResult]] = []
    for fin in data.history:
        if fin is data.history[-1]:
            out.append((fin, data.result))
        else:
            out.append((fin, checkup(fin, by_year.get(fin.bsns_year - 1), sector=sector)))
    return out


def _chips_text(result: CheckupResult) -> str:
    return " · ".join(f"{s.label} {n}" for s, n in summary_chips(result))


def company_entries(entry: CompanyEntry, site: Site) -> list[FeedEntry]:
    code, name = entry.stock_code, entry.name
    feed_path = company_feed_path(code)
    page_link = _href(site, feed_path, entry.path)
    entries: list[FeedEntry] = []
    by_year: dict[int, CheckupResult] = {}
    for fin, result in year_results(entry):
        year = fin.bsns_year
        by_year[year] = result
        due = filings_of(year)[-1].due
        statement = "연결재무제표" if fin.fs_div is FsDiv.CFS else "개별재무제표"
        entries.append(
            FeedEntry(
                name=f"c/{code}/fy/{year}",
                title=f"{name} {year} 사업연도 재무 신호등",
                updated=due,
                link=page_link,
                content=(
                    f"{year}년 {fin.reprt_code.label} · {statement} 기준 지표 {len(result.metrics)}개: "
                    f"{_chips_text(result)}.\n"
                    "지표마다 계산식과 경계값은 회사 페이지에 있습니다.\n"
                    f"날짜({due.isoformat()})는 사업보고서 법정 제출 기한(사업연도 종료 후 90일)이며 "
                    "실제 공시일과 다를 수 있습니다."
                ),
            )
        )
        prior = by_year.get(year - 1)
        if prior is None:
            continue
        before = {m.key: m.signal for m in prior.metrics}
        lines = [
            f"{m.label}: {before[m.key].emoji} {before[m.key].label} → {m.signal.emoji} {m.signal.label}"
            for m in result.metrics
            if m.key in before
            and before[m.key] is not m.signal
            and Signal.UNKNOWN not in (before[m.key], m.signal)
        ]
        if lines:
            entries.append(
                FeedEntry(
                    name=f"c/{code}/fy/{year}/signals",
                    title=f"{name} {year - 1}→{year} 사업연도 신호가 바뀐 지표 {len(lines)}개",
                    updated=due,
                    link=page_link,
                    content="\n".join(lines) + "\n같은 업종 기준으로 두 해를 각각 판정해 견준 결과입니다. "
                    "⚫(데이터 없음)이 낀 변화는 값이 바뀐 게 아니라 "
                    "비교할 해가 없거나 계정을 못 찾은 것이라 뺐습니다.",
                )
            )
    entries += [e for d in _company_disclosures(site, code) if (e := _disclosure_entry(d))]
    return entries


def _company_disclosures(site: Site, code: str) -> list[dict]:
    if not site.disclosures:
        return []
    return [d for d in site.disclosures["items"] if isinstance(d, dict) and d.get("stock_code") == code]


def _disclosure_entry(d: dict, with_company: bool = False) -> FeedEntry | None:
    day = _dart_day(str(d.get("rcept_dt", "")))
    rcept_no = str(d.get("rcept_no", ""))
    if day is None or not rcept_no.isdigit():
        return None
    url = str(d.get("url", ""))
    url = url if DART_URL.match(url) else None
    category = str(d.get("category_label", ""))
    title = str(d.get("report_nm", ""))
    corp = str(d.get("corp_name", ""))
    heading = f"[{category}] {corp} — {title}" if with_company else f"[{category}] {title}"
    correction = " (정정 공시)" if d.get("is_correction") else ""
    return FeedEntry(
        name=f"dart/{rcept_no}",
        title=heading,
        updated=day,
        link=url,
        content=(
            f"{corp} · 접수일 {day.isoformat()} · 분류 {category}{correction}\n"
            "분류는 공시 제목으로 자동으로 매긴 것입니다. 내용은 DART 원문에서 확인하세요."
            + (f"\n원문: {url}" if url else "")
        ),
    )


# ── Atom ──────────────────────────────────────────────────────────


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    node = ET.SubElement(parent, f"{{{ATOM}}}{tag}", attrs)
    if text is not None:
        node.text = _clean(text)
    return node


def atom_feed(
    *,
    name: str,
    title: str,
    subtitle: str,
    self_href: str,
    alternate: str | None,
    entries: list[FeedEntry],
    fallback_updated: date,
) -> str:
    ordered = sorted(entries, key=lambda e: (e.updated, e.name), reverse=True)
    feed = ET.Element(f"{{{ATOM}}}feed")
    _sub(feed, "id", feed_id(name))
    _sub(feed, "title", title)
    _sub(feed, "subtitle", subtitle)
    _sub(feed, "updated", _stamp(ordered[0].updated if ordered else fallback_updated))
    _sub(feed, "link", rel="self", type="application/atom+xml", href=self_href)
    if alternate:
        _sub(feed, "link", rel="alternate", type="text/html", href=alternate)
    author = _sub(feed, "author")
    _sub(author, "name", "fin-checkup")
    _sub(feed, "rights", DISCLAIMER)
    for e in ordered:
        node = _sub(feed, "entry")
        _sub(node, "id", e.id)
        _sub(node, "title", e.title)
        _sub(node, "updated", _stamp(e.updated))
        if e.link:
            _sub(node, "link", rel="alternate", href=e.link)
        _sub(node, "content", f"{e.content}\n\n{SOURCE} {DISCLAIMER}", type="text")
    ET.indent(feed, space=" ")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(feed, encoding="unicode") + "\n"


def company_feed(entry: CompanyEntry, site: Site) -> str:
    path = company_feed_path(entry.stock_code)
    return atom_feed(
        name=path.removesuffix(".xml"),
        title=f"{entry.name}({entry.stock_code}) 재무 신호등 · fin-checkup",
        subtitle=(
            "사업연도별 신호 개수, 직전 해와 달라진 신호, 최근 위험 공시. 측정값이며 투자 판단이 아닙니다."
        ),
        self_href=_href(site, path, path),
        alternate=_href(site, path, entry.path),
        entries=company_entries(entry, site),
        fallback_updated=site.built_on,
    )


def market_feed(site: Site) -> str:
    items = site.disclosures["items"] if site.disclosures else []
    picked = [d for d in items if isinstance(d, dict) and d.get("severity") == MARKET_SEVERITY]
    entries = [e for d in picked if (e := _disclosure_entry(d, with_company=True))]
    period = ""
    if site.disclosures:
        period = f" 수집 기간 {site.disclosures.get('bgn_de', '')}~{site.disclosures.get('end_de', '')}."
    return atom_feed(
        name="feeds/disclosures",
        title="상장사 위험 공시(심각) · fin-checkup",
        subtitle=(
            "유가증권·코스닥·코넥스 상장사의 최근 위험 공시 중 제목 기준 분류가 '심각' 인 것만."
            f"{period} 측정·분류 결과이며 투자 판단이 아닙니다."
        ),
        self_href=_href(site, MARKET_FEED, MARKET_FEED),
        alternate=_href(site, MARKET_FEED, ""),
        entries=entries,
        fallback_updated=site.built_on,
    )


@page("feeds")
def feed_files(site: Site) -> Iterator[Output]:
    for entry in site.companies:
        yield Output(company_feed_path(entry.stock_code), company_feed(entry, site))
    yield Output(MARKET_FEED, market_feed(site))
