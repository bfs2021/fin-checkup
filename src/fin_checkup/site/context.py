"""빌드 한 번이 공유하는 것 — 데이터 기준 연도, 회사 목록, 템플릿 렌더.

링크는 전부 **상대경로**다. 페이지 깊이만큼 `../` 를 붙인 `root` 를 템플릿에 넘기고,
템플릿은 `url('c/005930/')` 로 링크를 만든다. 그래서 GitHub Pages 프로젝트 사이트
(`/fin-checkup/`)든 도메인 루트든 로컬 `python -m http.server` 든 같은 산출물이 동작한다.

`base_url` 은 절대주소가 꼭 필요한 곳(canonical·sitemap·OG)만 쓴다 — `site.absolute_url(path)`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from posixpath import normpath
from typing import Any

from jinja2 import Environment

from fin_checkup.models import CorpCode
from fin_checkup.service import Checkup
from fin_checkup.site.registry import Output


@dataclass(frozen=True)
class CompanyEntry:
    """사이트에 페이지가 생기는 회사 하나."""

    corp: CorpCode
    checkup: Checkup

    @property
    def stock_code(self) -> str:
        return self.corp.stock_code

    @property
    def name(self) -> str:
        return self.corp.corp_name

    @property
    def path(self) -> str:
        """회사 페이지의 사이트 내 경로(디렉터리). 링크는 `url(entry.path)`."""
        return f"c/{self.stock_code}/"


def root_for(output_path: str) -> str:
    """출력 경로에서 사이트 루트로 가는 상대경로. `c/005930/index.html` → `../../`."""
    depth = output_path.count("/")
    return "./" if depth == 0 else "../" * depth


def safe_output_path(path: str) -> str:
    """출력 폴더 밖으로 나가는 경로를 거부한다. 종목코드는 DB 에서 오는 값이다."""
    normalized = normpath(path)
    if (
        not path
        or path.startswith("/")
        or "\\" in path
        or normalized.startswith("..")
        or normalized != path.rstrip("/")
    ):
        raise ValueError(f"허용하지 않는 출력 경로: {path!r}")
    return normalized


@dataclass
class Site:
    year: int
    built_on: date
    env: Environment
    companies: list[CompanyEntry] = field(default_factory=list)
    #: 절대주소용. 끝은 항상 '/'. 예: https://younghwan91.github.io/fin-checkup/
    base_url: str = "/"

    def __post_init__(self) -> None:
        if not self.base_url.endswith("/"):
            self.base_url += "/"

    def absolute_url(self, path: str = "") -> str:
        return self.base_url + path.lstrip("/")

    def render(self, template: str, output_path: str, **context: Any) -> Output:
        """템플릿 하나를 출력 경로에 렌더한다. root·site 는 자동으로 들어간다."""
        path = safe_output_path(output_path)
        html = self.env.get_template(template).render(
            site=self, root=root_for(path), page_path=path, **context
        )
        return Output(path, html)
