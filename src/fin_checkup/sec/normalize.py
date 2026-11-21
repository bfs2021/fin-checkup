"""US-GAAP companyfacts → Financials.

두 가지가 까다롭다.

1. 한 번의 10-K 공시(fy=2023)에 **전년도 값이 함께 들어 있다.** Apple의 FY2023
   10-K에는 end=2022-09-24와 end=2023-09-30이 모두 담긴다. 그래서 fy로 고르면
   안 되고 회계연도 종료일(end)로 골라야 한다.

2. 손익·현금흐름 항목에는 분기 값도 섞여 있다. start~end 기간이 1년에 가까운
   것만 연간으로 인정한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from fin_checkup.models import Financials, FsDiv, InterestSource, ReceivableSource, ReportCode

#: 이 일수 이상이어야 연간 값으로 본다. 분기(약 90일)를 걸러내기 위한 것.
MIN_ANNUAL_DAYS = 300


@dataclass(frozen=True)
class TagSpec:
    field: str
    #: 우선순위 순서. 앞에 있는 태그가 먼저 잡힌다.
    tags: tuple[str, ...]
    #: 손익·현금흐름처럼 기간 값이면 True, 재무상태표처럼 시점 값이면 False.
    is_flow: bool
    #: 현금 유출이 음수로 잡히는 항목은 절댓값으로.
    absolute: bool = False


TAG_SPECS: tuple[TagSpec, ...] = (
    # 재무상태표 (시점)
    TagSpec("total_assets", ("Assets",), False),
    TagSpec("total_liabilities", ("Liabilities",), False),
    TagSpec(
        "total_equity",
        ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
        False,
    ),
    TagSpec("current_assets", ("AssetsCurrent",), False),
    TagSpec("current_liabilities", ("LiabilitiesCurrent",), False),
    TagSpec("inventories", ("InventoryNet",), False),
    # 매출채권: AccountsReceivableNetCurrent(순수) → ReceivablesNetCurrent(미수금 포함 합계).
    # 어느 쪽인지 trade_receivables_source 에 남긴다(아래 RECEIVABLE_TAG_SOURCE).
    TagSpec(
        "trade_receivables",
        ("AccountsReceivableNetCurrent", "ReceivablesNetCurrent"),
        False,
    ),
    # 손익계산서 (기간)
    TagSpec(
        "revenue",
        (
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
        ),
        True,
    ),
    TagSpec("operating_income", ("OperatingIncomeLoss",), True),
    TagSpec("net_income", ("NetIncomeLoss", "ProfitLoss"), True),
    # 이자비용은 총액 태그만 여기서 찾는다. 없을 때의 대체 순서는 _interest_expense 가 맡는다.
    # InterestExpenseNonoperating 은 2024 택소노미부터 InterestExpense 를 대신해 늘었다
    # (frames CY2023 158곳 → CY2024 456곳, 같은 기간 InterestExpense 3,612 → 1,341).
    TagSpec(
        "interest_expense",
        ("InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"),
        True,
        absolute=True,
    ),
    # 현금흐름표 (기간)
    TagSpec(
        "operating_cash_flow",
        (
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ),
        True,
    ),
    TagSpec(
        "capex",
        (
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsToAcquireProductiveAssets",
        ),
        True,
        absolute=True,
    ),
)

#: 자본금(capital_stock)은 채우지 않는다. 한국의 자본잠식률은 상법·거래소 규정에
#: 묶인 개념이라 US-GAAP의 CommonStockValue와 대응하지 않는다. 억지로 맞추면
#: 미국 기업에 엉뚱한 "자본잠식" 딱지가 붙는다.


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


#: 현금흐름표 보충 공시의 이자 지급액(자본화 이자 제외). DART 의 '이자의 지급' 에 해당한다.
INTEREST_PAID_TAG = "InterestPaidNet"
#: 순이자(이자수익 − 이자비용). 양수면 순수익, 음수면 순비용이다. 비용 자리에는 음수일 때만
#: 절대값으로 쓰고, 그것도 대체값으로만 둔다 — 이자수익만큼 분모가 작아져 배율이 부풀려진다.
#: frames CY2023 에서 총액과 순액을 함께 낸 135곳 중 순액이 총액의 80% 미만인 곳이 24% 였다.
NET_INTEREST_TAG = "InterestIncomeExpenseNet"


#: 매출채권 태그 → 출처. ReceivablesNetCurrent 는 매출채권 외 채권까지 묶은 합계다.
RECEIVABLE_TAG_SOURCE = {
    "AccountsReceivableNetCurrent": ReceivableSource.TRADE,
    "ReceivablesNetCurrent": ReceivableSource.TRADE_AND_OTHER,
}


def _is_annual_form(entry: dict) -> bool:
    return str(entry.get("form", "")).startswith("10-K")


#: 결산일이 이 날짜 이전의 1월이면 전년도 회계연도로 본다. 52/53주 결산 기업은 토요일에
#: 마감해 12월 31일을 며칠 넘기기도 한다(FY2021 이 2022-01-01 에 끝나는 식).
EARLY_JANUARY_CUTOFF_DAY = 7


def _fiscal_year_of(end: date) -> int:
    if end.month == 1 and end.day <= EARLY_JANUARY_CUTOFF_DAY:
        return end.year - 1
    return end.year


def _pick(units: list[dict], fiscal_year: int, is_flow: bool) -> float | None:
    """해당 회계연도의 연간 값 하나를 고른다."""
    candidates: list[dict] = []
    for entry in units:
        if not _is_annual_form(entry):
            continue
        end = _parse_date(entry.get("end"))
        if end is None or _fiscal_year_of(end) != fiscal_year:
            continue
        if is_flow:
            start = _parse_date(entry.get("start"))
            if start is None or (end - start).days < MIN_ANNUAL_DAYS:
                continue
        if not isinstance(entry.get("val"), int | float):
            continue
        candidates.append(entry)

    if not candidates:
        return None

    # 정정 공시가 있으면 나중에 제출된 것을 쓴다.
    candidates.sort(key=lambda e: (str(e.get("filed", "")), str(e.get("end", ""))))
    return float(candidates[-1]["val"])


def _pick_tag(us_gaap: dict, tag: str, fiscal_year: int, is_flow: bool) -> float | None:
    units = us_gaap.get(tag, {}).get("units", {}).get("USD")
    return _pick(units, fiscal_year, is_flow) if units else None


def _interest_expense(
    us_gaap: dict, fiscal_year: int, gross: float | None
) -> tuple[float | None, InterestSource | None]:
    """이자비용과 그 출처: 총액 태그 → 이자 지급액(InterestPaidNet) → 순이자비용(대체값).

    DART 와 같은 순서다. 지급 0 은 무차입의 증거가 아니라 다음으로 내려가고, 순액 0 은
    '이자비용 = 이자수익' 이라 이자가 없다는 뜻이 아니어서 쓰지 않는다.
    """
    if gross is not None:
        return gross, InterestSource.INCOME_STATEMENT
    paid = _pick_tag(us_gaap, INTEREST_PAID_TAG, fiscal_year, True)
    if paid is not None and paid != 0:
        return abs(paid), InterestSource.CASH_FLOW
    net = _pick_tag(us_gaap, NET_INTEREST_TAG, fiscal_year, True)
    if net is not None and net < 0:
        return -net, InterestSource.NET_INTEREST
    return None, None


def normalize_company_facts(
    facts: dict,
    fiscal_year: int,
    cik: str = "",
) -> Financials | None:
    """companyfacts 응답에서 한 회계연도를 뽑아 Financials로.

    필요한 계정을 하나도 못 찾으면 None (그 해 10-K가 없다는 뜻).
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    if not us_gaap:
        return None

    values: dict[str, float | None] = {}
    matched: dict[str, str] = {}
    for spec in TAG_SPECS:
        picked: float | None = None
        for tag in spec.tags:
            if (picked := _pick_tag(us_gaap, tag, fiscal_year, spec.is_flow)) is not None:
                matched[spec.field] = tag
                break
        values[spec.field] = abs(picked) if (picked is not None and spec.absolute) else picked
    values["interest_expense"], source = _interest_expense(us_gaap, fiscal_year, values["interest_expense"])

    if all(v is None for v in values.values()):
        return None

    return Financials(
        corp_code=cik or str(facts.get("cik", "")),
        bsns_year=fiscal_year,
        # 미장에는 DART의 보고서 코드·연결구분 개념이 없다. 10-K는 연간·연결이라
        # 가장 가까운 값으로 채운다.
        reprt_code=ReportCode.ANNUAL,
        fs_div=FsDiv.CFS,
        currency="USD",
        interest_expense_source=source,
        trade_receivables_source=RECEIVABLE_TAG_SOURCE.get(matched.get("trade_receivables", "")),
        **values,
    )
