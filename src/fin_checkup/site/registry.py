"""페이지 레지스트리 — 페이지 종류마다 모듈 하나, 중앙 목록 없이.

새 페이지 종류를 더하려면 `fin_checkup/site/pages/` 에 모듈 하나를 만들고 빌더 함수에
`@page("이름")` 을 붙인다. `load_pages()` 가 그 패키지의 모듈을 전부 import 하므로 다른
파일을 고칠 필요가 없다::

    # src/fin_checkup/site/pages/sector.py
    from fin_checkup.site.registry import page

    @page("sector")
    def sector_pages(site):
        for label, members in ...:
            yield site.render("sector/index.html", f"s/{label}/index.html", members=members)

빌더는 `Site`(context.py) 를 받아 `Output` 을 내놓는 이터러블이면 된다. 경로는 출력 폴더
기준 상대경로(`c/005930/index.html`)이고, `..` 나 절대경로는 빌드가 거부한다.

회사 페이지에 섹션을 더하는 쪽은 `@company_context("이름")` 으로 그 섹션이 쓸 값을 보탠다.
함수는 `(entry, site) -> dict` 이고, 돌려준 dict 가 회사 템플릿 컨텍스트에 합쳐진다.
템플릿 쪽은 `templates/company/_<섹션>.html` 파일 하나 + `company/index.html` 의 include 한 줄.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fin_checkup.site.context import CompanyEntry, Site


@dataclass(frozen=True)
class Output:
    """빌드가 쓸 파일 하나. path 는 출력 폴더 기준 POSIX 상대경로."""

    path: str
    content: str | bytes


PageBuilder = Callable[["Site"], Iterable[Output]]
CompanyContext = Callable[["CompanyEntry", "Site"], dict[str, Any]]

#: 페이지 이름 → 빌더. `@page` 가 채운다.
PAGES: dict[str, PageBuilder] = {}
#: 이름 → 회사 페이지 컨텍스트 공급자. `@company_context` 가 채운다.
COMPANY_CONTEXTS: dict[str, CompanyContext] = {}


def page(name: str) -> Callable[[PageBuilder], PageBuilder]:
    """페이지 빌더를 등록한다. 같은 이름을 두 번 쓰면 실패한다 — 조용히 덮으면 페이지가 사라진다."""

    def register(builder: PageBuilder) -> PageBuilder:
        _register(PAGES, name, builder, "page")
        return builder

    return register


def company_context(name: str) -> Callable[[CompanyContext], CompanyContext]:
    """회사 페이지 템플릿에 값을 보태는 함수를 등록한다."""

    def register(provider: CompanyContext) -> CompanyContext:
        _register(COMPANY_CONTEXTS, name, provider, "company_context")
        return provider

    return register


def _register(table: dict, name: str, fn: Callable, kind: str) -> None:
    existing = table.get(name)
    if existing is not None and existing is not fn:
        # 모듈을 다시 import 하면 같은 이름의 새 함수 객체가 온다. 정의 위치가 같으면 교체한다.
        same_origin = (existing.__module__, existing.__qualname__) == (fn.__module__, fn.__qualname__)
        if not same_origin:
            raise ValueError(f"{kind} '{name}' 가 이미 등록돼 있다 ({existing.__module__}).")
    table[name] = fn


def load_pages() -> dict[str, PageBuilder]:
    """`fin_checkup.site.pages` 의 모든 모듈을 import 해 등록을 끝낸다. 여러 번 불러도 된다."""
    from fin_checkup.site import pages

    for module in pkgutil.iter_modules(pages.__path__):
        importlib.import_module(f"{pages.__name__}.{module.name}")
    return PAGES
