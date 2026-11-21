"""위험 신호 해설이 탐지 코드와 어긋나지 않는지."""

from __future__ import annotations

import ast
import inspect

from fin_checkup.explain import banned
from fin_checkup.explain.redflags import (
    RED_FLAG_EXPLAINERS,
    get_red_flag_explainer,
    red_flag_explainers,
)
from fin_checkup.metrics import redflags
from fin_checkup.metrics.redflags import detect_red_flags
from fin_checkup.models import Financials, FsDiv, ReportCode


def _keys_in_source() -> set[str]:
    """redflags.py 에서 RedFlag(...) 의 첫 인자(key 문자열)를 전부 모은다."""
    tree = ast.parse(inspect.getsource(redflags))
    keys = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "RedFlag"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            keys.add(node.args[0].value)
    return keys


def fin(year: int, **kwargs) -> Financials:
    return Financials(
        corp_code="00000000", bsns_year=year, reprt_code=ReportCode.ANNUAL, fs_div=FsDiv.CFS, **kwargs
    )


def test_every_red_flag_in_code_has_an_explainer_and_vice_versa():
    found = _keys_in_source()
    assert len(found) == 5
    assert set(RED_FLAG_EXPLAINERS) == found


def test_every_field_is_filled():
    for e in red_flag_explainers():
        for text in (e.title, e.what, e.why_matters, e.detection):
            assert text.strip() and "{" not in text, (e.key, text)


def test_detection_quotes_code_thresholds():
    assert (
        f"{redflags.IMPAIRMENT_RATE_MIN}%" in get_red_flag_explainer("partial_capital_impairment").detection
    )
    assert f"{redflags.LOSS_STREAK_MIN}년" in get_red_flag_explainer("consecutive_operating_loss").detection
    zombie = get_red_flag_explainer("zombie_streak").detection
    assert f"{redflags.ZOMBIE_STREAK_MIN}년" in zombie and f"{redflags.ZOMBIE_COVERAGE_MAX} 미만" in zombie


def test_detection_follows_a_changed_constant(monkeypatch):
    monkeypatch.setattr(redflags, "LOSS_STREAK_MIN", 4)
    assert "4년 이상" in get_red_flag_explainer("consecutive_operating_loss").detection
    monkeypatch.setattr(redflags, "IMPAIRMENT_RATE_MIN", 40)
    assert get_red_flag_explainer("partial_capital_impairment").title == "자본잠식률 40% 이상"


def test_detector_actually_uses_the_constants(monkeypatch):
    """해설이 상수를 말하는데 탐지는 리터럴을 쓰면 둘이 갈라진다."""
    history = [fin(2023, operating_income=-1), fin(2024, operating_income=-1)]
    assert not any(f.key == "consecutive_operating_loss" for f in detect_red_flags(history))
    monkeypatch.setattr(redflags, "LOSS_STREAK_MIN", 2)
    assert any(f.key == "consecutive_operating_loss" for f in detect_red_flags(history))

    impaired = [fin(2024, total_equity=600, capital_stock=1000)]  # 잠식률 40%
    assert detect_red_flags(impaired) == []
    monkeypatch.setattr(redflags, "IMPAIRMENT_RATE_MIN", 40)
    assert [f.key for f in detect_red_flags(impaired)] == ["partial_capital_impairment"]

    zombie = [fin(y, operating_income=15, interest_expense=10) for y in (2022, 2023, 2024)]
    assert detect_red_flags(zombie) == []
    monkeypatch.setattr(redflags, "ZOMBIE_COVERAGE_MAX", 2)
    assert [f.key for f in detect_red_flags(zombie)] == ["zombie_streak"]


def test_no_banned_phrase():
    texts = list(banned.iter_strings(red_flag_explainers()))
    texts += [e.title for e in red_flag_explainers()] + [e.detection for e in red_flag_explainers()]
    assert [(t, p) for t in texts for p in banned.find(t)] == []
