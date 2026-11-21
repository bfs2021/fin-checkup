"""위험 신호 해설 — 무엇을 뜻하고, 왜 중요하고, 코드가 어떻게 찾는지.

위험 신호는 재무제표만으로 확정되는 사실이다 (`metrics/redflags.py`). 해설도 사실과
일반적인 구조까지만 말한다. 상장폐지·관리종목은 거래소가 여러 요건과 절차를 거쳐
정하므로 "요건에 해당하는 수치가 보였다"보다 더 나아가지 않는다.

탐지 방법 문장의 숫자(50%·3년·1배)는 redflags.py 의 상수에서 가져온다.
"""

from __future__ import annotations

from dataclasses import dataclass

from fin_checkup.metrics import redflags as _rf


@dataclass(frozen=True)
class RedFlagExplainer:
    key: str
    #: 쉬운 제목. {…} 자리에 redflags.py 상수가 들어간다. 회사 화면 제목은 RedFlag.label(실제 해 수)을 쓴다.
    title_template: str
    #: 이게 무슨 상태인가.
    what: str
    #: 왜 중요한가 — 사실과 일반적인 구조만.
    why_matters: str
    #: 코드가 어떻게 찾는가. {impairment_rate_min} 같은 자리에 redflags.py 상수가 들어간다.
    detection_template: str

    @property
    def title(self) -> str:
        return self.title_template.format(**_thresholds())

    @property
    def detection(self) -> str:
        return self.detection_template.format(**_thresholds())


def _thresholds() -> dict[str, object]:
    # 호출할 때마다 읽는다 — 상수를 바꾸면 문장이 바로 따라간다.
    return {
        "impairment_rate_min": _rf.IMPAIRMENT_RATE_MIN,
        "loss_streak_min": _rf.LOSS_STREAK_MIN,
        "zombie_coverage_max": _rf.ZOMBIE_COVERAGE_MAX,
        "zombie_streak_min": _rf.ZOMBIE_STREAK_MIN,
    }


_STREAK_HOW = (
    "모아 둔 사업연도(보통 최근 5년)를 가장 최근 해부터 거꾸로 세어 나가요. "
    "중간에 조건이 깨지거나 값이 없는 해를 만나면 거기서 세기를 멈춰요."
)

_ENTRIES: tuple[RedFlagExplainer, ...] = (
    RedFlagExplainer(
        key="full_capital_impairment",
        title_template="완전자본잠식",
        what=(
            "회사의 자기자본(자산에서 빚을 뺀 몫)이 0 이하가 된 상태예요. 쌓인 손실이 주주가 넣은 돈과 "
            "그동안 모은 이익을 다 깎아 먹어서, 장부상으로는 자산을 모두 팔아 빚을 갚아도 주주 몫이 남지 않는다는 뜻이에요."
        ),
        why_matters=(
            "거래소 규정에서 완전자본잠식은 상장폐지 사유에 해당해요. 실제 결정은 거래소가 여러 요건과 절차를 거쳐 내리므로, "
            "여기서는 그 요건에 해당하는 수치가 재무제표에 보였다는 사실까지만 알려요."
        ),
        detection_template="가장 최근 사업연도 재무상태표의 자기자본(자본총계)이 0 이하이면 표시해요.",
    ),
    RedFlagExplainer(
        key="partial_capital_impairment",
        title_template="자본잠식률 {impairment_rate_min}% 이상",
        what=(
            "자본잠식률은 주주가 처음 넣은 돈(자본금)에 비해 자기자본이 얼마나 줄었는지를 나타내요. "
            "손실이 쌓여 자기자본이 자본금보다 작아지면 그 모자란 만큼을 자본금에 대한 비율로 적어요."
        ),
        why_matters=(
            "자본잠식률 50% 이상은 거래소의 관리종목 지정 요건 중 하나예요. 손실이 더 이어져 자기자본이 0 이하가 되면 완전자본잠식이 돼요."
        ),
        detection_template=(
            "가장 최근 사업연도의 자본잠식률 = (자본금 − 자기자본) ÷ 자본금 × 100 이 {impairment_rate_min}% 이상이면 표시해요. "
            "자본금 계정을 찾지 못하면 추정하지 않고 판정하지 않아요. 자기자본이 0 이하면 이 신호 대신 '완전자본잠식'을 표시해요."
        ),
    ),
    RedFlagExplainer(
        key="consecutive_operating_loss",
        title_template="몇 년 연속 영업손실",
        what="본업에서 손해(영업손실)를 본 해가 최근까지 몇 년째 이어지고 있다는 뜻이에요.",
        why_matters=(
            "본업에서 돈이 계속 나가면 그 부족분을 보유 현금, 새로 빌린 돈, 유상증자 같은 외부 자금으로 메워야 해요. "
            "연구개발 단계의 회사처럼 사업 구조상 적자가 이어지는 경우도 있어서, 사업보고서에서 적자의 이유를 함께 볼 수 있어요."
        ),
        detection_template="영업이익이 0보다 작은 해가 {loss_streak_min}년 이상 이어지면 표시해요. "
        + _STREAK_HOW,
    ),
    RedFlagExplainer(
        key="profit_without_cash",
        title_template="흑자인데 영업현금 유출",
        what="손익계산서로는 이익(당기순이익)이 났는데, 같은 해 본업에서 실제 현금은 들어오지 않고 오히려 빠져나간 상태예요.",
        why_matters=(
            "이익에는 외상으로 판 매출처럼 아직 현금이 들어오지 않은 것도 들어가요. 이익과 현금이 반대로 가면 "
            "매출채권이나 재고가 크게 늘었는지 같은 이유를 재무제표 주석에서 확인할 수 있어요."
        ),
        detection_template="가장 최근 사업연도의 당기순이익이 0보다 크고, 영업활동현금흐름이 0보다 작으면 표시해요.",
    ),
    RedFlagExplainer(
        key="zombie_streak",
        title_template="몇 년 연속 이자보상배율 {zombie_coverage_max} 미만",
        what=(
            "본업으로 번 돈(영업이익)이 이자비용보다 적은 해가 몇 년째 이어진다는 뜻이에요. "
            "흔히 '한계기업'이나 '좀비기업'이라고 부르는 상태예요."
        ),
        why_matters="번 돈으로 이자를 다 못 내면 모자란 이자를 새로 빌리거나, 자산을 팔거나, 증자한 돈으로 메워야 해요.",
        detection_template=(
            "영업이익 ÷ 이자비용이 {zombie_coverage_max} 미만인 해가 {zombie_streak_min}년 이상 이어지면 표시해요. "
            + _STREAK_HOW
            + " 이자비용이 0인 해, 이자비용을 금융원가(환율 손실 등이 섞인 값)로밖에 알 수 없는 해도 거기서 멈춰요."
            " 이자비용 항목이 없으면 현금흐름표의 이자 지급액으로 봐요. 금융업에는 적용하지 않아요 — 이자가 영업의 원가라서 {zombie_coverage_max} 미만이 흔해요."
        ),
    ),
)

RED_FLAG_EXPLAINERS: dict[str, RedFlagExplainer] = {e.key: e for e in _ENTRIES}


def get_red_flag_explainer(key: str) -> RedFlagExplainer:
    """RedFlag.key 의 해설. 없는 key 면 KeyError."""
    return RED_FLAG_EXPLAINERS[key]


def red_flag_explainers() -> tuple[RedFlagExplainer, ...]:
    return _ENTRIES
