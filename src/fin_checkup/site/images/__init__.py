"""사이트가 만드는 PNG — 공유 카드(`og.py`)와 카드뉴스.

- `fonts.py`  한국어 글꼴 찾기 (설정 → 알려진 경로 → fc-list). 없으면 None — PNG 를 건너뛴다.
- `layout.py` 글꼴 지표로 재는 줄바꿈·말줄임, 그린 글자의 상자를 남기는 `Canvas`.
- `og.py`     `og/<종목코드>.png` 1200×630.
- `cards.py`  카드뉴스 1080×1350 5~6장 (`cli site cards`, 사이트 빌드와 무관 — docs/card-news.md).
"""
