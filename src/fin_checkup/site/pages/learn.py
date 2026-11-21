"""처음 오셨나요 `/learn/` — 신호등 읽는 법. 자세한 가이드(U7 등)는 이 아래 경로에 붙는다."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fin_checkup.metrics.signals import Signal
from fin_checkup.site.context import Site
from fin_checkup.site.registry import Output, page
from fin_checkup.site.view import SignalView


@dataclass(frozen=True)
class LegendItem:
    signal: SignalView
    meaning: str


#: 신호마다 뜻 한 줄. 판정 규칙은 metrics/engine.py — 여기는 읽는 법만.
MEANINGS: dict[Signal, str] = {
    Signal.GREEN: "경계값으로 보면 정상 구간에 있습니다.",
    Signal.YELLOW: "주의 구간에 있습니다. 경계값과 작년 값을 함께 보세요.",
    Signal.RED: "위험 구간에 있습니다. 어떤 계산식으로 왜 그 구간인지 지표 옆에 적혀 있습니다.",
    Signal.NEUTRAL: "값은 쟀지만 절대 기준이 없는 지표입니다(업종마다 크게 다른 회전율 등).",
    Signal.NOT_APPLICABLE: "이 업종에는 맞지 않아 판정하지 않는 지표입니다. 대신 볼 것을 함께 적습니다.",
    Signal.UNKNOWN: "공시에서 필요한 계정을 찾지 못했습니다. 0으로 채우지 않습니다.",
}

LEGEND = tuple(LegendItem(SignalView.of(signal), MEANINGS[signal]) for signal in Signal)


@page("learn")
def learn_index(site: Site) -> Iterator[Output]:
    yield site.render("learn/index.html", "learn/index.html", legend=LEGEND)
