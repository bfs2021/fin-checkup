"""실제 숫자로 계산해 보기 — 계산식에 넣은 숫자가 엔진 값과 같은 답을 내는지.

예시가 엔진과 다른 공식으로 계산하면, 해설 페이지의 답과 회사 페이지의 값이 어긋난다.
"""

from __future__ import annotations

import pytest

from fin_checkup.explain import banned
from fin_checkup.explain.worked import RECIPES, money_text, recompute, worked_example
from fin_checkup.metrics.engine import METRIC_DEFS, checkup
from fin_checkup.models import Financials, FsDiv, InterestSource, ReportCode

#: 판단을 담는 형용사 — 계산 과정에는 들어가면 안 된다.
EVALUATIVE = ("좋", "나쁘", "우수", "양호", "건전", "탄탄", "훌륭", "부진", "높은 편", "낮은 편", "위험")


def fin(year: int, **kwargs) -> Financials:
    base = dict(corp_code="00000000", bsns_year=year, reprt_code=ReportCode.ANNUAL, fs_div=FsDiv.CFS)
    return Financials(**{**base, **kwargs})


FULL = dict(
    revenue=3_008_709e8,
    operating_income=327_260e8,
    net_income=344_514e8,
    interest_expense=6_800e8,
    interest_expense_source=InterestSource.CASH_FLOW,
    total_assets=5_145_319e8,
    total_liabilities=1_123_399e8,
    total_equity=4_021_920e8,
    current_assets=2_270_623e8,
    current_liabilities=934_263e8,
    inventories=517_549e8,
    trade_receivables=431_465e8,
    operating_cash_flow=729_826e8,
    capex=536_197e8,
)
HISTORY = [
    fin(2023, **{**FULL, "revenue": 2_589_355e8, "operating_income": 65_670e8, "net_income": 154_871e8}),
    fin(2024, **FULL),
]


def test_every_engine_metric_has_a_recipe():
    assert set(RECIPES) == {d.key for d in METRIC_DEFS}


@pytest.mark.parametrize("key", [d.key for d in METRIC_DEFS])
def test_inputs_reproduce_the_engine_value(key):
    result = checkup(HISTORY[1], HISTORY[0])
    metric = result.by_key(key)
    example = worked_example(metric, HISTORY)
    assert example is not None, key
    assert recompute(example) == pytest.approx(metric.value), key
    assert example.year == 2024


def test_growth_uses_this_year_and_last_year():
    metric = checkup(HISTORY[1], HISTORY[0]).by_key("revenue_growth")
    example = worked_example(metric, HISTORY)
    assert [i.year for i in example.inputs] == [2024, 2023]
    assert example.expression == "(3,008,709억원 − 2,589,355억원) ÷ 2,589,355억원 × 100"
    assert example.result_text == f"{metric.value:,.2f}%"


def test_growth_example_uses_the_same_prior_year_as_the_engine():
    """엔진이 올해 보고서의 전기 열로 계산했으면 예시도 그 숫자다 — 작년 보고서 숫자면 답이 어긋난다."""
    restated = fin(2023, revenue=2_000_000e8)
    latest = HISTORY[1].model_copy(update={"comparative": restated})
    history = [HISTORY[0], latest]
    metric = checkup(latest, HISTORY[0]).by_key("revenue_growth")
    example = worked_example(metric, history)
    assert example.inputs[1].value == 2_000_000e8
    assert recompute(example) == pytest.approx(metric.value)


def test_inputs_name_the_statement_they_come_from():
    metric = checkup(HISTORY[1], HISTORY[0]).by_key("interest_coverage")
    example = worked_example(metric, HISTORY)
    op, interest = example.inputs
    assert (op.label, op.statement) == ("영업이익", "손익계산서")
    assert interest.label == "이자의 지급" and interest.statement == "현금흐름표"


def test_no_example_without_a_value():
    """⚫(계정 없음)이나 규칙 판정(흑자 전환 등)은 계산 과정이 없다 — 0 으로 채워 만들지 않는다."""
    cur = fin(2024, **{**FULL, "capex": None})
    metric = checkup(cur).by_key("fcf")
    assert metric.value is None
    assert worked_example(metric, [cur]) is None
    turnaround = [fin(2023, **{**FULL, "operating_income": -10e8}), fin(2024, **FULL)]
    metric = checkup(turnaround[1], turnaround[0]).by_key("operating_income_growth")
    assert worked_example(metric, turnaround) is None


def test_money_is_written_in_eok_won():
    assert money_text(3_008_709e8) == "3,008,709억원"
    assert money_text(-1_234e8) == "-1,234억원"
    assert money_text(5_000_000) == "5,000,000원"


def test_example_text_has_no_verdict_words():
    result = checkup(HISTORY[1], HISTORY[0])
    for spec in METRIC_DEFS:
        example = worked_example(result.by_key(spec.key), HISTORY)
        for text in banned.iter_strings(example):
            assert not banned.find(text), (spec.key, text)
            assert not any(w in text for w in EVALUATIVE), (spec.key, text)
