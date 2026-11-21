"""캐시 → 회사별 건강검진 → 등록된 페이지 전부 → 출력 폴더.

**DART 를 부르지 않는다.** 인증키를 비운 설정으로 `CheckupService` 를 만들고
`allow_fetch=False` 로 돌린다 — 캐시에 없는 회사·연도는 페이지가 생기지 않을 뿐이다.
데이터 수집은 `scripts/collect_universe.py` 의 일이다.

출력 폴더는 매번 비우고 다시 쓴다(지난 빌드의 회사가 남지 않게). 실수로 다른 폴더를
지우지 않도록, 비어 있지 않은 폴더는 빌드가 남긴 표식(`MARKER`)이 있을 때만 비운다.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from fin_checkup.clock import kst_today
from fin_checkup.config import Settings
from fin_checkup.service import CheckupService
from fin_checkup.site.context import OG_IMAGE_PAGE, CompanyEntry, Site, safe_output_path
from fin_checkup.site.registry import load_pages
from fin_checkup.site.render import make_env
from fin_checkup.storage import Cache

MARKER = ".fin-checkup-site"
#: 추이·급변에 쓰는 연수. 캐시에 있는 해만큼만 쓰인다.
HISTORY_YEARS = 5

Progress = Callable[[int, int], None]


@dataclass(frozen=True)
class BuildReport:
    companies: int
    #: 상장사·재무가 있는데 건강검진을 못 만든 회사 (종목코드 형식 이상 포함).
    skipped: int
    files: int
    load_seconds: float
    render_seconds: float

    @property
    def per_company_ms(self) -> float:
        if not self.companies:
            return 0.0
        return (self.load_seconds + self.render_seconds) / self.companies * 1000


def _offline_service(cache: Cache) -> CheckupService:
    """인증키 없는 서비스. 캐시 미스가 DART 호출로 번질 길을 아예 없앤다."""
    return CheckupService(cache, settings=Settings(_env_file=None, dart_api_key=""))


def _valid_stock_code(code: str) -> bool:
    # KRX 단축코드는 6자리 영숫자(신형은 영문 포함). 경로에 들어가므로 엄격히 본다.
    return len(code) == 6 and code.isascii() and code.isalnum() and code.upper() == code


async def collect_companies(
    cache: Cache,
    year: int,
    limit: int | None = None,
    progress: Progress | None = None,
) -> tuple[list[CompanyEntry], int]:
    """(페이지를 만들 회사, 건너뛴 수). 캐시만 읽는다."""
    service = _offline_service(cache)
    corps = cache.list_listed_with_statements(year)
    if limit is not None:
        corps = corps[:limit]

    entries: list[CompanyEntry] = []
    skipped = 0
    for i, corp in enumerate(corps, start=1):
        data = None
        if _valid_stock_code(corp.stock_code):
            data = await service.run(corp, end_year=year, years=HISTORY_YEARS, allow_fetch=False)
        if data is None or data.history[-1].bsns_year != year:
            skipped += 1
        else:
            entries.append(CompanyEntry(corp=corp, checkup=data))
        if progress is not None:
            progress(i, len(corps))
    return entries, skipped


def _prepare_out(out: Path) -> None:
    if out.exists() and any(out.iterdir()):
        if not (out / MARKER).exists():
            raise FileExistsError(
                f"{out} 가 비어 있지 않고 사이트 빌드 폴더 표식({MARKER})이 없다. "
                "다른 폴더를 지우지 않도록 멈춘다 — 빈 폴더나 새 경로를 지정하세요."
            )
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / MARKER).write_text("fin-checkup site build output — 빌드마다 통째로 지워진다.\n")


async def build_site(
    cache: Cache,
    out: Path,
    year: int,
    limit: int | None = None,
    base_url: str = "/",
    built_on: date | None = None,
    progress: Progress | None = None,
) -> BuildReport:
    started = time.perf_counter()
    entries, skipped = await collect_companies(cache, year, limit, progress)
    loaded = time.perf_counter()

    pages = load_pages()
    site = Site(
        year=year,
        built_on=built_on or kst_today(),
        env=make_env(),
        companies=entries,
        base_url=base_url,
        og_images=OG_IMAGE_PAGE in pages,
    )
    _prepare_out(out)
    files = 0
    for _name, builder in sorted(pages.items()):
        for output in builder(site):
            target = out / safe_output_path(output.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(output.content, bytes):
                target.write_bytes(output.content)
            else:
                target.write_text(output.content, encoding="utf-8")
            files += 1

    return BuildReport(
        companies=len(entries),
        skipped=skipped,
        files=files,
        load_seconds=loaded - started,
        render_seconds=time.perf_counter() - loaded,
    )
