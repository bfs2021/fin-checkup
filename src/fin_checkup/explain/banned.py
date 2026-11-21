"""해설·화면 문장에 들어가면 안 되는 표현 — 추천·매매 권유·급하게 만드는 말.

해설은 "이 숫자가 무엇이고 왜 이 색인가"까지다. 사고팔라는 말이나 종목을 띄우는 말,
"놓치지 마세요" 같은 재촉이 섞이면 측정 도구가 아니라 투자 권유가 된다 (`docs/REGULATORY.md`).

예외는 정해 둔 문장(`ALLOWED_SENTENCES`)뿐이다 — "추천하지 않는다" 를 정규식으로 느슨하게
봐주면 "추천하지 않을 수 없는 종목" 도 통과한다. 사이트 빌드 산출물·템플릿 검사는
`fin_checkup.site.guard`, 해설 데이터 검사는 `explain_texts()` 가 쓴다.
"""

from __future__ import annotations

import dataclasses
import importlib
import pkgutil
import types
from collections.abc import Iterable, Iterator
from enum import Enum

#: 순서대로 검사한다. 대소문자를 구분한다 — 'TOP' 은 순위표 제목에 쓰이는 표기다.
BANNED_PHRASES: tuple[str, ...] = (
    "추천",
    "매수",
    "매도",
    "사세요",
    "파세요",
    "유망",
    "주목",
    "TOP",
    "우량",
    "저평가",
    "고평가",
    "급등",
    "대박",
    "놓치지",
    "지금 바로",
)

#: 금지 표현이 들어가도 되는 문장 — 그 표현을 **부정하는** 면책 문장만, 글자 그대로.
#: 더할 땐 문장 전체를 적는다(마침표까지). 테스트가 부정형인지·실제로 금지 표현을 담는지 본다.
ALLOWED_SENTENCES: tuple[str, ...] = (
    "종목 추천이나 투자 판단은 하지 않습니다.",
    "투자권유·추천이 아닙니다.",
)


def find(text: str) -> list[str]:
    """text 에 들어 있는 금지 표현 목록 (없으면 빈 목록)."""
    return [phrase for phrase in BANNED_PHRASES if phrase in text]


def find_outside_allowed(text: str, proper_nouns: Iterable[str] = ()) -> list[str]:
    """허용 문장과 고유명사(회사 이름 등 데이터)를 걷어낸 뒤의 금지 표현.

    고유명사는 우리가 쓴 문장이 아니다 — 회사 이름에 '대박' 이 있다고 배포를 막을 수는 없다.
    정확히 같은 문자열만 걷어낸다.
    """
    if not find(text):
        return []
    for sentence in ALLOWED_SENTENCES:
        text = text.replace(sentence, " ")
    # 금지 표현을 품은 이름만 걷어낸다 — 페이지 수천 장 × 회사 이름 수천 개를 다 바꾸면 느리다.
    nouns = {n for n in proper_nouns if n and find(n)}
    for noun in sorted(nouns, key=len, reverse=True):
        text = text.replace(noun, " ")
    return find(text)


def iter_strings(obj: object) -> Iterator[str]:
    """dataclass·튜플·dict 안의 문자열을 전부 꺼낸다. Enum 값은 코드라 건너뛴다."""
    if isinstance(obj, Enum):
        return
    if isinstance(obj, str):
        yield obj
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            yield from iter_strings(getattr(obj, f.name))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from iter_strings(k)
            yield from iter_strings(v)
    elif isinstance(obj, Iterable):
        for item in obj:
            yield from iter_strings(item)


#: 해설 문장이 아닌 모듈 — 금지 목록 자신과 조사 규칙.
_NOT_TEXT_MODULES = frozenset({"banned", "_korean"})


def explain_texts() -> Iterator[tuple[str, str]]:
    """`fin_checkup.explain` 의 모든 해설 데이터 문자열 — (어디, 문장).

    모듈 수준 값(상수·표·dataclass 목록)을 전부 훑는다. 함수가 그때그때 만드는 문장
    (`why.py`)은 그 모듈의 테스트가 결과 문장을 검사한다.
    """
    import fin_checkup.explain as package

    for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda m: m.name):
        if info.name in _NOT_TEXT_MODULES:
            continue
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        for name, value in sorted(vars(module).items()):
            if name.startswith("__") or isinstance(
                value, (types.ModuleType, types.FunctionType, type)
            ) or callable(value):
                continue
            for text in iter_strings(value):
                yield f"explain/{info.name}.py:{name}", text
