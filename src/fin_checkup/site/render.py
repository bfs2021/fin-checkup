"""Jinja2 환경 — 자동 이스케이프, 정의 안 된 변수는 오류.

회사명은 DB 에서 온다. 이스케이프를 끄면 이름 하나로 페이지에 스크립트가 들어간다.
템플릿엔 판정 로직을 두지 않는다 — 문장·숫자는 `view.py` 가 `presentation`·`format` 으로
미리 만들어 넘기고, 템플릿은 배치만 한다.

템플릿에서 쓸 수 있는 전역:
- `url(path)` — 현재 페이지 기준 상대 링크 (`url('c/005930/')`, `url('')` 은 홈)
- `DISCLAIMER` — 면책 문구 (`fin_checkup.disclaimer`)
- `site` · `root` · `page_path` — `Site.render` 가 넣는다
"""

from __future__ import annotations

from jinja2 import Environment, PackageLoader, StrictUndefined, pass_context, select_autoescape
from jinja2.runtime import Context

from fin_checkup.disclaimer import DISCLAIMER


@pass_context
def _url(context: Context, path: str = "") -> str:
    return context["root"] + path.lstrip("/")


def make_env() -> Environment:
    env = Environment(
        loader=PackageLoader("fin_checkup.site", "templates"),
        autoescape=select_autoescape(enabled_extensions=("html", "xml", "svg"), default=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.globals.update(url=_url, DISCLAIMER=DISCLAIMER)
    return env
