"""해설 문장에 들어가면 안 되는 표현.

해설은 "이 숫자가 무엇이고 왜 이 색인가"까지다. 사고팔라는 말이나 종목을 띄우는 말이
섞이면 측정 도구가 아니라 투자 권유가 된다 (`docs/REGULATORY.md`).
"""

from __future__ import annotations

import dataclasses
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
)


def find(text: str) -> list[str]:
    """text 에 들어 있는 금지 표현 목록 (없으면 빈 목록)."""
    return [phrase for phrase in BANNED_PHRASES if phrase in text]


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
