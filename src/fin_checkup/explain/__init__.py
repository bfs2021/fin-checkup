"""쉬운 말 해설 — 지표·위험 신호·공시 유형·용어.

UI 를 모른다. 사이트·Streamlit·CLI 가 같은 문장을 쓴다. 숫자(공식·경계값)는 전부
`fin_checkup.metrics` 에서 가져오고, 사고팔라는 말은 쓰지 않는다 (`explain.banned`).
"""

from fin_checkup.explain.metrics import (
    METRIC_EXPLAINERS,
    MetricExplainer,
    SectorCaveat,
    SpecialRule,
    band_ranges,
    explainers,
    get_explainer,
    threshold_text,
)
from fin_checkup.explain.redflags import (
    RED_FLAG_EXPLAINERS,
    RedFlagExplainer,
    get_red_flag_explainer,
    red_flag_explainers,
)
from fin_checkup.explain.why import why_color

__all__ = [
    "METRIC_EXPLAINERS",
    "MetricExplainer",
    "RED_FLAG_EXPLAINERS",
    "RedFlagExplainer",
    "SectorCaveat",
    "SpecialRule",
    "band_ranges",
    "explainers",
    "get_explainer",
    "get_red_flag_explainer",
    "red_flag_explainers",
    "threshold_text",
    "why_color",
]
