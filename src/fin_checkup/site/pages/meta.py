"""`<head>` 메타 중 회사마다 다른 값 — 공유 카드 이미지 주소.

제목·설명·canonical·og: 태그 자체는 `templates/base.html` 이 블록(title·description)과
`site.canonical_url(page_path)` 로 만든다. 여기는 회사 페이지에만 있는 `og_image` 하나를 보탠다.
이미지 파일은 `OG_IMAGE_PAGE`(context.py) 이름의 페이지가 만든다 — 그 페이지가 없으면 None 이라 태그도 없다.
"""

from __future__ import annotations

from typing import Any

from fin_checkup.site.context import CompanyEntry, Site
from fin_checkup.site.registry import company_context


@company_context("meta")
def og_image(entry: CompanyEntry, site: Site) -> dict[str, Any]:
    return {"og_image": site.og_image_url(entry.stock_code)}
