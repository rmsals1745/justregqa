# justregqa
소속: 경영지원 사업부 / 사내시스템팀
기억: _idx_systems.md

## 이 레포가 뭔가
- **가리킬 수 있는 조항으로만 답하는 규제 Q&A 엔진**이다. 룰북이 안 덮는 질문이면 추측하지 않고 모른다고 한다(README).
- 같은 엔진에 룰북만 갈아 끼운다 — 한국(kr: 식약처 표시·전자상거래)과 홍콩(hk: SFC 행동강령·HKMA AI 소비자보호).
- 검색은 BM25 + 용어집 확장 + 커버리지 게이트, 답은 추출 인용 또는 LLM 작성(인용은 사후 검사).

## 실행
- 설치: Python 3.10+ — 오프라인 모드는 의존성 0(`pyproject.toml`: `dependencies = []`)
- 개발 실행: `python -m regqa packs` · `python -m regqa ask --pack kr "반품 배송비는 누가 내나요?"` · `ask --pack hk "..."` · `python -m regqa eval`
- LLM 답을 켜려면 `.env.example` → `.env` 복사 후 `REGQA_LLM=anthropic|openai`
- 배포: 배포 스크립트 없음 (콘솔 스크립트 `regqa` 는 패키지 설치 시 생긴다)

## 시험
- `python -m unittest` — 네트워크 없는 스모크 시험
- `python -m regqa eval` — 검색·기권 점수를 잰다(회귀 감지용)
- pytest 로 돌릴 때: `python -m pytest -q tests/test_smoke.py`

## 주의
- `.env` 는 커밋 금지다. `.env.example` 만 레포에 둔다.
- LLM 이 **주지 않은 조항**을 인용하면 사후 검사에서 표시된다 — 인용 검사를 끄지 마라.
- 홍콩 룰북은 짧은 인용만 동봉돼 있다. 전문이 필요하면 `scripts/fetch_hk.py` 로 로컬에 받는다.
- 법률 자문이 아니다 — 답마다 공식 출처 링크가 함께 나가야 한다.

## 지도
- 이 레포가 속한 사업부·팀 기억 색인: _idx_systems.md
- 저장소: https://github.com/rmsals1745/justregqa.git (remote 이름 `origin`)
