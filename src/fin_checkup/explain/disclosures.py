"""위험 공시 유형 해설 — 이게 뭔가, 주주에게 보통 어떤 의미가 있을 수 있나, 원문에서 무엇을 보나.

알림은 "어떤 공시가 떴다는 사실 + DART 원문 링크"까지다 (`docs/REGULATORY.md`). 해설도
그 공시가 무엇이고 일반적으로 어떤 구조로 주주와 이어지는지(예: 유상증자 → 주식 수 증가 →
지분 희석 가능)까지만 말한다. 그래서 어떻게 하라는 말은 쓰지 않는다.

분류 기준(제목에 걸리는 표현)과 알림 강도는 `alerts/classify.py` 에서 가져온다.
"""

from __future__ import annotations

from dataclasses import dataclass

from fin_checkup.alerts import classify as _classify
from fin_checkup.alerts.classify import RiskKind, Severity

#: 모든 유형에 공통인 DART 원문 보는 법.
HOW_TO_READ_ON_DART: tuple[str, ...] = (
    "알림이나 화면의 'DART 원문 보기' 링크를 누르면 그 공시가 바로 열려요.",
    "직접 찾을 때는 dart.fss.or.kr 에서 회사 이름을 검색한 뒤, 공시 목록에서 제목을 누르면 돼요.",
    "공시 화면 왼쪽 목차에서 항목별로 골라 볼 수 있어요.",
    "제목 앞에 [기재정정]·[첨부정정] 등이 붙어 있으면 앞서 낸 공시를 고친 거예요. 무엇이 바뀌었는지는 본문 앞쪽의 정정 사항 표에 있어요.",
)


@dataclass(frozen=True)
class DisclosureExplainer:
    kind: RiskKind
    #: 이게 뭔가.
    what: str
    #: 주주에게 보통 어떤 의미가 있을 수 있나 — 사실과 일반적인 구조만.
    shareholder_meaning: str
    #: 원문에서 먼저 볼 곳.
    where_to_look: str
    #: 실제 DART 공시 제목 예. classify() 가 이 유형으로 분류한다(테스트).
    example_titles: tuple[str, ...]

    @property
    def label(self) -> str:
        return self.kind.label

    @property
    def severity(self) -> Severity:
        return self.kind.severity

    @property
    def matched_phrases(self) -> tuple[str, ...]:
        """제목에 이 표현(정규식)이 있으면 이 유형으로 분류한다 — classify.PATTERNS 그대로."""
        return tuple(pattern for kind, pattern in _classify.PATTERNS if kind is self.kind)


