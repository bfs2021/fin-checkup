"""정적 사이트 생성기 — 캐시만 읽어 회사별 신호등 페이지를 만든다.

    uv run python -m fin_checkup.cli site build --year 2024 --out site-out [--limit N]

구성
- `build.py`    캐시 → 회사별 `Checkup`(service.py 그대로, DART 호출 0) → 등록된 페이지 → 출력 폴더
- `registry.py` 페이지 레지스트리. `@page("이름")` · `@company_context("이름")` · `load_pages()`
- `pages/`      페이지 종류마다 모듈 하나. 여기 둔 모듈은 자동으로 import·등록된다
- `context.py`  `Site`(빌드 공유 상태·`render`) · `CompanyEntry` · 상대 링크(`root_for`)
- `view.py`     회사 페이지에 넘길 문장·숫자 (`format`·`presentation` 재사용, 템플릿은 판정하지 않는다)
- `render.py`   Jinja2 환경 (자동 이스케이프, StrictUndefined, `url()`·`DISCLAIMER` 전역)
- `templates/`  `company/index.html` 이 섹션마다 하나인 부분 템플릿 `company/_*.html` 을 include

확장
- 페이지 종류 추가: `pages/<이름>.py` 에 `@page("<이름>")` 빌더 하나.
- 회사 페이지 섹션 추가: `templates/company/_<섹션>.html` + `company/index.html` 에 include 한 줄.
  데이터가 더 필요하면 `@company_context("<섹션>")` 으로 `(entry, site) -> dict` 를 등록.
- 링크는 `url('경로/')` (상대경로). 절대주소가 필요하면 `site.absolute_url(path)` (`--base-url`).
"""
