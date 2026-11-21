"""PNG 에 쓸 한국어 글꼴 찾기.

순서: 설정(`FIN_CHECKUP_FONT_REGULAR`·`FIN_CHECKUP_FONT_BOLD`) → 알려진 경로(`CANDIDATES`)
→ `fc-list :lang=ko`.
찾은 글꼴은 한글을 실제로 그리는지 확인한다(`has_hangul`) — 한글이 없는 글꼴로 그리면 글자마다
같은 두부(□)가 찍힌다. 끝내 못 찾으면 None 이고, 호출하는 쪽이 PNG 를 건너뛰며 경고한다.

CI(GitHub Actions ubuntu)는 `fonts-noto-cjk` 를 깔아 첫 후보(`NotoSansCJK-*.ttc`)로 잡힌다.
`.ttc` 는 한 파일에 일·한·중 글꼴이 들어 있어 이름에 'KR' 이 든 면을 고른다(`_korean_index`).
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

#: (보통, 굵게) 경로. 앞에서부터 쓴다.
CANDIDATES: tuple[tuple[str, str], ...] = (
    # Debian·Ubuntu `fonts-noto-cjk` (CI 가 까는 것)
    (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ),
    # Arch `noto-fonts-cjk` · Fedora `google-noto-sans-cjk-fonts`
    ("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc"),
    (
        "/usr/share/fonts/google-noto-sans-cjk-fonts/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/google-noto-sans-cjk-fonts/NotoSansCJK-Bold.ttc",
    ),
    # Debian·Ubuntu `fonts-nanum`
    (
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    ),
    # macOS · Windows
    ("/System/Library/Fonts/AppleSDGothicNeo.ttc", "/System/Library/Fonts/AppleSDGothicNeo.ttc"),
    ("C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/malgunbd.ttf"),
)

INSTALL_HINT = (
    "한국어 글꼴을 찾지 못했다 — `sudo apt-get install fonts-noto-cjk` 로 깔거나 "
    "FIN_CHECKUP_FONT_REGULAR·FIN_CHECKUP_FONT_BOLD 에 .ttf/.otf/.ttc 경로를 지정할 것."
)


@dataclass(frozen=True)
class FontFace:
    path: str
    index: int = 0


@dataclass(frozen=True)
class FontSet:
    """보통·굵게 한 벌. 프로세스 사이로 넘길 수 있게 경로만 든다."""

    regular: FontFace
    bold: FontFace

    def font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        face = self.bold if bold else self.regular
        return _load(face.path, face.index, size)


@lru_cache(maxsize=256)
def _load(path: str, index: int, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size, index=index)


def has_hangul(face: FontFace) -> bool:
    """이 글꼴이 한글을 그리는가. 없는 글자는 전부 같은 .notdef 모양이라 '가'와 '힣'이 똑같이 찍힌다."""
    try:
        font = _load(face.path, face.index, 40)
    except OSError:
        return False
    a, b = font.getmask("가"), font.getmask("힣")
    if a.getbbox() is None:
        return False
    return a.size != b.size or bytes(a) != bytes(b)


def _korean_index(path: str) -> int:
    """.ttc 안에서 한국어 면. 이름에 KR·Korean 이 든 면이 없으면 0."""
    if not path.lower().endswith(".ttc"):
        return 0
    for index in range(32):
        try:
            family = ImageFont.truetype(path, 12, index=index).getname()[0] or ""
        except OSError:
            break
        if " KR" in family or "Korean" in family:
            return index
    return 0


def _face(path: str, index: int | None = None) -> FontFace | None:
    expanded = str(Path(path).expanduser())
    if not Path(expanded).is_file():
        return None
    face = FontFace(expanded, _korean_index(expanded) if index is None else index)
    return face if has_hangul(face) else None


def _pair(regular: str, bold: str) -> FontSet | None:
    reg = _face(regular)
    if reg is None:
        return None
    return FontSet(regular=reg, bold=_face(bold) or reg)


def _from_fc_list() -> FontSet | None:
    """fontconfig 가 아는 한국어 산세리프. 명조·세리프는 고르지 않는다(작은 글씨가 흐려진다)."""
    if shutil.which("fc-list") is None:
        return None
    try:
        out = subprocess.run(
            ["fc-list", ":lang=ko", "--format", "%{file}\t%{index}\t%{style}\t%{family}\n"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    regular: FontFace | None = None
    bold: FontFace | None = None
    for line in sorted(out.splitlines()):
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        path, index, style, family = parts
        if any(word in family for word in ("Serif", "Myeongjo", "Batang", "Mono")):
            continue
        styles = style.split(",")[0].strip().lower()
        face = _face(path, int(index) if index.isdigit() else 0)
        if face is None:
            continue
        if styles in ("regular", "normal", "book") and regular is None:
            regular = face
        elif styles == "bold" and bold is None:
            bold = face
    if regular is None:
        regular = bold
    if regular is None:
        return None
    return FontSet(regular=regular, bold=bold or regular)


def find_fonts(regular: str = "", bold: str = "") -> FontSet | None:
    """설정 → 후보 경로 → fc-list.

    설정한 경로가 있는데 한글이 안 되면 다른 데서 찾지 않는다 — 설정이 틀린 걸 감추지 않게.
    """
    if regular:
        return _pair(regular, bold or regular)
    for reg, bld in CANDIDATES:
        found = _pair(reg, bld)
        if found is not None:
            return found
    return _from_fc_list()


@lru_cache(maxsize=1)
def resolve_fonts() -> FontSet | None:
    """설정을 읽어 한 번만 찾는다."""
    from fin_checkup.config import settings

    return find_fonts(settings.fin_checkup_font_regular, settings.fin_checkup_font_bold)
