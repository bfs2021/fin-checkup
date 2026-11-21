"""빌드된 사이트의 가드 — 넘지 않는 선을 산출물에서 직접 확인한다.

    uv run python -m fin_checkup.cli site check site-out

테스트(`tests/test_site_guard.py`)는 픽스처로 빌드한 사이트에, Pages 워크플로는 실제 빌드에
같은 `check_site` 를 돌린다. 템플릿을 고쳐 선을 넘으면 배포 전에 막힌다.

규칙 (`Violation.rule`)
- `disclaimer`  모든 HTML 에 면책 문구(`DISCLAIMER`)가 그대로 있다.
- `basis`       판정한 지표(🟢🟡🔴)마다 계산식과 경계값이 비어 있지 않게 적혀 있다.
                지표 카드(`.fc-metric`)는 판정과 무관하게 계산식을 적는다.
- `csp`         모든 HTML 에 CSP `<meta>` — default-src 'self', unsafe-eval 없음,
                unsafe-inline 은 style-src 에만, 그것도 인라인 스타일이 실제로 있을 때만.
- `script`      다른 사이트의 스크립트·스타일·이미지를 싣지 않는다. 인라인 실행 스크립트 없음.
- `handler`     인라인 이벤트 핸들러(`onclick=` …)·`javascript:` 주소 없음.
- `storage`     쿠키·sessionStorage·indexedDB 없음. localStorage 는 `fin-checkup:` 키만.
- `secret`      DART 인증키처럼 생긴 40자리 16진수·`crtfc_key` 가 어떤 파일에도 없다.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from fin_checkup.disclaimer import DISCLAIMER

#: 판정한 신호. 이 신호의 지표는 경계값을 반드시 보여야 한다 — 왜 이 색인지 감추지 않는다.
JUDGED_SIGNALS = frozenset({"sig-green", "sig-yellow", "sig-red"})
#: 브라우저 저장소에 쓸 수 있는 키의 접두사 (관심종목 등, 이 기기 안에서만).
STORAGE_PREFIX = "fin-checkup:"
#: 실행되지 않는 데이터 블록. CSP 와 무관하게 허용한다.
DATA_SCRIPT_TYPES = frozenset({"application/ld+json", "application/json"})

_VOID = frozenset("area base br col embed hr img input link meta source track wbr".split())
#: 자원을 불러오는 태그와 그 주소 속성. `<a href>` 는 이동이라 외부도 괜찮다.
_LOADERS = {
    "script": "src",
    "link": "href",
    "img": "src",
    "iframe": "src",
    "source": "src",
    "embed": "src",
    "object": "data",
    "audio": "src",
    "video": "src",
}
_OFFSITE = re.compile(r"^\s*(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//)")
_HEX40 = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{40}(?![0-9a-fA-F])")
_STORAGE_BANNED = re.compile(r"document\s*\.\s*cookie|sessionStorage|indexedDB")
_LOCAL_STORAGE = re.compile(r"localStorage")
_LOCAL_STORAGE_OK = re.compile(
    r"localStorage\.(?:getItem|setItem|removeItem)\(\s*([\"'`])" + re.escape(STORAGE_PREFIX)
)
_TEXT_SUFFIXES = frozenset({".html", ".js", ".css", ".json", ".xml", ".txt", ".svg", ".webmanifest"})


@dataclass(frozen=True)
class Violation:
    #: 출력 폴더 기준 POSIX 경로. 사이트 전체에 걸친 규칙은 빈 문자열.
    path: str
    rule: str
    detail: str

    def __str__(self) -> str:
        where = self.path or "(사이트 전체)"
        return f"{where}: [{self.rule}] {self.detail}"


@dataclass
class _Card:
    """`.fc-metric` 카드 하나에서 모은 것."""

    classes: set[str]
    ident: str
    depth: int
    #: (dt 글자, dd 글자) 쌍.
    basis: list[tuple[str, str]] = field(default_factory=list)


class _PageScan(HTMLParser):
    """HTML 한 장에서 가드가 볼 것만 모은다. 템플릿이 태그를 닫는다는 전제(Jinja 산출물)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.csp: list[str] = []
        self.loads: list[tuple[str, str]] = []
        self.inline_scripts = 0
        self.handlers: list[str] = []
        self.js_urls: list[str] = []
        self.inline_styles = 0
        self.cards: list[_Card] = []
        self._open_cards: list[_Card] = []
        self._dt: list[str] | None = None
        self._dd: list[str] | None = None
        self._pending_dt = ""
        self._script_inline = False
        self._script_text: list[str] = []

    # -- 태그 ------------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        for name, value in a.items():
            if name.startswith("on"):
                self.handlers.append(f"<{tag} {name}=…>")
            if name in {"href", "src", "action", "formaction", "data"} and value.strip().lower().startswith(
                "javascript:"
            ):
                self.js_urls.append(f"<{tag} {name}={value[:40]}>")
        if "style" in a:
            self.inline_styles += 1
        if tag == "style":
            self.inline_styles += 1
        if tag == "meta" and a.get("http-equiv", "").lower() == "content-security-policy":
            self.csp.append(a.get("content", ""))
        attr = _LOADERS.get(tag)
        if attr and a.get(attr):
            self.loads.append((tag, a[attr]))
        if tag == "script":
            self._script_inline = not a.get("src") and a.get("type", "").lower() not in DATA_SCRIPT_TYPES
            self._script_text = []

        if tag in _VOID:
            return
        self.stack.append(tag)
        classes = set(a.get("class", "").split())
        if "fc-metric" in classes:
            card = _Card(classes=classes, ident=a.get("id", ""), depth=len(self.stack))
            self._open_cards.append(card)
        if self._open_cards:
            if tag == "dt":
                self._dt = []
            elif tag == "dd":
                self._dd = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID or tag not in self.stack:
            return
        if tag == "script" and self._script_inline and "".join(self._script_text).strip():
            self.inline_scripts += 1
        if self._open_cards:
            if tag == "dt" and self._dt is not None:
                self._pending_dt = " ".join("".join(self._dt).split())
                self._dt = None
            elif tag == "dd" and self._dd is not None:
                self._open_cards[-1].basis.append((self._pending_dt, " ".join("".join(self._dd).split())))
                self._dd = None
        while self.stack:
            closed = self.stack.pop()
            if self._open_cards and self._open_cards[-1].depth == len(self.stack) + 1:
                self.cards.append(self._open_cards.pop())
            if closed == tag:
                break

    def handle_data(self, data: str) -> None:
        if self.stack and self.stack[-1] == "script":
            self._script_text.append(data)
        if self._dt is not None:
            self._dt.append(data)
        if self._dd is not None:
            self._dd.append(data)


