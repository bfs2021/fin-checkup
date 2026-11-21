"""실제 숫자로 계산해 보기 — 한 회사의 공시 숫자를 계산식에 그대로 넣어 보인다.

지표 해설 페이지(`/m/<지표>/`)와 '재무제표 처음 읽기' 가 쓴다. 계산 과정만 보여 준다 — 결과가
좋다·나쁘다는 말을 붙이지 않는다. 결과 값은 다시 계산하지 않고 엔진(`metrics/engine.py`)이 낸
`Metric.value` 를 그대로 쓴다. 계산식에 넣는 숫자와 엔진 값이 어긋나지 않는지는
`tests/test_explain_worked.py` 가 지킨다.

UI 를 모른다. 회사를 고르는 규칙은 사이트 쪽(`site/examples.py`)에 있다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from fin_checkup.metrics.engine import MONEY, Metric
from fin_checkup.models import Financials, InterestSource

BALANCE = "재무상태표"
INCOME = "손익계산서"
CASH = "현금흐름표"

#: Financials 필드 → (화면 이름, 어느 표에 있나).
FIELDS: dict[str, tuple[str, str]] = {
    "revenue": ("매출액", INCOME),
    "operating_income": ("영업이익", INCOME),
    "net_income": ("당기순이익", INCOME),
    "interest_expense": ("이자비용", INCOME),
    "total_assets": ("자산총계", BALANCE),
    "total_liabilities": ("부채총계", BALANCE),
    "total_equity": ("자본총계(자기자본)", BALANCE),
    "current_assets": ("유동자산", BALANCE),
    "current_liabilities": ("유동부채", BALANCE),
    "inventories": ("재고자산", BALANCE),
    "trade_receivables": ("매출채권", BALANCE),
    "operating_cash_flow": ("영업활동현금흐름", CASH),
    "capex": ("유형자산의 취득", CASH),
}

Kind = Literal["ratio", "pct", "growth", "value", "minus"]


@dataclass(frozen=True)
class Recipe:
    """지표 하나를 어떤 숫자로 어떻게 계산하나. engine.METRIC_DEFS 와 1:1."""

    kind: Kind
    fields: tuple[str, ...]


RECIPES: dict[str, Recipe] = {
    "operating_margin": Recipe("pct", ("operating_income", "revenue")),
    "net_margin": Recipe("pct", ("net_income", "revenue")),
    "roe": Recipe("pct", ("net_income", "total_equity")),
    "roa": Recipe("pct", ("net_income", "total_assets")),
    "debt_ratio": Recipe("pct", ("total_liabilities", "total_equity")),
    "current_ratio": Recipe("pct", ("current_assets", "current_liabilities")),
    "interest_coverage": Recipe("ratio", ("operating_income", "interest_expense")),
    "equity_ratio": Recipe("pct", ("total_equity", "total_assets")),
    "revenue_growth": Recipe("growth", ("revenue",)),
    "operating_income_growth": Recipe("growth", ("operating_income",)),
    "net_income_growth": Recipe("growth", ("net_income",)),
    "operating_cash_flow": Recipe("value", ("operating_cash_flow",)),
    "ocf_to_net_income": Recipe("ratio", ("operating_cash_flow", "net_income")),
    "fcf": Recipe("minus", ("operating_cash_flow", "capex")),
    "asset_turnover": Recipe("ratio", ("revenue", "total_assets")),
    "inventory_turnover": Recipe("ratio", ("revenue", "inventories")),
    "receivable_turnover": Recipe("ratio", ("revenue", "trade_receivables")),
}

#: 이자비용 출처별 계정 이름 (models.InterestSource).
_INTEREST_LABELS = {
    InterestSource.INCOME_STATEMENT: "이자비용",
    InterestSource.CASH_FLOW: "이자의 지급",
    InterestSource.FINANCE_COSTS: "금융원가(이자비용 대신 쓴 값)",
}

#: 금액을 억 단위로 줄였다는 안내. 계산은 공시 원래 숫자로 한다.
ROUNDING_NOTE = "금액은 읽기 쉽게 억 원 단위로 반올림해 적었어요. 계산은 공시된 원래 숫자로 했어요."


@dataclass(frozen=True)
class Input:
    label: str
    #: 이 숫자가 실린 표 (재무상태표·손익계산서·현금흐름표).
    statement: str
    year: int
    value: float
    text: str


@dataclass(frozen=True)
class WorkedExample:
    key: str
    year: int
    inputs: tuple[Input, ...]
    #: 숫자를 넣은 계산식 ("65,670억원 ÷ 3,008,709억원 × 100").
    expression: str
    #: 엔진이 낸 값 ("2.18%").
    result_text: str


def money_text(value: float, currency: str = "KRW") -> str:
    """계산 과정용 금액. 원화는 억 원 단위(쉼표), 1억 미만은 원 단위. 다른 통화는 원래 숫자."""
    if currency != "KRW":
        symbol = "$" if currency == "USD" else f"{currency} "
        return f"{symbol}{value:,.0f}"
    if abs(value) >= 1e8:
        return f"{value / 1e8:,.0f}억원"
    return f"{value:,.0f}원"


def result_text(metric: Metric, currency: str = "KRW") -> str:
    assert metric.value is not None
    if metric.unit == MONEY:
        return money_text(metric.value, currency)
    return f"{metric.value:,.2f}{metric.unit}"


def _prior(history: Sequence[Financials], latest: Financials) -> Financials | None:
    # service.run 과 같은 규칙 — 바로 앞 사업연도만 '작년' 이다.
    return next((f for f in history if f.bsns_year == latest.bsns_year - 1), None)


def _label(field: str, fin: Financials) -> str:
    label, _ = FIELDS[field]
    if field == "interest_expense" and fin.interest_expense_source is not None:
        # 이자비용을 어느 계정에서 가져왔는지 그대로 적는다. 표 이름은 Input.statement 가 따로 말한다.
        return _INTEREST_LABELS[fin.interest_expense_source]
    return label


def _input(field: str, fin: Financials, currency: str) -> Input | None:
    value = getattr(fin, field)
    if value is None:
        return None
    _, statement = FIELDS[field]
    if field == "interest_expense" and fin.interest_expense_source is not None:
        statement = CASH if fin.interest_expense_source is InterestSource.CASH_FLOW else INCOME
    return Input(_label(field, fin), statement, fin.bsns_year, value, money_text(value, currency))


def worked_example(
    metric: Metric, history: Sequence[Financials], currency: str = "KRW"
) -> WorkedExample | None:
    """이 회사의 숫자로 계산 과정을 만든다. 엔진 값이 없거나(⚫·규칙 판정) 숫자가 모자라면 None."""
    if metric.value is None or not history:
        return None
    recipe = RECIPES[metric.key]
    latest = max(history, key=lambda f: f.bsns_year)

    if recipe.kind == "growth":
        prior = _prior(history, latest)
        if prior is None:
            return None
        (field,) = recipe.fields
        cur, old = _input(field, latest, currency), _input(field, prior, currency)
        if cur is None or old is None:
            return None
        inputs = (cur, old)
        expression = f"({cur.text} − {old.text}) ÷ {old.text} × 100"
    else:
        found = [_input(f, latest, currency) for f in recipe.fields]
        if any(i is None for i in found):
            return None
        inputs = tuple(i for i in found if i is not None)
        texts = [i.text for i in inputs]
        if recipe.kind == "value":
            expression = texts[0]
        elif recipe.kind == "minus":
            expression = f"{texts[0]} − {texts[1]}"
        elif recipe.kind == "pct":
            expression = f"{texts[0]} ÷ {texts[1]} × 100"
        else:
            expression = f"{texts[0]} ÷ {texts[1]}"

    return WorkedExample(
        key=metric.key,
        year=latest.bsns_year,
        inputs=inputs,
        expression=expression,
        result_text=result_text(metric, currency),
    )


def recompute(example: WorkedExample) -> float:
    """입력 숫자만으로 다시 계산한 값 — 테스트가 엔진 값과 견준다."""
    kind = RECIPES[example.key].kind
    values = [i.value for i in example.inputs]
    if kind == "value":
        return values[0]
    if kind == "minus":
        return values[0] - values[1]
    if kind == "growth":
        return (values[0] - values[1]) / values[1] * 100
    ratio = values[0] / values[1]
    return ratio * 100 if kind == "pct" else ratio
