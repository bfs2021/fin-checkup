"""회사 페이지 차트 — JS·CDN 없이 서버에서 만드는 인라인 SVG 문자열.

원칙
- **없는 해는 그리지 않는다.** 이어 긋거나 0 막대로 메우지 않고, 그 칸에 ⚫ 데이터 없음(또는 ⊘ 해당 없음)을
  글자로 적는다. 선 그래프 대신 연도별 막대를 쓰는 것도 그래서다 — 선은 빈 해를 건너 이어 보인다.
- **색은 CSS 변수로만.** 모양은 클래스(`fc-ch-*`)만 달고 색·글꼴은 `static/site.css` 가 정한다.
  다크 모드가 따라오고, CSP(`style-src 'self'`) 가 막는 인라인 style 을 쓰지 않는다.
- **글자는 전부 이스케이프.** 지표 이름은 코드에서 오지만 회사명·값 문자열이 섞여도 SVG 가 깨지지 않게
  `_esc` 를 거친다. 결과는 `Markup` 이라 템플릿이 다시 이스케이프하지 않는다.
- **색만으로 말하지 않는다.** 모든 그림에 `<title>`·`<desc>`, 막대마다 `<title>`(마우스를 올리면 값),
  템플릿은 같은 값을 `<details>` 표로 한 번 더 싣는다.

확장 지점: 새 그림은 `(데이터) -> Markup` 함수 하나 + `tests/test_site_charts.py`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from html import escape

from markupsafe import Markup

from fin_checkup.format import chart_scale, format_metric, format_money
from fin_checkup.metrics.engine import MONEY, checkup
from fin_checkup.metrics.signals import Signal
from fin_checkup.models import Financials
from fin_checkup.service import Checkup

#: 추이에 그릴 금액 계정 (Financials 필드, 이름). 순서가 화면 순서다.
AMOUNT_SERIES: tuple[tuple[str, str], ...] = (
    ("revenue", "매출액"),
    ("operating_income", "영업이익"),
    ("net_income", "당기순이익"),
    ("operating_cash_flow", "영업활동현금흐름"),
)
#: 추이에 그릴 비율 지표 (engine 의 key). 이름·단위·⊘ 여부는 엔진이 정한다.
RATIO_SERIES: tuple[str, ...] = ("operating_margin", "debt_ratio", "current_ratio")


def _esc(text: object) -> str:
    return escape(str(text), quote=True)


# ── 추이 데이터 ───────────────────────────────────────────────────


class Gap(str, Enum):
    """그 해 값이 없는 이유. 칸을 비울 때 무엇 때문인지 감추지 않는다."""

    NO_YEAR = "no_year"
    NO_ACCOUNT = "no_account"
    NOT_APPLICABLE = "not_applicable"

    @property
    def mark(self) -> str:
        return "⊘" if self is Gap.NOT_APPLICABLE else "⚫"

    @property
    def label(self) -> str:
        return "해당 없음" if self is Gap.NOT_APPLICABLE else "데이터 없음"

    @property
    def reason(self) -> str:
        return {
            "no_year": "이 해의 사업보고서 재무가 아직 수집되지 않았습니다",
            "no_account": "공시에서 이 계정을 찾지 못했습니다",
            "not_applicable": "이 업종에는 뜻이 없는 지표라 판정하지 않습니다",
        }[self.value]


@dataclass(frozen=True)
class TrendPoint:
    year: int
    value: float | None
    #: 표시 문자열. 값이 없으면 "⚫ 데이터 없음" / "⊘ 해당 없음".
    text: str
    gap: Gap | None = None


@dataclass(frozen=True)
class TrendSeries:
    key: str
    label: str
    #: `MONEY` 또는 엔진 지표의 단위(%, 배 …).
    unit: str
    currency: str
    points: tuple[TrendPoint, ...]

    @property
    def present(self) -> list[TrendPoint]:
        return [p for p in self.points if p.gap is None]


def _gap_point(year: int, gap: Gap) -> TrendPoint:
    return TrendPoint(year=year, value=None, text=f"{gap.mark} {gap.label}", gap=gap)


def trend_series(data: Checkup, years: int = 5) -> list[TrendSeries]:
    """최근 `years` 개 사업연도(최신 연도 포함)의 금액·비율 추이.

    캐시에 없는 해도 칸으로 남긴다 — 5칸 중 2칸만 차 있으면 그렇게 보여야 한다.
    비율 지표가 이 업종에 ⊘ 이면(최신 연도 기준) 그 추이는 통째로 뺀다.
    """
    latest = data.history[-1]
    currency = latest.currency
    by_year: dict[int, Financials] = {f.bsns_year: f for f in data.history}
    span = range(latest.bsns_year - years + 1, latest.bsns_year + 1)
    sector = data.result.sector

    series: list[TrendSeries] = []
    for field, label in AMOUNT_SERIES:
        points = []
        for year in span:
            fin = by_year.get(year)
            value = getattr(fin, field) if fin is not None else None
            if fin is None:
                points.append(_gap_point(year, Gap.NO_YEAR))
            elif value is None:
                points.append(_gap_point(year, Gap.NO_ACCOUNT))
            else:
                points.append(TrendPoint(year, value, format_money(value, currency)))
        series.append(TrendSeries(field, label, MONEY, currency, tuple(points)))

    yearly = {year: checkup(fin, by_year.get(year - 1), sector=sector) for year, fin in by_year.items()}
    for key in RATIO_SERIES:
        current = data.result.by_key(key)
        if current is None or current.signal is Signal.NOT_APPLICABLE:
            continue
        points = []
        for year in span:
            result = yearly.get(year)
            metric = result.by_key(key) if result is not None else None
            if result is None:
                points.append(_gap_point(year, Gap.NO_YEAR))
            elif metric is None or metric.signal is Signal.NOT_APPLICABLE:
                points.append(_gap_point(year, Gap.NOT_APPLICABLE))
            elif metric.value is None:
                points.append(_gap_point(year, Gap.NO_ACCOUNT))
            else:
                points.append(TrendPoint(year, metric.value, format_metric(metric, currency)))
        series.append(TrendSeries(key, current.label, current.unit, currency, tuple(points)))
    return series


# ── 눈금 ──────────────────────────────────────────────────────────


def nice_ticks(lo: float, hi: float, count: int = 3) -> list[float]:
    """0 을 지나는 깔끔한 눈금(1·2·2.5·5 × 10ⁿ 간격). 막대는 0 에서 자라므로 0 은 늘 포함."""
    lo, hi = min(lo, 0.0), max(hi, 0.0)
    if hi == lo:
        hi = lo + 1.0
    raw = (hi - lo) / max(count, 1)
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    start = math.floor(lo / step) * step
    ticks: list[float] = []
    value = start
    while value < hi + step * 0.999:
        ticks.append(round(value, 10))
        value += step
    return ticks


_SHORT_KRW = {"조원": "조", "억원": "억", "만원": "만"}
_SHORT_USD = {"십억 달러": "B", "백만 달러": "M", "천 달러": "K"}


def _tick_text(value: float, unit: str, divisor: float, scale_label: str) -> str:
    if unit == MONEY:
        scaled = value / divisor
        digits = 0 if abs(scaled) >= 10 or scaled == int(scaled) else 1
        short = _SHORT_KRW.get(scale_label) or _SHORT_USD.get(scale_label, "")
        return f"{scaled:,.{digits}f}{short}"
    digits = 0 if abs(value) >= 10 or value == int(value) else 1
    return f"{value:,.{digits}f}{unit}"


def scale_note(series: TrendSeries) -> str:
    """패널 캡션에 붙일 단위 설명."""
    if series.unit == MONEY:
        _, label = chart_scale([p.value for p in series.points], series.currency)
        return f"단위 {label}"
    return f"단위 {series.unit}"


# ── 추이 SVG ──────────────────────────────────────────────────────

#: viewBox 크기. 폭 100% 로 늘어나므로 360px 화면에서는 약 0.9배, 넓은 화면 2단에서는 약 1.1배.
TREND_W, TREND_H = 320, 128
_LEFT, _RIGHT, _TOP, _BOTTOM = 46, 6, 20, 24
_BAR_MAX = 24
_RADIUS = 4


def _bar_path(x: float, width: float, y_zero: float, y_end: float) -> str:
    """0 에서 자라는 막대. 데이터 끝만 4px 둥글게, 기준선 쪽은 각지게."""
    height = abs(y_end - y_zero)
    r = min(_RADIUS, height, width / 2)
    left, right = x, x + width
    if y_end <= y_zero:  # 양수 — 위로
        return (
            f"M{left:.1f},{y_zero:.1f}V{y_end + r:.1f}"
            f"Q{left:.1f},{y_end:.1f} {left + r:.1f},{y_end:.1f}"
            f"H{right - r:.1f}Q{right:.1f},{y_end:.1f} {right:.1f},{y_end + r:.1f}"
            f"V{y_zero:.1f}Z"
        )
    return (  # 음수 — 아래로
        f"M{left:.1f},{y_zero:.1f}V{y_end - r:.1f}"
        f"Q{left:.1f},{y_end:.1f} {left + r:.1f},{y_end:.1f}"
        f"H{right - r:.1f}Q{right:.1f},{y_end:.1f} {right:.1f},{y_end - r:.1f}"
        f"V{y_zero:.1f}Z"
    )


def _desc(series: TrendSeries) -> str:
    return " · ".join(f"{p.year}년 {p.text}" for p in series.points)


def trend_svg(series: TrendSeries, chart_id: str) -> Markup:
    """연도별 막대 한 칸 그림(작은 배수 한 장). 값이 없는 해는 ⚫/⊘ 칸."""
    cid = _esc(chart_id)
    values = [p.value for p in series.present if p.value is not None]
    divisor, scale_label = chart_scale(values, series.currency) if series.unit == MONEY else (1.0, "")
    ticks = nice_ticks(min(values, default=0.0), max(values, default=0.0))
    lo, hi = ticks[0], ticks[-1]

    plot_top, plot_bottom = _TOP, TREND_H - _BOTTOM
    # 음수가 있으면 맨 아래 막대 끝 밑에 값 글자가 들어갈 자리를 남긴다.
    floor = plot_bottom - (14 if lo < 0 else 0)

    def y(value: float) -> float:
        return floor - (value - lo) / (hi - lo) * (floor - plot_top)

    slot = (TREND_W - _LEFT - _RIGHT) / len(series.points)
    bar = min(_BAR_MAX, slot * 0.55)
    y_zero = y(0.0)
    latest = series.points[-1]

    parts = [
        f'<svg class="fc-ch fc-ch-trend" viewBox="0 0 {TREND_W} {TREND_H}" role="img" '
        f'aria-labelledby="{cid}-t {cid}-d" xmlns="http://www.w3.org/2000/svg">',
        f'<title id="{cid}-t">{_esc(series.label)} {len(series.points)}개년 추이</title>',
        f'<desc id="{cid}-d">{_esc(_desc(series))}</desc>',
    ]
    for tick in ticks:
        ty = y(tick)
        cls = "fc-ch-zero" if tick == 0 else "fc-ch-grid"
        parts.append(
            f'<line class="{cls}" x1="{_LEFT}" x2="{TREND_W - _RIGHT}" y1="{ty:.1f}" y2="{ty:.1f}"/>'
        )
        parts.append(
            f'<text class="fc-ch-tick" x="{_LEFT - 6}" y="{ty + 4:.1f}" text-anchor="end">'
            f"{_esc(_tick_text(tick, series.unit, divisor, scale_label))}</text>"
        )

    for i, point in enumerate(series.points):
        cx = _LEFT + slot * (i + 0.5)
        is_latest = point is latest
        parts.append(f'<g class="fc-ch-year{" fc-ch-latest" if is_latest else ""}">')
        parts.append(f"<title>{_esc(point.year)}년 {_esc(series.label)}: {_esc(point.text)}</title>")
        if point.gap is not None or point.value is None:
            gap = point.gap or Gap.NO_ACCOUNT
            gx = cx - slot / 2 + 3
            mid = (plot_top + plot_bottom) / 2
            parts.append(
                f'<rect class="fc-ch-gap" x="{gx:.1f}" y="{plot_top}" width="{slot - 6:.1f}" '
                f'height="{plot_bottom - plot_top}" rx="4"/>'
            )
            parts.append(
                f'<text class="fc-ch-gap-mark" x="{cx:.1f}" y="{mid - 6:.1f}" text-anchor="middle">'
                f"{gap.mark}</text>"
            )
            for line, text in enumerate(gap.label.split(" ")):
                parts.append(
                    f'<text class="fc-ch-gap-text" x="{cx:.1f}" y="{mid + 10 + line * 12:.1f}" '
                    f'text-anchor="middle">{_esc(text)}</text>'
                )
        else:
            y_end = y(point.value)
            parts.append(f'<path class="fc-ch-bar" d="{_bar_path(cx - bar / 2, bar, y_zero, y_end)}"/>')
            if is_latest:
                label_y = y_end - 5 if point.value >= 0 else y_end + 12
                parts.append(
                    f'<text class="fc-ch-value" x="{cx:.1f}" y="{label_y:.1f}" text-anchor="middle">'
                    f"{_esc(_tick_text(point.value, series.unit, divisor, scale_label))}</text>"
                )
        parts.append(
            f'<text class="fc-ch-x" x="{cx:.1f}" y="{TREND_H - 6}" text-anchor="middle">'
            f"{_esc(point.year)}</text>"
        )
        parts.append("</g>")
    parts.append("</svg>")
    return Markup("".join(parts))


@dataclass(frozen=True)
class TrendPanel:
    series: TrendSeries
    svg: Markup
    scale_note: str


def trend_panels(data: Checkup, years: int = 5) -> list[TrendPanel]:
    """회사 페이지 '5개년 추이' 섹션이 쓰는 패널 목록."""
    code = data.corp.stock_code or data.corp.corp_code
    return [
        TrendPanel(s, trend_svg(s, f"trend-{code}-{s.key}"), scale_note(s)) for s in trend_series(data, years)
    ]


def years_of(panels: Sequence[TrendPanel]) -> list[int]:
    """표 머리에 쓸 연도. 모든 패널이 같은 연도 칸을 쓴다."""
    return [p.year for p in panels[0].series.points] if panels else []