# ----------------------------------------------------------------------
# 규칙
# ----------------------------------------------------------------------


def _csp_directives(content: str) -> dict[str, list[str]]:
    directives: dict[str, list[str]] = {}
    for part in content.split(";"):
        tokens = part.split()
        if tokens:
            directives[tokens[0].lower()] = [t.lower() for t in tokens[1:]]
    return directives


def _check_csp(path: str, scan: _PageScan) -> Iterator[Violation]:
    if len(scan.csp) != 1:
        yield Violation(path, "csp", f"CSP <meta http-equiv> 가 {len(scan.csp)}개 (정확히 하나여야 함)")
        return
    d = _csp_directives(scan.csp[0])
    default = d.get("default-src")
    if default is None or not set(default) <= {"'self'", "'none'"} or not default:
        yield Violation(path, "csp", f"default-src 는 'self' 여야 한다: {default}")
    for name, sources in d.items():
        if "'unsafe-eval'" in sources or "'wasm-unsafe-eval'" in sources:
            yield Violation(path, "csp", f"{name} 에 unsafe-eval")
        if "'unsafe-inline'" in sources and name != "style-src":
            yield Violation(path, "csp", f"{name} 에 unsafe-inline (style-src 에만 허용)")
    script = d.get("script-src", default or [])
    if not set(script) <= {"'self'", "'none'"}:
        yield Violation(path, "csp", f"script-src 는 'self' 만: {script}")
    style = d.get("style-src", default or [])
    if scan.inline_styles and "'unsafe-inline'" not in style:
        yield Violation(path, "csp", f"인라인 스타일 {scan.inline_styles}곳이 CSP 에 막힌다")
    if "'unsafe-inline'" in style and not scan.inline_styles:
        yield Violation(path, "csp", "인라인 스타일이 없는데 style-src 에 unsafe-inline")


