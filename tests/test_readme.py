"""README 가 지키는 것 — 깨진 상대 링크, 금지 표현, 회사 페이지 없이 떠도는 배지.

README 첫 화면은 사이트로 보내는 입구다. 상대 경로가 파일 이동으로 깨지거나, 홍보 문구에 "추천" 같은
말이 섞이거나(`docs/REGULATORY.md`), 배지를 근거(회사 페이지) 없이 붙이면(`docs/embed.md`) 첫 화면이
도구가 하지 않는 말을 대신 하게 된다. 사이트 주소가 실제로 열리는지는 네트워크라 여기서 보지 않는다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fin_checkup.explain.banned import find_outside_allowed

ROOT = Path(__file__).resolve().parents[1]
READMES = sorted(ROOT.glob("README*.md"))
SITE_URL = "https://younghwan91.github.io/fin-checkup/"

#: `[글](대상)` · `![글](대상)` · `<img src="대상">` · `<a href="대상">`
_LINK = re.compile(r"\]\(([^)\s]+)\)|(?:src|href)=\"([^\"]+)\"")


def _relative_targets(text: str) -> list[str]:
    targets = [a or b for a, b in _LINK.findall(text)]
    return [t for t in targets if not re.match(r"[a-z]+:|#", t)]


def test_there_is_a_readme():
    assert ROOT / "README.md" in READMES


@pytest.mark.parametrize("readme", READMES, ids=lambda p: p.name)
def test_relative_links_point_to_existing_files(readme):
    text = readme.read_text(encoding="utf-8")
    missing = [t for t in _relative_targets(text) if not (ROOT / t.split("#")[0]).exists()]
    assert missing == []


@pytest.mark.parametrize("readme", READMES, ids=lambda p: p.name)
def test_readme_links_the_live_site_on_the_first_screen(readme):
    first_screen = "\n".join(readme.read_text(encoding="utf-8").splitlines()[:15])
    assert SITE_URL in first_screen
    assert f"{SITE_URL}c/005930/" in first_screen


def test_korean_readme_has_no_banned_phrases():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert find_outside_allowed(text) == []


@pytest.mark.parametrize("readme", READMES, ids=lambda p: p.name)
def test_badges_in_readme_link_back_to_the_company_page(readme):
    for line in readme.read_text(encoding="utf-8").splitlines():
        for code in re.findall(r"badge/(\w{6})\.svg", line):
            assert f"]({SITE_URL}c/{code}/)" in line or f'href="{SITE_URL}c/{code}/"' in line, line