_ENTRIES: tuple[DisclosureExplainer, ...] = (
    DisclosureExplainer(
        RiskKind.DISTRESS,
        what=(
            "회사가 어음·수표 대금을 치르지 못했거나(부도), 영업의 전부나 일부를 멈추게 됐거나, "
            "법원에 회생절차(빚을 조정해 회사를 다시 세우는 절차)나 파산을 신청했다는 등의 사실을 알리는 공시예요. "
            "채권은행이 관리하는 절차(이른바 워크아웃)가 시작된 경우도 여기에 묶어요."
        ),
        shareholder_meaning=(
            "회사가 계속 영업할 수 있는지에 직접 걸린 사건이에요. 회생절차에서는 빚 조정과 함께 기존 주식을 줄이는 감자가 "
            "이뤄지는 경우가 있고, 거래소가 주식 매매를 멈추는 경우도 있어요."
        ),
        where_to_look="공시 본문의 사유와 앞으로의 일정(법원 결정·채권자 협의 등)이 적힌 표를 먼저 보세요.",
        example_titles=("주요사항보고서(부도발생)", "주요사항보고서(회생절차개시신청)"),
    ),
    DisclosureExplainer(
        RiskKind.LISTING_STATUS,
        what=(
            "거래소가 회사를 관리종목으로 지정했거나, 상장폐지 사유가 생겼거나, 주식 매매를 잠시 멈췄거나, "
            "투자주의환기종목(코스닥)으로 지정했다는 공시예요. 지정이 풀렸다는 '해제' 공시는 여기서 빼요."
        ),
        shareholder_meaning=(
            "관리종목은 상장폐지 요건에 가까워졌다는 뜻의 지정이에요. 매매거래정지 동안에는 그 주식을 거래소에서 사고팔 수 없어요. "
            "상장폐지가 확정되면 정리매매 기간을 거쳐 거래소에서 빠져요. 다만 매매거래정지는 액면분할·합병 같은 "
            "일상적인 절차 때문에도 생기니 사유를 꼭 확인해야 해요."
        ),
        where_to_look="지정·정지의 사유와 기간(매매거래정지라면 정지 기간과 해제 조건)을 먼저 보세요.",
        example_titles=("관리종목지정", "상장폐지사유발생"),
    ),
    DisclosureExplainer(
        RiskKind.AUDIT_OPINION,
        what=(
            "외부 감사인(회계법인)이 회사 재무제표를 검토하고 낸 감사보고서, 또는 감사의견과 관련된 공시예요. "
            "제목에 '감사보고서'가 들어간 공시는 모두 이 유형으로 잡혀요 — 대부분은 '적정' 의견이 담긴 정기 제출이에요."
        ),
        shareholder_meaning=(
            "감사의견은 적정·한정·부적정·의견거절 네 가지예요. 적정이 아닌 의견(비적정)은 관리종목 지정이나 "
            "상장폐지 사유가 될 수 있어요. 적정이어도 '계속기업 관련 중요한 불확실성' 문단이 붙으면 "
            "감사인이 회사의 존속에 의문을 적어 둔 거예요."
        ),
        where_to_look="'독립된 감사인의 감사보고서' 첫 부분의 감사의견 문단, 그리고 계속기업 관련 문단이 있는지를 보세요.",
        example_titles=("감사보고서제출",),
    ),
    DisclosureExplainer(
        RiskKind.CAPITAL_REDUCTION,
        what=(
            "회사의 자본금을 줄이는 결정이에요. 보통 여러 주를 한 주로 합치거나 일부 주식을 없애는 식으로 주식 수를 줄여요."
        ),
        shareholder_meaning=(
            "무상감자는 주주에게 대가 없이 주식 수를 줄이는 것으로, 쌓인 손실(결손금)을 장부에서 털어 내려고 하는 경우가 많아요. "
            "유상감자는 줄인 주식만큼 주주에게 돈을 돌려줘요. 어느 쪽이든 감자 비율만큼 내 주식 수가 줄고, "
            "감자 절차 중에는 매매거래가 잠시 정지되기도 해요. 무상인지 유상인지는 원문에서 확인해야 해요."
        ),
        where_to_look="감자 비율, 감자 방법(무상·유상), 감자 사유, 그리고 일정(매매거래정지 기간)을 보세요.",
        example_titles=("주요사항보고서(감자결정)",),
    ),
    DisclosureExplainer(
        RiskKind.CONVERTIBLE_BOND,
        what=(
            "회사가 돈을 빌리면서 내는 채권인데, 나중에 주식으로 바꿀 수 있는 권리가 붙은 것을 발행하기로 했다는 공시예요. "
            "전환사채(CB)는 채권을 정해진 가격(전환가액)에 그 회사 새 주식으로 바꿀 수 있고, "
            "신주인수권부사채(BW)는 채권은 그대로 두고 새 주식을 살 권리가 붙어 있어요. "
            "교환사채(EB)는 회사가 이미 가진 주식(자기주식이나 다른 회사 주식)으로 바꿔 줘요."
        ),
        shareholder_meaning=(
            "CB·BW의 권리가 행사되면 새 주식이 생겨 전체 주식 수가 늘고, 기존 주주의 지분 비율이 낮아질 수 있어요(지분 희석). "
            "주가가 내려가면 전환가액을 낮추는 조항(리픽싱)이 붙기도 하는데, 그러면 바뀌는 주식 수가 더 늘어나요. "
            "EB는 새 주식을 만들지 않아 주식 수는 그대로지만, 회사가 갖고 있던 주식이 시장에 나올 수 있어요."
        ),
        where_to_look="전환(행사·교환)가액, 전환으로 발행될 주식 수와 그것이 전체 주식에서 차지하는 비율, 전환가액 조정 조항을 보세요.",
        example_titles=("주요사항보고서(전환사채권발행결정)", "주요사항보고서(신주인수권부사채권발행결정)"),
    ),
    DisclosureExplainer(
        RiskKind.CAPITAL_RAISE,
        what=(
            "회사가 새 주식을 발행해 돈을 받고 파는 결정이에요. 기존 주주에게 먼저 살 권리를 주는 주주배정, "
            "누구나 청약할 수 있는 일반공모, 정해진 상대에게 파는 제3자배정 같은 방식이 있어요."
        ),
        shareholder_meaning=(
            "주식 수가 늘어서, 새 주식을 받지 않는 기존 주주는 지분 비율이 낮아져요(지분 희석). "
            "새 주식은 보통 시가보다 할인된 가격에 발행돼요. 모은 돈을 어디에 쓰는지는 공시에 적혀 있어요."
        ),
        where_to_look="증자 방식, 새로 발행할 주식 수, 발행가액, 그리고 '자금조달의 목적'(시설·운영·빚 갚기 등에 각각 얼마)을 보세요.",
        example_titles=("주요사항보고서(유상증자결정)",),
    ),
    DisclosureExplainer(
        RiskKind.MAJOR_SHAREHOLDER,
        what=(
            "회사의 최대주주가 바뀌었다는 공시, 또는 누군가 회사 주식을 5% 이상 갖게 됐거나 "
            "그 비율이 1%포인트 이상 바뀌었을 때 내는 대량보유 보고(이른바 5% 룰)예요."
        ),
        shareholder_meaning=(
            "최대주주가 바뀌면 경영진이나 사업 방향이 달라질 수 있어요. 대량보유 보고에는 그 주식을 가진 목적"
            "(경영에 영향을 주려는지, 단순 투자인지)이 적혀 있어요."
        ),
        where_to_look="최대주주 변경은 변경 전후의 최대주주와 지분율·변경 사유를, 대량보유 보고는 보유 목적과 보유 비율 변화를 보세요.",
        example_titles=("최대주주변경", "주식등의대량보유상황보고서(일반)"),
    ),
    DisclosureExplainer(
        RiskKind.INSIDER_TRADING,
        what=(
            "회사 임원이나 주요주주(10% 이상 보유 등)가 가진 그 회사 주식 수가 바뀌었을 때 내는 "
            "'임원·주요주주 특정증권등 소유상황보고서'예요."
        ),
        shareholder_meaning=(
            "회사 사정을 가까이에서 아는 사람들의 보유 변화지만, 세금·대출 상환·"
            "주식 보상(스톡옵션 행사) 같은 개인 사정으로도 생겨요. 한 건만으로 뜻을 읽기는 어려워요."
        ),
        where_to_look="소유 상황 표의 변동일, 변동 사유(장내 거래·증여 등), 늘거나 준 주식 수와 단가를 보세요.",
        example_titles=("임원ㆍ주요주주특정증권등소유상황보고서",),
    ),
)

DISCLOSURE_EXPLAINERS: dict[RiskKind, DisclosureExplainer] = {e.kind: e for e in _ENTRIES}


def get_disclosure_explainer(kind: RiskKind | str) -> DisclosureExplainer:
    """RiskKind(또는 그 값 'capital_raise' 등)의 해설."""
    return DISCLOSURE_EXPLAINERS[RiskKind(kind)]


def disclosure_explainers() -> tuple[DisclosureExplainer, ...]:
    """classify.RiskKind 정의 순서대로."""
    return tuple(DISCLOSURE_EXPLAINERS[k] for k in RiskKind)