def _check_page(path: str, text: str) -> Iterator[Violation]:
    if DISCLAIMER not in text:
        yield Violation(path, "disclaimer", "면책 문구(DISCLAIMER)가 없다")

    scan = _PageScan()
    scan.feed(text)
    scan.close()

    yield from _check_csp(path, scan)

    for tag, target in scan.loads:
        if _OFFSITE.match(target) and not target.lower().startswith("data:"):
            yield Violation(path, "script", f"<{tag}> 가 다른 사이트 자원을 싣는다: {target}")
    if scan.inline_scripts:
        yield Violation(path, "script", f"인라인 <script> {scan.inline_scripts}개 (assets/*.js 로)")
    for handler in scan.handlers:
        yield Violation(path, "handler", f"인라인 이벤트 핸들러 {handler}")
    for url in scan.js_urls:
        yield Violation(path, "handler", f"javascript: 주소 {url}")

    for card in scan.cards:
        label = card.ident or "(id 없음)"
        terms = {dt.split(" ")[0]: dd for dt, dd in card.basis}
        if not terms.get("계산식"):
            yield Violation(path, "basis", f"지표 카드 {label} 에 계산식이 없다")
        if card.classes & JUDGED_SIGNALS and not terms.get("경계값"):
            yield Violation(path, "basis", f"판정한 지표 {label} 에 경계값이 없다")


def _check_storage(path: str, text: str) -> Iterator[Violation]:
    for m in _STORAGE_BANNED.finditer(text):
        yield Violation(path, "storage", f"{m.group(0)} 사용 — 쿠키·세션 저장소는 쓰지 않는다")
    allowed = {m.start() for m in _LOCAL_STORAGE_OK.finditer(text)}
    for m in _LOCAL_STORAGE.finditer(text):
        if m.start() not in allowed:
            snippet = text[m.start() : m.start() + 50].splitlines()[0]
            yield Violation(
                path,
                "storage",
                f'localStorage 는 getItem/setItem/removeItem("{STORAGE_PREFIX}…") 꼴만: {snippet}',
            )


def _check_secrets(path: str, text: str) -> Iterator[Violation]:
    for m in _HEX40.finditer(text):
        yield Violation(path, "secret", f"DART 인증키처럼 생긴 40자리 16진수 {m.group(0)[:6]}…")
    if "crtfc_key" in text:
        yield Violation(path, "secret", "crtfc_key (DART 인증키 파라미터)")


def check_file(path: str, data: bytes) -> list[Violation]:
    """파일 하나. `path` 는 출력 폴더 기준 경로(확장자로 규칙을 고른다)."""
    suffix = Path(path).suffix.lower()
    # 바이너리(ico·png)도 인증키 검사는 한다 — latin-1 은 어떤 바이트든 글자로 읽는다.
    text = data.decode("utf-8") if suffix in _TEXT_SUFFIXES else data.decode("latin-1")
    found = list(_check_secrets(path, text))
    if suffix == ".html":
        found += _check_page(path, text)
    if suffix in {".html", ".js"}:
        found += _check_storage(path, text)
    return found


def check_site(out: Path) -> list[Violation]:
    """출력 폴더 전체. 위반이 없으면 빈 목록."""
    if not out.is_dir():
        return [Violation("", "site", f"출력 폴더가 없다: {out}")]
    violations: list[Violation] = []
    pages = 0
    for file in sorted(p for p in out.rglob("*") if p.is_file()):
        rel = file.relative_to(out).as_posix()
        pages += rel.endswith(".html")
        violations += check_file(rel, file.read_bytes())
    if not pages:
        violations.append(Violation("", "site", "HTML 페이지가 하나도 없다 — 빈 빌드는 통과시키지 않는다"))
    return violations
