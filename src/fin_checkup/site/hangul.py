"""한글 검색 보조 — 회사명 정규화와 초성 추출 (빌드 때 미리 계산해 검색 인덱스에 넣는다).

`ㅅㅅㅈㅈ` 로 삼성전자를 찾게 하려면 회사마다 초성 문자열이 있어야 한다. 브라우저에서 매번
분해하는 대신 빌드 때 한 번 만들어 두고, JS(`static/search.js`)는 부분 문자열만 비교한다.
JS 의 `norm()` 은 `normalize_name` 과 같은 규칙이어야 한다.
"""

from __future__ import annotations

import re

#: 키보드로 치는 호환 자모(U+3131~). 첫소리 자모(U+1100~)로 만들면 입력과 안 맞는다.
CHOSUNG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_SYLLABLE_FIRST, _SYLLABLE_LAST = 0xAC00, 0xD7A3
#: 초성 하나가 묶는 음절 수 (중성 21 × 종성 28).
_PER_INITIAL = 21 * 28
_JAMO_FIRST, _JAMO_LAST = 0x3131, 0x314E

_NOISE = re.compile(r"\s+|\(주\)|㈜|주식회사")


def normalize_name(name: str) -> str:
    """검색용 이름: 소문자, 공백·`(주)`·`주식회사` 제거."""
    return _NOISE.sub("", name).lower()


def chosung(text: str) -> str:
    """한글 음절은 초성으로, 영숫자·자모는 그대로, 나머지(기호)는 버린다."""
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if _SYLLABLE_FIRST <= code <= _SYLLABLE_LAST:
            out.append(CHOSUNG[(code - _SYLLABLE_FIRST) // _PER_INITIAL])
        elif (ch.isascii() and ch.isalnum()) or _JAMO_FIRST <= code <= _JAMO_LAST:
            out.append(ch)
    return "".join(out)
