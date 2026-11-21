"""배우기 `/learn/` — 허브와 그 아래 가이드.

- `/learn/` 허브: 신호등 읽는 법 + 가이드 목록
- `/learn/first-read/` 재무제표 처음 읽기: 실제 회사 페이지 하나(`site.examples.default_example`)를
  위에서부터 따라 읽는다
- `/learn/redflags/` 위험 신호 해설 (`explain.redflags`)
- `/learn/disclosures/` 위험 공시 유형 해설과 DART 원문 보는 법 (`explain.disclosures`)
- `/learn/glossary/` 용어집 (`explain.glossary`)

문장 데이터는 `fin_checkup.explain` 의 것을 그대로 쓴다. 가이드 본문(회사 페이지의 어디를 보라는 안내)은
사이트 화면에 묶인 말이라 템플릿에 있다. 사고팔 때를 말하지 않는다 — 금지 문구는 테스트가 본다.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fin_checkup.explain._korean import topic
from fin_checkup.explain.disclosures import HOW_TO_READ_ON_DART, disclosure_explainers
from fin_checkup.explain.glossary import GLOSSARY, GLOSSARY_BY_SLUG, GlossaryTerm
from fin_checkup.explain.metrics import get_explainer
from fin_checkup.explain.redflags import red_flag_explainers
from fin_checkup.explain.worked import ROUNDING_NOTE, money_text
from fin_checkup.metrics.signals import Signal
from fin_checkup.site.context import CompanyEntry, Site
from fin_checkup.site.examples import RULE_TEXT, default_example
from fin_checkup.site.registry import Output, page
from fin_checkup.site.related import next_reads
from fin_checkup.site.view import CompanyView, SignalView, company_view


@dataclass(frozen=True)
class LegendItem:
    signal: SignalView
    meaning: str


#: 신호마다 뜻 한 줄. 판정 규칙은 metrics/engine.py — 여기는 읽는 법만.
MEANINGS: dict[Signal, str] = {
    Signal.GREEN: "경계값으로 보면 정상 구간에 있어요.",
    Signal.YELLOW: "주의 구간에 있어요. 경계값과 작년 값을 함께 보세요.",
    Signal.RED: "위험 구간에 있어요. 어떤 계산식으로 왜 그 구간인지 지표 옆에 적혀 있어요.",
    Signal.NEUTRAL: "값은 쟀지만 절대 기준이 없는 지표예요(업종마다 크게 다른 회전율 등).",
    Signal.NOT_APPLICABLE: "이 업종에는 맞지 않아 판정하지 않는 지표예요. 대신 볼 것을 함께 적어요.",
    Signal.UNKNOWN: "공시에서 필요한 계정을 찾지 못했어요. 0으로 채우지 않아요.",
}

LEGEND = tuple(LegendItem(SignalView.of(signal), MEANINGS[signal]) for signal in Signal)


@dataclass(frozen=True)
class Guide:
    path: str
    title: str
    summary: str


#: 허브에 싣는 가이드 — 읽는 차례대로.
GUIDES: tuple[Guide, ...] = (
    Guide("learn/first-read/", "재무제표 처음 읽기", "실제 회사 페이지 하나를 위에서부터 같이 읽어 봐요."),
    Guide(
        "m/",
        "재무 지표 17개",
        "신호등 한 칸 한 칸이 무엇을 재는지, 계산식과 경계값, 실제 숫자로 계산해 보기.",
    ),
    Guide("learn/redflags/", "위험 신호", "재무제표만으로 확인되는 다섯 가지 신호가 무엇을 뜻하는지."),
    Guide(
        "learn/disclosures/",
        "위험 공시 유형",
        "유상증자·감자·감사의견 같은 공시가 무엇이고, DART 원문에서 어디를 보는지.",
    ),
    Guide(
        "learn/sectors/",
        "업종별 읽는 법",
        "은행·보험·지주회사·부동산 회사는 왜 일부 지표가 ⊘ 이고, 대신 무엇을 보는지.",
    ),
    Guide("learn/glossary/", "용어집", f"화면에서 처음 만나는 말 {len(GLOSSARY)}개를 한 줄로."),
    Guide("s/", "업종 목록", "업종마다 지표가 어떻게 퍼져 있는지(중앙값·사분위)와 소속 회사 이름순 목록."),
)


def glossary_path(slug: str) -> str:
    return f"learn/glossary/#{slug}"


# ── 재무제표 처음 읽기 ─────────────────────────────────────────────


@dataclass(frozen=True)
class KeyNumber:
    label: str
    statement: str
    text: str
    #: 용어집 slug. 없으면 빈 문자열.
    term: str


#: 첫 읽기에서 보여 줄 공시 숫자 — (Financials 필드, 이름, 표, 용어집 slug).
KEY_NUMBERS: tuple[tuple[str, str, str, str], ...] = (
    ("total_assets", "자산총계", "재무상태표", "assets"),
    ("total_liabilities", "부채총계", "재무상태표", "liabilities"),
    ("total_equity", "자본총계(자기자본)", "재무상태표", "equity"),
    ("revenue", "매출액", "손익계산서", "revenue"),
    ("operating_income", "영업이익", "손익계산서", "operating-income"),
    ("net_income", "당기순이익", "손익계산서", "net-income"),
    ("operating_cash_flow", "영업활동현금흐름", "현금흐름표", "operating-cash-flow"),
)


@dataclass(frozen=True)
class FirstRead:
    entry: CompanyEntry
    c: CompanyView
    numbers: tuple[KeyNumber, ...]
    #: "삼성전자는" · "기아는" · "LG화학은" — 받침에 맞춘 조사.
    name_topic: str
    #: 예시로 짚는 지표 하나 — 영업이익률 (해설 페이지와 같은 회사·같은 값).
    sample_metric_label: str
    sample_metric_easy: str
    sample_formula: str


def first_read(site: Site) -> FirstRead | None:
    entry = default_example(site)
    if entry is None:
        return None
    latest = entry.checkup.history[-1]
    currency = entry.checkup.result.currency
    numbers = []
    for field, label, statement, slug in KEY_NUMBERS:
        value = getattr(latest, field)
        # 없는 숫자는 '—' 로 둔다. 0 으로 채우지 않는다.
        text = "—" if value is None else money_text(value, currency)
        numbers.append(KeyNumber(label, statement, text, slug if slug in GLOSSARY_BY_SLUG else ""))
    sample = get_explainer("operating_margin")
    return FirstRead(
        entry=entry,
        c=company_view(entry.checkup),
        numbers=tuple(numbers),
        name_topic=topic(entry.name),
        sample_metric_label=sample.label,
        sample_metric_easy=sample.easy_name,
        sample_formula=sample.formula,
    )


# ── 용어집 ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TermLink:
    path: str
    text: str


#: 용어집 묶음 — 묶음이 시작하는 용어 slug → 제목. 용어집(explain/glossary.py)의 주석 묶음과 같은 차례.
GLOSSARY_SECTIONS: dict[str, str] = {
    "dart": "재무제표와 보고서",
    "revenue": "손익",
    "assets": "재무상태",
    "operating-cash-flow": "현금흐름",
    "capital-impairment": "위험한 상태",
    "audit-report": "감사",
    "rights-offering": "주식·자금 조달",
    "ksic": "비교·통계",
}


@dataclass(frozen=True)
class TermSection:
    title: str
    terms: tuple[TermView, ...]


@dataclass(frozen=True)
class TermView:
    t: GlossaryTerm
    links: tuple[TermLink, ...]
    see_also: tuple[GlossaryTerm, ...]


#: 용어 → 그 말을 실제로 쓰는 사이트 페이지 (지표·위험 신호·공시 유형 링크 말고). 정적 표.
GLOSSARY_PAGE_LINKS: dict[str, tuple[TermLink, ...]] = {
    "peer-group": (TermLink("s/", "업종 목록"),),
    "ksic": (TermLink("learn/sectors/", "업종별 읽는 법"), TermLink("s/", "업종 목록")),
    "median": (TermLink("market/", "전체 상장사 분포"),),
    "percentile": (TermLink("market/", "전체 상장사 분포"),),
    "dart": (TermLink("learn/disclosures/#how-to-read", "DART 원문 보는 법"),),
    "annual-report": (TermLink("learn/first-read/", "재무제표 처음 읽기"),),
}


def term_view(t: GlossaryTerm) -> TermView:
    links = list(GLOSSARY_PAGE_LINKS.get(t.slug, ()))
    links += [TermLink(f"m/{key}/", get_explainer(key).label) for key in t.metrics]
    flags = {e.key: e for e in red_flag_explainers()}
    links += [TermLink(f"learn/redflags/#{key}", flags[key].title) for key in t.red_flags]
    links += [TermLink(f"learn/disclosures/#{kind.value}", kind.label) for kind in t.disclosures]
    return TermView(t, tuple(links), tuple(GLOSSARY_BY_SLUG[s] for s in t.see_also))


def glossary_sections() -> tuple[TermSection, ...]:
    sections: list[tuple[str, list[TermView]]] = []
    for t in GLOSSARY:
        if t.slug in GLOSSARY_SECTIONS or not sections:
            sections.append((GLOSSARY_SECTIONS.get(t.slug, "용어"), []))
        sections[-1][1].append(term_view(t))
    return tuple(TermSection(title, tuple(views)) for title, views in sections)


# ── 페이지 ─────────────────────────────────────────────────────────


@page("learn")
def learn_pages(site: Site) -> Iterator[Output]:
    yield site.render("learn/index.html", "learn/index.html", legend=LEGEND, guides=GUIDES)
    yield site.render(
        "learn/first_read.html",
        "learn/first-read/index.html",
        fr=first_read(site),
        legend=LEGEND,
        rule_text=RULE_TEXT,
        rounding_note=ROUNDING_NOTE,
        glossary_path=glossary_path,
        next_reads=next_reads("learn/first-read/"),
    )
    yield site.render(
        "learn/redflags.html",
        "learn/redflags/index.html",
        flags=red_flag_explainers(),
        next_reads=next_reads("learn/redflags/"),
    )
    yield site.render(
        "learn/disclosures.html",
        "learn/disclosures/index.html",
        kinds=disclosure_explainers(),
        how_to_read=HOW_TO_READ_ON_DART,
        next_reads=next_reads("learn/disclosures/"),
    )
    yield site.render(
        "learn/glossary.html",
        "learn/glossary/index.html",
        sections=glossary_sections(),
        next_reads=next_reads("learn/glossary/"),
    )
