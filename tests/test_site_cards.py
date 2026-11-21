"""카드뉴스 — 모든 장에 출처·면책, 판 밖으로 넘치는 글자 없음, 금지 표현 없음, 두부(□) 없음.

글자는 OCR 하지 않고 `Canvas.texts`(그린 문자열과 글꼴 지표로 잰 상자)로 본다.
한국어 글꼴이 없는 환경에선 건너뛴다 (CI 는 fonts-noto-cjk 를 깔고, 없으면 test_site_images 가 실패한다).
"""

from __future__ import annotations

import dataclasses
import io

import pytest
from hub_seed import seed_site_cache
from PIL import Image

from fin_checkup.cli import main
from fin_checkup.config import settings
from fin_checkup.disclaimer import DISCLAIMER
from fin_checkup.explain import banned
from fin_checkup.metrics.signals import Signal
from fin_checkup.site.build import collect_companies
from fin_checkup.site.images.cards import (
    HEIGHT,
    SOURCE_NAME,
    WIDTH,
    BannedPhraseError,
    CardDeck,
    MetricBlock,
    Section,
    card_deck,
    draw_deck,
    plain,
)
from fin_checkup.site.images.fonts import missing_glyphs, resolve_fonts
from fin_checkup.storage import Cache


@pytest.fixture(scope="module")
def fonts():
    found = resolve_fonts()
    if found is None:
        pytest.skip("한국어 글꼴 없음 (CI 는 fonts-noto-cjk 를 깐다)")
    return found


@pytest.fixture
async def checkups(tmp_path):
    with Cache(tmp_path / "cards.duckdb") as cache:
        seed_site_cache(cache)
        entries, _ = await collect_companies(cache, 2024)
    return {e.stock_code: e.checkup for e in entries}


def squash(text: str) -> str:
    """줄바꿈·띄어쓰기를 걷어낸다 — 문단이 여러 줄로 나뉘어 그려져도 같은 문장인지 보려고."""
    return "".join(text.split())


def assert_card_rules(canvas, deck, fonts):
    text = canvas.all_text()
    assert squash(DISCLAIMER) in squash(text), "모든 장에 면책 문구 전문"
    assert f"출처: {SOURCE_NAME}" in text and "DART" in text, "모든 장에 출처"
    assert canvas.overflow(margin=24) == [], "판 밖으로 나간 글자·도형"
    assert canvas.collisions() == [], "서로 겹친 글자 (본문이 바닥글을 덮는 등)"
    assert banned.find_outside_allowed(text, [deck.name]) == []
    for line, _box in canvas.texts:
        assert not missing_glyphs(line, fonts.font(24)), f"글꼴에 없는 글자(두부): {line!r}"
        assert not missing_glyphs(line, fonts.font(24, bold=True)), line


@pytest.mark.parametrize("code", ["005930", "105560", "028300"])
async def test_every_card_has_source_disclaimer_and_stays_inside(checkups, fonts, code):
    deck = card_deck(checkups[code])
    pages = draw_deck(deck, fonts)
    assert 5 <= len(pages) <= 6
    for name, canvas in pages:
        assert name.startswith(f"{code}-")
        assert_card_rules(canvas, deck, fonts)


async def test_cards_carry_formula_and_plain_language_why(checkups, fonts):
    deck = card_deck(checkups["005930"])
    text = squash("\n".join(c.all_text() for _, c in draw_deck(deck, fonts)))
    block = deck.sections[0].blocks[0]
    assert squash(f"계산식: {block.formula}") in text
    assert squash(block.why) in text or squash(block.why_short) in text
    # 신호 기호는 도형으로 그리고 글자로는 안 찍는다.
    assert not any(s.emoji in text for s in Signal if s is not Signal.NOT_APPLICABLE)


async def test_bank_cards_say_what_to_look_at_instead(checkups, fonts):
    deck = card_deck(checkups["105560"])
    assert deck.sector_label == "금융업"
    text = squash("\n".join(c.all_text() for _, c in draw_deck(deck, fonts)))
    assert squash("대신 볼 것") in text


