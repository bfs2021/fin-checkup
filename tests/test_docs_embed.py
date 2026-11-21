"""`docs/embed.md` 의 붙이는 코드가 회사 페이지가 실제로 내는 코드와 같은지.

문서의 예시는 삼성전자(005930) · 2024 · Pages 주소다. 배지 경로나 alt 문구가 바뀌면 문서도 따라 바뀌어야
블로거가 복사한 코드가 깨지지 않는다.
"""

from __future__ import annotations

import html
import re
from datetime import date
from pathlib import Path

from hub_seed import seed_site_cache

from fin_checkup.site.build import build_site
from fin_checkup.storage import Cache

DOC = Path(__file__).resolve().parents[1] / "docs" / "embed.md"
SITE_URL = "https://younghwan91.github.io/fin-checkup/"


async def test_embed_doc_snippets_match_the_company_page(tmp_path):
    with Cache(tmp_path / "site.duckdb") as cache:
        seed_site_cache(cache)
        out = tmp_path / "out"
        await build_site(cache, out, 2024, base_url=SITE_URL, built_on=date(2026, 11, 21))
    page = (out / "c" / "005930" / "index.html").read_text(encoding="utf-8")
    embed = page[page.index('id="embed"') :]
    blocks = re.findall(r'<pre class="fc-code-block"><code>(.*?)</code></pre>', embed)
    snippets = [html.unescape(s) for s in blocks]
    assert len(snippets) == 2  # 마크다운 · HTML

    doc = DOC.read_text(encoding="utf-8")
    for snippet in snippets:
        assert snippet in doc, snippet


def test_every_embed_snippet_in_the_doc_links_back_to_the_company_page():
    doc = DOC.read_text(encoding="utf-8")
    badges = re.findall(r"badge/(\w{6})\.svg", doc)
    assert badges
    for line in doc.splitlines():
        if "badge/" in line and (line.startswith("[![") or line.startswith("<a ")):
            code = re.search(r"badge/(\w{6})\.svg", line).group(1)
            assert f"{SITE_URL}c/{code}/" in line, line
