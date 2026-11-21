"""찾을 수 없는 주소 `/404.html` — 검색창과 갈 만한 곳.

GitHub Pages 는 없는 주소 **어디에서든** 이 파일을 그대로 돌려준다(`/fin-checkup/c/999999/` 에서도).
그래서 상대 링크(`../../assets/…`)가 깊이에 따라 깨진다 — 이 페이지만 `site.root_path`
(`--base-url` 의 경로 부분, 예: `/fin-checkup/`)를 링크 기준으로 쓴다. sitemap 에서는 빠진다(`sitemap.py`).
"""

from __future__ import annotations

from collections.abc import Iterator

from fin_checkup.site.context import Site
from fin_checkup.site.registry import Output, page

PATH = "404.html"


@page("404")
def not_found_page(site: Site) -> Iterator[Output]:
    yield site.render("404.html", PATH, root=site.root_path)
