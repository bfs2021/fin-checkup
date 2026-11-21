"""금지 문구 린트 — 템플릿·해설 데이터·빌드된 HTML 에 추천·매매 권유·재촉 표현이 없다.

같은 검사를 `cli site check` 가 실제 빌드에 돌린다(`site/guard.py` 의 `banned` 규칙).
"""

from __future__ import annotations

import json

import pytest

from fin_checkup.disclaimer import DISCLAIMER
from fin_checkup.explain import banned
from fin_checkup.site import guard
from fin_checkup.site.guard import check_file, check_site, check_sources

CSP = '<meta http-equiv="Content-Security-Policy" content="default-src \'self\'">'


def page(body: str) -> bytes:
    return (
        f'<html lang="ko"><head>{CSP}</head><body><a href="#main">본문으로</a>'
        f'<header><nav><a href="./">홈</a></nav></header><main id="main">{body}</main>'
        f"<footer><p>{DISCLAIMER}</p></footer></body></html>"
    ).encode()


# ── 소스 ───────────────────────────────────────────────────────────


def test_templates_and_explain_texts_are_clean():
    assert check_sources() == []


def test_explain_texts_cover_every_text_module():
    modules = {where.split(":")[0] for where, _ in banned.explain_texts()}
    for name in ("metrics", "glossary", "redflags", "disclosures", "sectors"):
        assert f"explain/{name}.py" in modules
    assert "explain/banned.py" not in modules, "금지 목록 자신은 검사 대상이 아니다"


def test_template_lint_reads_templates_but_ignores_jinja_comments(tmp_path, monkeypatch):
    (tmp_path / "company").mkdir()
    (tmp_path / "company" / "_bad.html").write_text("<p>지금 바로 확인하세요</p>", encoding="utf-8")
    (tmp_path / "ok.html").write_text(
        "{# 여기에 '추천' 같은 말을 쓰지 않는다 #}<p>계산식</p>", encoding="utf-8"
    )
    monkeypatch.setattr(guard, "TEMPLATES", tmp_path)
    found = [v for v in check_sources() if v.path.startswith("templates/")]
    assert [(v.path, v.rule) for v in found] == [("templates/company/_bad.html", "banned")]


# ── 문구 ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "이 종목을 추천합니다",
        "지금 매수할 때",
        "매도 신호",
        "지금 사세요",
        "얼른 파세요",
        "유망 종목",
        "주목할 회사",
        "TOP 10",
        "우량주 모음",
        "저평가 구간",
        "고평가 경고",
        "급등 예상",
        "대박 기회",
        "놓치지 마세요",
        "지금 바로 확인",
    ],
)
def test_recommendation_and_urgency_wording_is_caught(text):
    assert banned.find_outside_allowed(text)


def test_only_exact_allowed_sentences_pass():
    allowed = banned.ALLOWED_SENTENCES[0]
    assert banned.find_outside_allowed(f"면책: {allowed}") == []
    # 같은 단어가 허용 문장 밖에도 있으면 걸린다.
    assert banned.find_outside_allowed(f"{allowed} 대신 이 종목을 추천합니다.") == ["추천"]
    # 한 글자만 달라도 허용 문장이 아니다 — 부정이 빠진 변형을 정규식으로 봐주지 않는다.
    assert banned.find_outside_allowed("종목 추천이나 투자 판단은 합니다.") == ["추천"]


def test_allowed_sentences_are_negated_disclaimers_that_need_the_exception():
    for sentence in banned.ALLOWED_SENTENCES:
        assert banned.find(sentence), f"금지 표현이 없는 문장은 허용목록에 둘 이유가 없다: {sentence}"
        assert any(neg in sentence for neg in ("않", "아닙", "아니")), f"부정문이 아니다: {sentence}"
        assert sentence.endswith("."), "문장 전체(마침표까지)를 적는다"


def test_proper_nouns_are_data_not_wording():
    assert banned.find_outside_allowed("대박엔터 (123456) 재무 신호등", ["대박엔터"]) == []
    assert banned.find_outside_allowed("대박엔터, 대박 기회", ["대박엔터"]) == ["대박"]


# ── 빌드된 HTML ────────────────────────────────────────────────────


def test_built_html_with_banned_wording_fails():
    assert [v.rule for v in check_file("c/1/index.html", page("<p>놓치지 마세요!</p>"))] == ["banned"]
    assert check_file("data.json", "추천".encode()) == [], "HTML 만 본다 (JSON 은 데이터)"


def test_company_names_from_the_search_index_are_not_flagged(tmp_path):
    out = tmp_path / "out"
    (out / "c" / "123456").mkdir(parents=True)
    (out / "c" / "123456" / "index.html").write_bytes(page("<h1>대박엔터 123456</h1>"))
    index = {"companies": [{"name": "대박엔터", "code": "123456"}]}
    (out / "search-index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    assert check_site(out, sources=False) == []

    (out / "search-index.json").unlink()
    assert [v.rule for v in check_site(out, sources=False)] == ["banned"]
