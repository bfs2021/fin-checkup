"""시장 전체의 최근 위험 공시를 모아 JSON 파일로 쓴다 (사이트의 '최근 위험 공시' 재료).

알림 워커와 같은 수집(공시유형별 기간 조회 + `alerts.classify`)을 쓰되, 관심종목·발송 기록과
무관하게 상장사 전체를 본다. 파일에는 **사실만** 담는다 — 어느 회사가 언제 어떤 제목의 공시를
냈고 분류기가 어느 유형으로 봤는지, 그리고 DART 원문 링크. 해석·권유 문장은 넣지 않는다.

호출 수는 공시유형 수 × 페이지 수다. 페이지 상한에 걸린 유형은 `truncated_types` 에 적는다 —
빠진 공시가 있을 수 있다는 사실을 숨기지 않는다.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path

from fin_checkup.alerts.classify import classify
from fin_checkup.alerts.worker import WATCH_TYPES
from fin_checkup.clock import kst_now, kst_today
from fin_checkup.dart.client import DartClient

logger = logging.getLogger(__name__)

#: 출력 JSON 형식 버전. 필드를 바꾸면 올린다 (사이트 빌더가 읽는다).
FORMAT_VERSION = 1
#: corp_code 없이 조회하면 DART 는 3개월까지만 준다.
MAX_DAYS = 90
#: 유형 하나당 따라갈 최대 페이지(페이지당 100건). 실측 위험 공시는 하루 ~145건이라 7일은 여유가 있다.
DEFAULT_MAX_PAGES = 50
#: 유가(Y)·코스닥(K)·코넥스(N). 사이트는 상장사 페이지만 만든다.
LISTED_CORP_CLS = frozenset({"Y", "K", "N"})


def worst_case_calls(max_pages: int = DEFAULT_MAX_PAGES) -> int:
    """한 번 실행이 쓸 수 있는 최대 호출 수. 예산 확인은 이 값으로 한다."""
    return len(WATCH_TYPES) * max_pages


async def fetch_recent_risks(
    client: DartClient,
    days: int = 7,
    today: date | None = None,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> dict:
    """최근 `days` 일(KST, 오늘 포함)의 상장사 위험 공시. `RateLimitExceeded` 는 그대로 올린다."""
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"days 는 1~{MAX_DAYS} 사이여야 한다 (받은 값 {days})")
    end = today or kst_today()
    begin = end - timedelta(days=days - 1)
    bgn_de, end_de = begin.strftime("%Y%m%d"), end.strftime("%Y%m%d")

    seen: dict[str, dict] = {}
    truncated: list[str] = []
    for pblntf_ty in WATCH_TYPES:
        found = await client.search_disclosures(
            bgn_de=bgn_de, end_de=end_de, pblntf_ty=pblntf_ty, max_pages=max_pages
        )
        if client.last_search_truncated:
            truncated.append(pblntf_ty.value)
        for disclosure in found:
            if disclosure.corp_cls not in LISTED_CORP_CLS or disclosure.rcept_no in seen:
                continue
            risk = classify(disclosure)
            if risk is None:
                continue
            seen[disclosure.rcept_no] = {
                "corp_code": disclosure.corp_code,
                "stock_code": disclosure.stock_code,
                "corp_name": disclosure.corp_name,
                "report_nm": disclosure.report_nm,
                "rcept_dt": disclosure.rcept_dt,
                "rcept_no": disclosure.rcept_no,
                "category": risk.kind.value,
                "category_label": risk.kind.label,
                "severity": risk.severity.value,
                "is_correction": risk.is_correction,
                "url": disclosure.url,
            }

    items = sorted(seen.values(), key=lambda i: (i["rcept_dt"], i["rcept_no"]), reverse=True)
    if truncated:
        logger.warning("[disclosures] 페이지 상한에 걸린 공시유형: %s — 빠진 공시가 있을 수 있다", truncated)
    return {
        "format_version": FORMAT_VERSION,
        "generated_at": kst_now().isoformat(timespec="seconds"),
        "source": "DART 공시검색(list.json) · opendart.fss.or.kr",
        "scope": "유가증권·코스닥·코넥스 상장사, 제목 기준 위험 공시 분류(alerts/classify.py)",
        "bgn_de": bgn_de,
        "end_de": end_de,
        "days": days,
        "truncated_types": truncated,
        "count": len(items),
        "items": items,
    }


def write_json(payload: dict, path: Path | str) -> None:
    """임시 파일에 쓰고 바꿔 끼운다 — 도중에 죽어도 지난 파일이 반쯤 덮이지 않는다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path | str) -> dict:
    """`write_json` 이 쓴 파일을 읽는다. 형식 버전이 다르면 ValueError — 필드 뜻이 달라졌을 수 있다."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("format_version") != FORMAT_VERSION:
        raise ValueError(f"{path}: 공시 JSON 형식 버전이 {FORMAT_VERSION} 이 아니다")
    if not isinstance(payload.get("items"), list):
        raise ValueError(f"{path}: items 가 없다")
    return payload