async def test_png_size(checkups, fonts):
    (_name, canvas), *_ = draw_deck(card_deck(checkups["005930"]), fonts)
    with Image.open(io.BytesIO(canvas.png())) as image:
        assert image.size == (WIDTH, HEIGHT) == (1080, 1350)


def _stress_deck() -> CardDeck:
    long_why = "아주 긴 설명이 이어지는 경우를 본다. " * 12
    block = MetricBlock(
        label="아주아주 긴 지표 이름 (영문 약칭까지 붙은 경우의 이름)",
        value_text="-12,345,678.90%",
        signal=Signal.RED,
        band="위험 — 기준: 정상 100% 이하 · 주의 200% 이하 · 그 초과는 위험",
        formula="부채총계 ÷ 자기자본 × 100 (연결재무제표의 지배기업 소유주지분 기준으로 다시 계산한 값)",
        why=long_why,
        why_short=long_why,
    )
    return CardDeck(
        name="한국가스공사에스케이하이닉스포스코퓨처엠엘지에너지솔루션우선주",
        stock_code="900000",
        market="KOSDAQ",
        year=2024,
        report_label="사업보고서",
        statement_label="연결재무제표",
        sector_label="부동산업",
        sector_notice="이 회사는 부동산업으로 분류돼 일부 지표를 ‘해당 없음’으로 둡니다. " * 4,
        chips=tuple((s, 9) for s in Signal),
        metric_signals=tuple((f"지표 이름 {i} 아주 길게 늘인 경우", Signal.GREEN) for i in range(17)),
        total=54,
        sections=(Section("수익성", "부제", (block,) * 5),),
        page_url="https://a-very-long-custom-domain.example.com/some/deep/path/fin-checkup/c/900000/",
    )


def test_worst_case_text_still_fits(fonts):
    deck = _stress_deck()
    for _name, canvas in draw_deck(deck, fonts):
        assert_card_rules(canvas, deck, fonts)


def test_a_banned_phrase_stops_the_deck(fonts):
    deck = _stress_deck()
    bad = dataclasses.replace(
        deck, sections=(Section("수익성", "지금 매수할 종목", deck.sections[0].blocks),)
    )
    with pytest.raises(BannedPhraseError):
        draw_deck(bad, fonts)


def test_company_name_with_a_banned_word_is_data_not_advice(fonts):
    """회사 이름은 우리가 쓴 문장이 아니다 — 이름에 금지 표현이 있어도 카드는 나온다."""
    deck = dataclasses.replace(_stress_deck(), name="우량산업")
    assert draw_deck(deck, fonts)


def test_plain_strips_signal_symbols_but_keeps_the_word():
    assert (
        plain("영업이익률 10.88%는 7% 이상이라 🟢 정상이에요") == "영업이익률 10.88%는 7% 이상이라 정상이에요"
    )
    assert plain("업종에 맞지 않는 지표는 ⊘로 표시") == "업종에 맞지 않는 지표는 ‘해당 없음’으로 표시"
    assert plain("부채비율 ⚫ 데이터 없음") == "부채비율 데이터 없음"


def test_missing_glyphs_catches_color_emoji(fonts):
    assert "🟢" in missing_glyphs("정상 🟢", fonts.font(24))
    assert missing_glyphs("정상 7% 이상 · 계산식 ÷ ×", fonts.font(24)) == set()


async def test_cli_writes_the_cards(tmp_path, monkeypatch, fonts, capsys):
    db = tmp_path / "cli.duckdb"
    with Cache(db) as cache:
        seed_site_cache(cache)
    monkeypatch.setattr(settings, "fin_checkup_db_path", db)
    out = tmp_path / "cards"
    assert await _run(["site", "cards", "005930", "--year", "2024", "--out", str(out)]) == 0
    files = sorted(p.name for p in out.iterdir())
    assert files[0] == "005930-1-cover.png" and files[-1].endswith("-read.png")
    assert 5 <= len(files) <= 6
    assert "docs/card-news.md" in capsys.readouterr().out

    assert await _run(["site", "cards", "999999", "--year", "2024", "--out", str(out)]) == 1


async def _run(argv):
    # main() 은 asyncio.run 을 쓴다 — 이미 도는 이벤트 루프 밖(스레드)에서 부른다.
    import asyncio

    return await asyncio.to_thread(main, argv)
