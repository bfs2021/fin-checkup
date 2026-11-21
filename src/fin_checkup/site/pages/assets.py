"""정적 자원 `/assets/…` — `site/static/` 의 파일을 그대로 복사한다 (CSS·JS)."""

from __future__ import annotations

from collections.abc import Iterator
from importlib.resources import files
from importlib.resources.abc import Traversable

from fin_checkup.site.context import Site
from fin_checkup.site.registry import Output, page

STATIC = files("fin_checkup.site") / "static"


def _walk(node: Traversable, prefix: str) -> Iterator[tuple[str, Traversable]]:
    for child in sorted(node.iterdir(), key=lambda c: c.name):
        if child.name.startswith((".", "_")):
            continue
        if child.is_dir():
            yield from _walk(child, f"{prefix}{child.name}/")
        else:
            yield f"{prefix}{child.name}", child


@page("assets")
def asset_files(site: Site) -> Iterator[Output]:
    for path, resource in _walk(STATIC, "assets/"):
        yield Output(path, resource.read_bytes())
