"""'최근 위험 공시' — `cli disclosures fetch` 가 쓴 JSON(`fin_checkup.disclosures`)을 사이트가 읽는 쪽.

    uv run python -m fin_checkup.cli site build --disclosures _site-data/disclosures.json

파일을 넘기지 않으면 `Site.disclosures` 가 None 이고, 회사 페이지·첫 화면의 공시 섹션은 아예 생기지 않는다.

싣는 건 **사실만**: 언제(접수일) · 어느 회사가 · 어떤 제목의 공시를 냈고 · 분류기가 어느 유형으로 봤는지 ·
DART 원문 링크 · 유형 해설(`/learn/disclosures/#<유형>`). 해석·권유 문장은 없다.

파일은 Actions 가 만든 것이지만 그래도 검증한다 — 형식 버전이 다르면 멈추고(`DisclosureFormatError`),
항목 하나가 형식 밖이면(접수번호·종목코드·유형) 그 항목만 뺀다. 원문 링크는 파일의 `url` 을 믿지 않고
접수번호로 다시 만든다 (`models.Disclosure.url` 과 같은 주소).

첫 화면 목록의 기준(시장 전체로 올리는 유형, 같은 사건 묶기)은 알림 채널과 같다 — `alerts.classify` 의
`is_market_wide` · `same_event_key`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from fin_checkup.alerts.classify import RiskKind, is_market_wide, same_event_key
from fin_checkup.disclaimer import DISCLAIMER
from fin_checkup.disclosures import FORMAT_VERSION, read_json
from fin_checkup.models import Disclosure

#: 회사 페이지에 보이는 최대 건수 (최근 것부터). 넘으면 몇 건 더 있는지 적는다.
COMPANY_LIMIT = 10
#: 첫 화면 목록의 최대 건수.
MARKET_LIMIT = 20

_RCEPT_NO = re.compile(r"^\d{14}$")
_YMD = re.compile(r"^\d{8}$")
_STOCK_CODE = re.compile(r"^[0-9A-Z]{6}$")


class DisclosureFormatError(ValueError):
    """공시 JSON 을 읽을 수 없다 (형식 버전이 다르거나 JSON 이 아니다)."""


def _ymd(value: str) -> date:
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


@dataclass(frozen=True)
class DisclosureItem:
    rcept_no: str
    rcept_dt: date
    corp_code: str
    stock_code: str
    corp_name: str
    report_nm: str
    kind: RiskKind
    #: [기재정정] 등 앞서 낸 공시를 고친 것.
    is_correction: bool = False

    @property
    def label(self) -> str:
        return self.kind.label

    @property
    def url(self) -> str:
        return Disclosure(
            rcept_no=self.rcept_no, corp_code=self.corp_code, corp_name=self.corp_name, report_nm=""
        ).url

    @property
    def explainer_path(self) -> str:
        """유형 해설 (`/learn/disclosures/` 의 앵커는 RiskKind 값)."""
        return f"learn/disclosures/#{self.kind.value}"

    @property
    def company_path(self) -> str:
        return f"c/{self.stock_code}/"


def _item(raw: Any) -> DisclosureItem | None:
    if not isinstance(raw, dict):
        return None
    rcept_no = str(raw.get("rcept_no", ""))
    rcept_dt = str(raw.get("rcept_dt", ""))
    stock_code = str(raw.get("stock_code", ""))
    if not (_RCEPT_NO.match(rcept_no) and _YMD.match(rcept_dt) and _STOCK_CODE.match(stock_code)):
        return None
    try:
        kind = RiskKind(raw.get("category"))
        when = _ymd(rcept_dt)
    except ValueError:
        return None
    name, title = str(raw.get("corp_name", "")).strip(), str(raw.get("report_nm", "")).strip()
    if not name or not title:
        return None
    return DisclosureItem(
        rcept_no=rcept_no,
        rcept_dt=when,
        corp_code=str(raw.get("corp_code", "")),
        stock_code=stock_code,
        corp_name=name,
        report_nm=title,
        kind=kind,
        is_correction=raw.get("is_correction") is True,
    )


@dataclass(frozen=True)
class DisclosureFeed:
    begin: date
    end: date
    generated_at: str
    #: 페이지 상한에 걸려 빠진 공시가 있을 수 있는 공시유형(DART pblntf_ty).
    truncated_types: tuple[str, ...]
    #: 최근 것부터 (접수일, 접수번호 내림차순).
    items: tuple[DisclosureItem, ...]
    #: 형식 밖이라 뺀 항목 수.
    dropped: int = 0
    #: `/data/disclosures.json` 으로 다시 싣는 문서 — 원본에서 검증을 통과한 항목만, 원문 링크는 다시 만든 것.
    public: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def truncated(self) -> bool:
        return bool(self.truncated_types)

    def for_company(self, stock_code: str) -> list[DisclosureItem]:
        return [i for i in self.items if i.stock_code == stock_code]

    def market_wide(self) -> list[DisclosureItem]:
        """시장 전체로 올리는 유형만, 같은 사건은 접수번호가 빠른 것 하나로 — 알림 채널과 같은 기준."""
        leaders: dict[tuple[str, str, str], DisclosureItem] = {}
        for item in sorted(self.items, key=lambda i: i.rcept_no):
            if is_market_wide(item.kind):
                key = same_event_key(item.corp_code or item.stock_code, item.rcept_dt.isoformat(), item.kind)
                leaders.setdefault(key, item)
        return sorted(leaders.values(), key=lambda i: (i.rcept_dt, i.rcept_no), reverse=True)


def load_disclosures(path: Path | str) -> DisclosureFeed:
    """파일을 읽어 검증한다. 읽을 수 없거나 형식 버전이 다르면 `DisclosureFormatError`."""
    try:
        doc = read_json(path)  # 형식 버전·items 확인은 쓰는 쪽(fin_checkup.disclosures)과 같은 함수로
    except (OSError, ValueError) as exc:
        raise DisclosureFormatError(f"공시 JSON 을 읽지 못했다: {path} ({exc})") from exc
    return feed_from_payload(doc)


def as_feed(value: DisclosureFeed | dict | None) -> DisclosureFeed | None:
    """`build_site(disclosures=…)` 가 받는 것 — 이미 읽은 피드, `read_json` 결과 dict, 또는 None."""
    if value is None or isinstance(value, DisclosureFeed):
        return value
    return feed_from_payload(value)


def feed_from_payload(doc: dict) -> DisclosureFeed:
    """`disclosures fetch` 가 쓴 문서 → 검증한 피드. 형식 버전·조회 기간이 틀리면 `DisclosureFormatError`."""
    if not isinstance(doc, dict) or doc.get("format_version") != FORMAT_VERSION:
        got = doc.get("format_version") if isinstance(doc, dict) else type(doc).__name__
        raise DisclosureFormatError(f"공시 JSON 형식 버전 {got} — 이 빌더는 {FORMAT_VERSION} 만 읽는다")
    try:
        begin, end = _ymd(str(doc["bgn_de"])), _ymd(str(doc["end_de"]))
    except (KeyError, ValueError) as exc:
        raise DisclosureFormatError(f"공시 JSON 의 조회 기간(bgn_de·end_de)이 없다: {exc}") from exc

    raws = doc.get("items") or []
    pairs = [(i, r) for i, r in ((_item(r), r) for r in raws) if i is not None]
    pairs.sort(key=lambda p: (p[0].rcept_dt, p[0].rcept_no), reverse=True)
    items = [i for i, _ in pairs]
    public = {
        **doc,
        "disclaimer": DISCLAIMER,
        "count": len(items),
        "items": [{**r, "url": i.url} for i, r in pairs],
    }
    return DisclosureFeed(
        begin=begin,
        end=end,
        generated_at=str(doc.get("generated_at", "")),
        truncated_types=tuple(str(t) for t in doc.get("truncated_types") or ()),
        items=tuple(items),
        dropped=len(raws) - len(items),
        public=public,
    )
