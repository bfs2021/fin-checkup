"""업종별 읽는 법 — 왜 은행·보험·지주회사는 같은 자로 재지 않나.

지표마다의 ⊘ 이유와 대신 볼 것은 `explain.metrics` 의 `SectorCaveat` 에, 어떤 지표가 ⊘ 인지는
`metrics.engine.NOT_APPLICABLE_BY_SECTOR` 에 있다 — 여기서 다시 쓰지 않는다. 여기는 업종 구분 하나하나가
"어떤 장사라서 숫자가 다르게 생겼는지" 를 쉬운 말로 적는다. 업종이 좋다·나쁘다는 말은 하지 않는다.

UI 를 모른다. 업종을 가르는 규칙(KSIC 접두·지주회사 이름)은 `metrics.sector` 그대로다.
"""

from __future__ import annotations

from dataclasses import dataclass

from fin_checkup.metrics.sector import (
    FINANCIAL_PREFIXES,
    HOLDING_COMPANY_CODE,
    REAL_ESTATE_PREFIXES,
    Sector,
)


def _codes(prefixes: frozenset[str]) -> str:
    return "·".join(sorted(prefixes))


@dataclass(frozen=True)
class SectorReading:
    sector: Sector
    #: 어떤 회사가 이 기준으로 판정되나 (업종코드 규칙 포함).
    who: str
    #: 장사의 모양이 어떻게 달라서 숫자가 다르게 생겼나.
    why_different: tuple[str, ...]
    #: 이 사이트 밖에서 찾아볼 곳 — 대신 볼 지표가 어디에 실리는지.
    where_else: str = ""


#: 왜 업종을 먼저 가르나 — 페이지 첫머리.
WHY_SECTORS = (
    "같은 공식을 모든 회사에 들이대면 숫자가 거짓말을 할 때가 있어요. 은행은 고객이 맡긴 예금이 장부에 '빚(부채)'으로 "
    "잡혀서, 일반 회사의 자로 재면 부채비율이 1,000%를 훌쩍 넘어요. 그건 은행이 원래 그렇게 생긴 장사라서예요.",
    "그래서 fin-checkup 은 회사마다 업종을 먼저 가르고, 그 업종에 맞지 않는 지표는 억지로 색을 매기지 않아요. "
    "그런 칸에는 ⊘ 해당 없음과 함께 '대신 볼 것'을 적어요. 값이 나쁘게 나왔다는 이유로 ⊘가 되는 일은 없어요.",
)

#: 업종은 어떻게 정하나.
HOW_DECIDED = (
    "업종은 DART 기업개황에 적힌 업종코드(통계청 한국표준산업분류, KSIC)로 정해요. "
    f"앞 두 자리가 {_codes(FINANCIAL_PREFIXES)}이면 금융업, {_codes(REAL_ESTATE_PREFIXES)}이면 부동산업 기준으로 보고, "
    "나머지는 모두 일반 기준이에요. 업종코드가 없는 회사도 일반 기준으로 봐요."
)

READINGS: tuple[SectorReading, ...] = (
    SectorReading(
        Sector.FINANCIAL,
        who=(
            f"은행·보험·증권·카드·캐피탈과 금융지주예요(업종코드 앞 두 자리 {_codes(FINANCIAL_PREFIXES)}). "
            f"지주회사 코드({HOLDING_COMPANY_CODE})는 이름(금융·은행·증권 등)으로 가려낸 금융지주만 여기에 넣어요."
        ),
        why_different=(
            "은행은 고객에게 예금을 받아 그 돈을 빌려주고 이자 차이로 벌어요. 받은 예금은 언젠가 돌려줘야 하니 부채로 잡히고, "
            "그래서 부채가 자기 돈의 열 배를 넘는 게 보통이에요.",
            "보험사는 보험료를 받아 두었다가 나중에 보험금으로 내줘요. 내줄 준비로 쌓아 둔 돈(보험계약부채)이 부채의 대부분이에요.",
            "이자는 은행에겐 빌린 돈의 값이 아니라 장사의 원가(예금 이자)예요. 그래서 이자보상배율이 1보다 작아도 "
            "갚을 능력이 모자라다는 뜻이 아니에요.",
            "금융회사 재무상태표는 1년 안·밖(유동·비유동)으로 나누지 않고, 재고자산이나 매출채권 대신 대출채권으로 영업해요.",
        ),
        where_else=(
            "BIS 자기자본비율·지급여력비율(K-ICS)·고정이하여신비율 같은 건전성 숫자는 재무제표만으로는 계산할 수 없어 "
            "이 사이트에는 없어요. 사업보고서 본문이나 각 회사의 경영공시에 실려요."
        ),
    ),
    SectorReading(
        Sector.REAL_ESTATE,
        who=f"부동산 개발·임대·공급 회사예요(업종코드 앞 두 자리 {_codes(REAL_ESTATE_PREFIXES)}).",
        why_different=(
            "부동산 회사의 재고자산은 분양하려고 가진 땅과 건물이에요. 땅을 사서 짓고 다 팔기까지 몇 년이 걸려서, "
            "재고가 1년에 몇 번 팔려 나갔는지 세는 재고자산회전율이 뜻을 잃어요.",
            "그 밖의 지표(부채비율·영업이익률 등)는 일반 기준 그대로 판정해요.",
        ),
        where_else="사업별 분양률·공사 진행 현황은 사업보고서 본문의 '사업의 내용'에 있어요.",
    ),
)

#: 지주회사 — 같은 코드, 다른 기준.
HOLDING_READING = (
    f"업종코드 {HOLDING_COMPANY_CODE}(지주회사)는 KB금융 같은 금융지주와 (주)LG·(주)GS 같은 비금융 지주가 함께 써요. "
    "코드만 보고 모두 금융업으로 보면, 비금융 지주의 부채비율·이자보상배율이 ⊘로 가려져서 실제로 갚아야 하는 빚이 "
    "안 보이게 돼요. 그래서 이름으로 금융지주만 골라 금융업 기준으로 보고, 나머지 지주회사는 일반 기준으로 판정해요.",
    "연결재무제표가 있으면 연결을 쓰기 때문에, 지주회사의 숫자에는 지배하는 자회사들이 합쳐져 있어요. "
    "지주회사 한 곳의 지표는 그룹 여러 사업이 섞인 값이에요.",
)

#: 일반 기준 안에서도 업종마다 다른 것.
GENERAL_READING = (
    "일반 기준 안에서도 업종마다 '보통'이 달라요. 유통처럼 많이 팔고 조금 남기는 업종은 영업이익률이 원래 낮고, "
    "공장이 큰 업종은 총자산이익률(ROA)이 낮게 나오기 쉬워요. 회사 페이지의 지표 카드마다 같은 업종 회사들의 분포를 "
    "함께 보여 주는 것도 그래서예요.",
    "회전율 세 가지(총자산·재고자산·매출채권)는 업종 차이가 너무 커서 아예 경계값을 두지 않고 ⚪ 측정값으로만 보여 줘요.",
    "반대로 부채비율·유동비율·이자보상배율 같은 안정성 지표는 '갚을 수 있는가'라는 뜻이 업종과 상관없어서 같은 경계값을 써요.",
)


def reading_for(sector: Sector) -> SectorReading:
    return next(r for r in READINGS if r.sector is sector)
