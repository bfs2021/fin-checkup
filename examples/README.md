# 정적 JSON 으로 두 회사 나란히 보기

사이트는 회사 페이지와 같은 값을 정적 JSON 으로도 냅니다. 서버가 없는 파일이라 키도 호출 제한도 없습니다.
필드 뜻은 [`docs/api-static.md`](../docs/api-static.md).

| 파일 | 내용 |
|---|---|
| `https://younghwan91.github.io/fin-checkup/api/index.json` | 회사 목록 (종목코드순) — 종목코드 · 이름 · 시장 · 회사 파일 경로 |
| `https://younghwan91.github.io/fin-checkup/api/c/<종목코드>.json` | 회사 하나 — 지표 17개의 값 · 신호 · 계산식 · 경계값 · 대조군 분포 |

**측정값입니다.** 투자권유·자문이 아니며, 모든 파일에 `disclaimer` 가 들어 있습니다. 값을 다시 보여 줄 때는 그 문구와
출처(DART)를 함께 보여 주세요.

## 바로 돌려 보기

[`compare_signals.py`](compare_signals.py) 는 표준 라이브러리만 씁니다.

```bash
python examples/compare_signals.py 005930 000660
python examples/compare_signals.py 005930 105560 --base ./site-out   # 로컬 빌드 폴더 (site build 의 출력)
```

```
2024 사업연도 · 사업보고서

지표                  삼성전자             KB금융                경계값
-----------------------------------------------------------------------
영업이익률            🟢 정상 10.9%        🟢 정상 70.2%         정상 7% 이상 · 주의 0% 이상 · 그 미만은 위험
...
부채비율              🟢 정상 27.9%        ⊘ 해당 없음 1,167.0%  삼성전자: 정상 100% 이하 … / KB금융: 이 업종에는 판정 기준을 적용하지 않음 …
...
```

## 한 단계씩

### 1. 회사 목록에서 파일 경로 찾기

```python
import json
import urllib.request

SITE = "https://younghwan91.github.io/fin-checkup/"

def get(path):
    with urllib.request.urlopen(SITE + path, timeout=30) as response:
        return json.load(response)

index = get("api/index.json")
entry = next(c for c in index["companies"] if c["stock_code"] == "005930")
company = get(entry["json"])          # "api/c/005930.json"
```

`httpx` 를 쓴다면 `httpx.get(SITE + path).json()` 이 같은 일을 합니다.

### 2. 지표 한 줄 읽기

```python
for m in company["metrics"]:
    print(m["label"], m["signal"]["emoji"], m["value"], m["unit"], "|", m["formula"], "|", m["threshold_text"])
```

- `value` 가 `None`(JSON `null`)이면 공시에서 값을 찾지 못한 것(⚫)입니다. **0 으로 바꿔 계산하지 마세요.**
- `signal.key` 가 `not_applicable`(⊘)이면 계산은 되지만 그 업종에선 뜻이 없는 지표입니다. `note` 에 대신 볼 것이 있습니다.
- `thresholds` 는 회사 업종에 따라 다를 수 있습니다(금융업 ROA 등). 두 회사를 비교할 때 한쪽 경계값으로 다른 쪽을 판정하지 마세요.
- 금액(`unit == "money"`)의 통화는 파일의 `currency` 입니다.

### 3. 두 회사를 지표 키로 맞추기

```python
a, b = get("api/c/005930.json"), get("api/c/000660.json")
b_by_key = {m["key"]: m for m in b["metrics"]}
for m in a["metrics"]:                 # 파일의 지표 순서 그대로
    other = b_by_key[m["key"]]
    print(m["label"], m["signal"]["emoji"], other["signal"]["emoji"])
print(a["disclaimer"])
```

## 하지 말아 주세요

이 데이터로 회사를 지표 순으로 줄 세워 "상위 N" 목록을 만들거나, 신호를 합쳐 점수·등급을 매기면 이 도구가 일부러 하지 않는
일(근거를 감춘 종합 판단, [`docs/REGULATORY.md`](../docs/REGULATORY.md))을 대신 하게 됩니다. 목록이 필요하면 이름순·종목코드순으로,
판정을 보여 줄 땐 계산식과 경계값을 함께 보여 주세요.
