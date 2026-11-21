"""검색 — 이름·종목코드·초성. 인덱스는 빌드 때 만들고, 브라우저는 작은 JS 로 거른다."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from importlib.resources import files

import pytest
from hub_seed import seed_site_cache

from fin_checkup.site.build import build_site
from fin_checkup.site.hangul import chosung, normalize_name
from fin_checkup.storage import Cache

SEARCH_JS = files("fin_checkup.site") / "static" / "search.js"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("삼성전자", "ㅅㅅㅈㅈ"),
        ("SK하이닉스", "skㅎㅇㄴㅅ"),
        ("KB금융", "kbㄱㅇ"),
        ("까뮤이앤씨", "ㄲㅁㅇㅇㅆ"),  # 쌍자음
        ("삼성 전자", "ㅅㅅㅈㅈ"),  # 띄어쓰기는 검색에 방해만 된다
        ("(주)LG", "lg"),
        ("CJ ENM", "cjenm"),
        ("HLB글로벌", "hlbㄱㄹㅂ"),
        ("", ""),
    ],
)
def test_chosung_extracts_initial_consonants(text, expected):
    assert chosung(normalize_name(text)) == expected


def test_chosung_uses_the_jamo_people_type():
    """키보드로 치는 ㅅ 은 호환 자모(U+3145)다. 첫소리 자모(U+1109)로 만들면 아무것도 안 걸린다."""
    assert chosung("삼") == "ㅅ"


@pytest.fixture
async def out(tmp_path):
    with Cache(tmp_path / "site.duckdb") as cache:
        seed_site_cache(cache)
        target = tmp_path / "out"
        await build_site(cache, target, 2024, built_on=date(2026, 11, 21))
    return target


async def test_search_index_lists_every_company_page(out):
    index = json.loads((out / "search-index.json").read_text(encoding="utf-8"))
    assert index["year"] == 2024
    companies = index["companies"]
    assert [c["code"] for c in companies] == ["105560", "005930", "028300"], "이름순 (가나다)"
    samsung = next(c for c in companies if c["code"] == "005930")
    assert samsung == {
        "name": "삼성전자",
        "code": "005930",
        "market": "KOSPI",
        "sector": "일반",
        "chosung": "ㅅㅅㅈㅈ",
    }
    for c in companies:
        assert (out / "c" / c["code"] / "index.html").exists()


async def test_search_index_holds_no_metric_values(out):
    """검색 인덱스는 찾기용이다. 지표 값을 넣으면 순위표로 쓰이기 쉽다."""
    raw = (out / "search-index.json").read_text(encoding="utf-8")
    for word in ("signal", "value", "metric", "score"):
        assert word not in raw


async def test_every_page_loads_the_search_script_relatively(out):
    assert 'src="./assets/search.js"' in (out / "index.html").read_text(encoding="utf-8")
    company = (out / "c" / "005930" / "index.html").read_text(encoding="utf-8")
    assert 'src="../../assets/search.js"' in company
    assert 'data-root="../../"' in company, "JS 는 이 값으로 인덱스·회사 링크를 찾는다 (하위 경로 배포)"
    assert (out / "assets" / "search.js").exists()


# ── JS 매칭 (node 가 있으면 실제로 돌린다) ────────────────────────

ITEMS = [
    {"name": "삼성전자", "code": "005930", "chosung": "ㅅㅅㅈㅈ"},
    {"name": "삼성전자우", "code": "005935", "chosung": "ㅅㅅㅈㅈㅇ"},
    {"name": "삼성SDI", "code": "006400", "chosung": "ㅅㅅsdi"},
    {"name": "SK하이닉스", "code": "000660", "chosung": "skㅎㅇㄴㅅ"},
    {"name": "대한전선", "code": "001440", "chosung": "ㄷㅎㅈㅅ"},
]


def run_search(query: str) -> list[str]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 가 없다")
    script = (
        f"const s = require({json.dumps(str(SEARCH_JS))});"
        f"const r = s.search({json.dumps(ITEMS)}, {json.dumps(query)}, 10);"
        "process.stdout.write(JSON.stringify(r.map(x => x.code)));"
    )
    done = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True, timeout=30)
    return json.loads(done.stdout)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("ㅅㅅㅈㅈ", ["005930", "005935"]),
        ("삼성전자", ["005930", "005935"]),  # 정확히 같은 이름이 먼저
        ("005930", ["005930"]),
        ("0059", ["005930", "005935"]),
        ("하이닉스", ["000660"]),
        ("sk하이", ["000660"]),
        ("SK 하이닉스", ["000660"]),
        ("ㅈㅅ", ["001440"]),
        ("", []),
        ("   ", []),
        ("없는회사", []),
    ],
)
def test_js_search_matches_name_code_and_chosung(query, expected):
    assert run_search(query) == expected


def test_js_search_orders_by_match_then_name_not_by_any_metric():
    # '삼성' 은 셋 다 앞에서 맞는다 → 이름순.
    assert run_search("삼성") == ["006400", "005930", "005935"]
