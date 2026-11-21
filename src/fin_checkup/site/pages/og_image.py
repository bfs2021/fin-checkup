"""공유 카드 이미지 `/og/<종목코드>.png` (그림은 `site/images/og.py`).

이 페이지가 등록돼 있고 이번 빌드가 PNG 를 만들 때(`--images` + 한국어 글꼴 있음)만 build 가
`site.og_images` 를 켜고, 그래야 회사 페이지가 og:image 를 낸다 — 파일이 없는 주소를 카드로 내보내지 않게.
"""

from __future__ import annotations

from collections.abc import Iterator

from fin_checkup.site.context import OG_IMAGE_PAGE, Site
from fin_checkup.site.images.og import og_card_for, og_path, render_many
from fin_checkup.site.registry import Output, page


def site_label(site: Site) -> str:
    """바닥글에 찍을 주소 — 스킴과 끝 '/' 를 뗀다. 절대주소가 없으면 빈 문자열."""
    if not site.has_absolute_base:
        return ""
    return site.base_url.split("://", 1)[1].rstrip("/")


@page(OG_IMAGE_PAGE)
def og_images(site: Site) -> Iterator[Output]:
    if site.fonts is None:  # build 가 이 페이지를 빼야 했다. 직접 불렸을 때도 두부 PNG 를 내지 않는다.
        return
    label = site_label(site)
    cards = [og_card_for(entry, label) for entry in site.companies]
    for card, png in zip(cards, render_many(cards, site.fonts, site.image_workers), strict=True):
        yield Output(og_path(card.stock_code), png)
