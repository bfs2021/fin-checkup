"""빌드 메타 `/build.json` · 꼬리의 데이터 기준 줄 · 사업연도 신선도.

`build.json` 은 빌드가 다른 파일을 다 쓴 뒤 마지막에 쓴다(파일 수를 세야 해서) — `build.py`.
싣는 것: 빌드 시각(KST) · 기준 사업연도와 데이터에 있는 사업연도들 · 기대 사업연도
(`fiscal.default_fiscal_year`)와 그보다 오래됐는지 · 스냅샷 manifest 의 날짜 · git 커밋(앞 12자리) · 개수.

git 커밋은 앞 12자리만 싣는다 — 40자리 16진수는 가드(`guard.py` secret 규칙)가 DART 인증키로 본다.

신선도: 데이터의 가장 최근 사업연도가 `default_fiscal_year(빌드 날짜)` 보다 오래되면 빌드 로그와
`site check` 가 경고한다 (실패는 아니다 — 새 사업연도 수집은 D1, 사람이 판단한다).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fin_checkup.clock import kst_today
from fin_checkup.disclaimer import DISCLAIMER
from fin_checkup.fiscal import default_fiscal_year
from fin_checkup.snapshot import read_manifest

if TYPE_CHECKING:
    from fin_checkup.site.context import CompanyEntry, Site

BUILD_JSON = "build.json"
#: build.json 형식 판. 필드를 빼거나 뜻을 바꾸면 올린다.
SCHEMA_VERSION = 1
SHA_LENGTH = 12

_SHA = re.compile(r"^[0-9a-f]{7,40}$")


@dataclass(frozen=True)
class SnapshotInfo:
    """`snapshot import` 한 스냅샷의 manifest 중 사이트가 보이는 것."""

    built_on: str
    built_at: str
    bsns_years: tuple[int, ...]

    def as_json(self) -> dict[str, Any]:
        return {"built_on": self.built_on, "built_at": self.built_at, "bsns_years": list(self.bsns_years)}


def read_snapshot_info(src_dir: Path | str) -> SnapshotInfo:
    """스냅샷을 푼 폴더(manifest.json 이 있는 곳)에서. 없거나 깨졌으면 `SnapshotError`."""
    manifest = read_manifest(src_dir)
    return SnapshotInfo(
        built_on=str(manifest.get("built_on", "")),
        built_at=str(manifest.get("built_at", "")),
        bsns_years=tuple(int(y) for y in manifest.get("bsns_years") or ()),
    )


def git_sha() -> str | None:
    """빌드한 코드의 커밋 앞 12자리. Actions 는 GITHUB_SHA, 로컬은 git. 모르면 None."""
    sha = os.environ.get("GITHUB_SHA", "").strip().lower()
    if not sha:
        try:
            done = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=Path(__file__).parent,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        sha = done.stdout.strip().lower() if done.returncode == 0 else ""
    return sha[:SHA_LENGTH] if _SHA.match(sha) else None


def data_years(companies: Iterable[CompanyEntry]) -> list[int]:
    """페이지가 생기는 회사들의 계산에 쓰인 사업연도 전부."""
    return sorted({f.bsns_year for e in companies for f in e.checkup.history})


def freshness_warning(newest: int | None, today: date) -> str:
    """가장 최근 사업연도가 기대값보다 오래됐으면 경고 문장, 아니면 빈 문자열."""
    expected = default_fiscal_year(today)
    if newest is not None and newest >= expected:
        return ""
    have = f"{newest} 사업연도" if newest is not None else "사업연도 없음"
    return (
        f"데이터의 가장 최근이 {have}인데 {today.isoformat()} 기준 기대값은 {expected} 사업연도다 "
        f"(fiscal.default_fiscal_year). 새 사업연도 수집·스냅샷이 필요할 수 있다."
    )


def build_json(site: Site, built_at: datetime, sha: str | None, counts: dict[str, int]) -> dict[str, Any]:
    years = data_years(site.companies)
    feed = site.disclosures
    return {
        "schema_version": SCHEMA_VERSION,
        "disclaimer": DISCLAIMER,
        "built_at": built_at.isoformat(timespec="seconds"),
        "built_on": site.built_on.isoformat(),
        "fiscal_year": site.year,
        "fiscal_years_in_data": years,
        "expected_fiscal_year": default_fiscal_year(site.built_on),
        "fresh": not freshness_warning(max(years, default=None), site.built_on),
        "snapshot": site.snapshot.as_json() if site.snapshot else None,
        "disclosures": None
        if feed is None
        else {"begin": feed.begin.isoformat(), "end": feed.end.isoformat(), "count": len(feed.items)},
        "git_sha": sha,
        "counts": counts,
    }


def dump(doc: dict[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=1) + "\n"


def check_freshness(out: Path, today: date | None = None) -> str:
    """빌드 폴더의 build.json 으로 신선도 경고 (`site check`). build.json 이 없으면 빈 문자열."""
    path = out / BUILD_JSON
    if not path.is_file():
        return ""
    try:
        years = json.loads(path.read_text(encoding="utf-8")).get("fiscal_years_in_data") or []
    except (ValueError, AttributeError):
        return f"{BUILD_JSON} 를 읽지 못했다"
    return freshness_warning(max((int(y) for y in years), default=None), today or kst_today())
