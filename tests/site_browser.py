"""브라우저 스모크 테스트 보조 — 빌드한 정적 사이트를 로컬 HTTP 로 띄우고 Chromium(playwright)으로 연다.

Chromium 이 설치돼 있지 않으면(CI 기본) 건너뛴다: `uv run playwright install chromium` 후 로컬에서 돈다.
"""

from __future__ import annotations

import functools
import http.server
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest


@contextmanager
def serve(root: Path) -> Iterator[str]:
    """`root` 를 임의 포트로 서빙하고 기본 주소(끝 '/')를 준다."""

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_args) -> None:
            pass

    handler = functools.partial(Quiet, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()


@contextmanager
def chromium() -> Iterator[object]:
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 — 브라우저 미설치는 실패가 아니라 건너뜀
            pytest.skip(f"Chromium 을 띄울 수 없다: {exc}")
        try:
            yield browser
        finally:
            browser.close()
