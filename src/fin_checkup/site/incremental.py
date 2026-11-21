"""증분 빌드 캐시 — `site build --incremental <폴더>`.

빌드에서 비싼 두 단계만 캐시한다. HTML·JSON 렌더는 싸고(빌드 날짜·사이트 전체 목록이 들어가 회사마다 입력을
나누기 어렵다) 매번 다시 만든다.

1. 회사별 건강검진(`build.collect_companies`) — 열쇠: 코드 판 + **데이터 지문** + 연도 + 회사.
   건강검진의 대조군(동종업계·전체 상장사 분포)이 그해 다른 회사 전부의 값에 기대므로, 한 회사의 입력은
   사실상 그해 데이터 전체다. 그래서 데이터 지문은 회사 하나가 아니라 빌드가 읽는 테이블 전체의 내용 해시다
   (`data_fingerprint`) — 스냅샷이 같으면(매일 공시만 바뀌는 재빌드) 전부 재사용, 바뀌면 전부 다시 계산.
2. 공유 카드 PNG(`pages/og_image.py`) — 열쇠: 코드 판 + 글꼴 + 카드 내용(`OgCard`). 카드에 그려지는 값이
   같으면 데이터가 바뀌어도 다시 그리지 않는다.

코드 판(`code_version`)은 `fin_checkup` 패키지의 모든 소스·템플릿·정적 파일 내용 해시다. 코드가 한 줄이라도
바뀌면 캐시 전체가 무효 — 무엇이 어디에 영향을 주는지 따지지 않는 대신 틀린 재사용이 없다.

캐시 폴더는 `objects/<해시 앞 2자리>/<해시>` 파일들이다. 빌드가 끝나면 이번에 쓰지 않은 객체를 지운다
(`prune`) — 폴더가 끝없이 자라지 않게. Pages 워크플로는 이 폴더를 actions/cache 로 이어 쓴다.
pickle 을 쓰므로 **남이 준 캐시 폴더를 쓰지 않는다** (같은 저장소의 Actions 캐시·로컬 폴더만).
"""

from __future__ import annotations

import hashlib
import os
import pickle
from functools import cache
from pathlib import Path
from typing import Any

import fin_checkup

#: 데이터 지문에 넣는 테이블 — 건강검진이 읽는 것 전부 (storage/db.py).
DATA_TABLES = ("corp_codes", "companies", "statement_lines", "metric_values")
_CODE_SUFFIXES = frozenset({".py", ".html", ".xml", ".svg", ".css", ".js", ".json", ".txt"})


@cache
def code_version() -> str:
    """`fin_checkup` 패키지 소스·템플릿·정적 파일의 내용 해시. 프로세스마다 한 번 계산한다."""
    root = Path(fin_checkup.__file__).parent
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in _CODE_SUFFIXES):
        if "__pycache__" in path.parts:
            continue
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def data_fingerprint(cache_db: Any) -> str:
    """빌드가 읽는 테이블의 내용 해시 (행 수 + 행 해시의 합). 스냅샷을 다시 들여와도 내용이 같으면 같다."""
    digest = hashlib.sha256()
    for table in DATA_TABLES:
        rows, total = cache_db.table_fingerprint(table)
        digest.update(f"{table}:{rows}:{total};".encode())
    return digest.hexdigest()


def fonts_id(fonts: Any) -> str:
    """글꼴 한 벌의 정체 — 경로·번호에 파일 크기·수정 시각까지 (같은 경로에 다른 글꼴이 깔릴 수 있다)."""
    parts = [repr(fonts)]
    for face in (getattr(fonts, "regular", None), getattr(fonts, "bold", None)):
        path = getattr(face, "path", None)
        if path:
            st = os.stat(path)
            parts.append(f"{path}:{st.st_size}:{st.st_mtime_ns}")
    return "|".join(parts)


def key(*parts: object) -> str:
    """열쇠 — 부분들의 repr 을 이어 해시한다. 부분은 repr 이 결정적인 값(문자열·숫자·frozen dataclass)만."""
    digest = hashlib.sha256()
    for part in parts:
        digest.update(repr(part).encode())
        digest.update(b"\x1f")
    return digest.hexdigest()


class BuildCache:
    """내용 주소 객체 저장소. 같은 빌드 안에서 쓰인 열쇠를 기억했다가 `prune` 때 나머지를 지운다."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.objects = self.root / "objects"
        self.objects.mkdir(parents=True, exist_ok=True)
        self.used: set[str] = set()
        self.hits = 0
        self.misses = 0

    def _path(self, k: str) -> Path:
        return self.objects / k[:2] / k

    def get_bytes(self, k: str) -> bytes | None:
        self.used.add(k)
        try:
            data = self._path(k).read_bytes()
        except FileNotFoundError:
            self.misses += 1
            return None
        self.hits += 1
        return data

    def put_bytes(self, k: str, data: bytes) -> None:
        self.used.add(k)
        path = self._path(k)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    _MISSING = object()

    def get_object(self, k: str) -> Any:
        """없으면 `BuildCache.MISSING`. 깨진 객체도 없는 것으로 친다 (다시 계산하면 된다)."""
        data = self.get_bytes(k)
        if data is None:
            return MISSING
        try:
            return pickle.loads(data)  # noqa: S301 — 이 빌드가 쓴 캐시만 읽는다 (모듈 docstring)
        except Exception:  # noqa: BLE001
            self.hits -= 1
            self.misses += 1
            return MISSING

    def put_object(self, k: str, value: Any) -> None:
        self.put_bytes(k, pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL))

    def prune(self) -> int:
        """이번 빌드에서 쓰지 않은 객체를 지운다. 지운 수."""
        removed = 0
        for path in self.objects.glob("*/*"):
            if path.name not in self.used:
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    def summary(self) -> str:
        total = self.hits + self.misses
        return f"증분 캐시 재사용 {self.hits:,}/{total:,}"


MISSING: Any = BuildCache._MISSING
