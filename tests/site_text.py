"""화면 HTML 을 글자 기준으로 비교할 때 — CSS 신호 모양(.fc-mark)을 원래 이모지로 되돌린다.

사이트 화면은 신호를 이모지 대신 모양(`_signal.html`, `render.signal_marks`)으로 그린다. 문장 데이터
(`explain`·`groups`)는 이모지를 그대로 가지고 있으니, 그 문장이 페이지에 실렸는지 보려면 되돌려 견준다.
"""

from __future__ import annotations

import re

from fin_checkup.metrics.signals import Signal

_EMOJI = {s.value: s.emoji for s in Signal}
_MARK = r'<span class="fc-mark mark-(\w+)" aria-hidden="true"></span>'


def unmark(text: str) -> str:
    text = re.sub(
        _MARK + r'<span class="fc-visually-hidden">[^<]*</span>', lambda m: _EMOJI[m.group(1)], text
    )
    return re.sub(_MARK, lambda m: _EMOJI[m.group(1)] + " ", text)
