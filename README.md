# justregqa — one engine, two rulebooks

**A regulatory Q&A agent that answers only with the clause it can point to — or says it can't.**
The same engine runs on a Korean rulebook (MFDS food labelling & e-commerce consumer law) and a
Hong Kong rulebook (SFC Code of Conduct & HKMA AI consumer-protection principles). Swap the
documents, keep the engine.

[한국어 설명은 아래](#한국어)

> **Status: v0.2 — working, measured.** The Korean rulebook is verbatim statute text from
> law.go.kr (시행일 recorded per file); the Hong Kong rulebook is verbatim excerpts of the SFC
> Code of Conduct and HKMA circulars. This is not legal advice. Always check the official source
> (links are printed with every answer).

---

## Why this exists

Compliance and CS teams in regulated industries get the same questions every day —
*"Can we say this tea helps with diabetes?"*, *"Do we have to tell customers the chatbot is AI?"* —
and the cost of a confident wrong answer is high. A useful assistant here has to:

1. **Cite** — every rule it states points at a specific article / paragraph.
2. **Abstain** — if the loaded rulebook does not cover the question, it says so instead of guessing.
3. **Be measured** — retrieval and abstention are scored on an eval set, so changes can't silently regress.
4. **Travel** — a new jurisdiction is a new folder of documents, not a new codebase.

## Quickstart

Python 3.10+, no dependencies for the offline mode.

```bash
git clone <this repo> && cd justregqa
python -m regqa packs                                    # kr 17 clauses / hk 15 clauses
python -m regqa ask --pack kr "반품 배송비는 누가 내나요?"
python -m regqa ask --pack hk "Must we tell customers they are talking to a GenAI chatbot?"
python -m regqa ask --pack kr "주식 양도소득세 세율은?"      # out of scope -> refuses
python -m regqa eval                                     # retrieval + abstention scores
python -m unittest                                       # smoke tests, no network
```

Example output:

```
What the rulebook says:
- Accordingly, they should disclose the use of GenAI to customers, and, among others, communicate
  with customers on the use and purpose of adoption of the GenAI models as well as the limitations
  of such models, in order to enhance customers' understanding of the model-generated outputs." [1]
...

Sources:
  [1] HKMA circulars — Consumer Protection in respect of Use of Generative Artificial Intelligence
      (19 Aug 2024) and of Big Data Analytics and AI (5 Nov 2019) — 3. Transparency and disclosure
      (hk-hkma-genai-consumer#3)
(mode: extractive)
```

### Optional: LLM-written answers

Offline mode quotes the clauses verbatim. To let a model write a fluent answer from the same
clauses, copy `.env.example` to `.env` and set `REGQA_LLM=anthropic` or `REGQA_LLM=openai`
(any OpenAI-compatible endpoint works via `OPENAI_BASE_URL`) plus the key and model id.
The model only sees the retrieved clauses, must cite them as `[n]`, and its citations are
**checked after the fact** — a citation to a clause it was never given is flagged.

## How it works

```
question ──► glossary expansion ──► BM25 retrieval ──► coverage gate ──► answer ──► citation check
             (plain words →          (Hangul bigrams +   (too little of     (extractive
              statute terms,          English words,      the question       quote, or LLM
              per pack)               one index)          matched → refuse)  over [n] clauses)
```

| Piece | File | Design choice |
|---|---|---|
| Rulebook pack | `corpora/<pack>/*.md` | One Markdown file per statute / code; every `##` heading is one citable clause with a stable id like `kr-ecommerce-act#17`. |
| Glossary | `corpora/<pack>/glossary.json` | Users type "반품", "refund", "chatbot"; statutes say "청약철회", "환급", "generative AI system". The gap is jurisdiction-specific, so it lives with the documents, not the engine. |
| Retrieval | `regqa/retrieve.py` | Zero-dependency BM25. Korean is indexed as character bigrams (no morphological analyser needed), English as words. |
| Abstention | `regqa/answer.py` | If the best clause covers too little of the question (`REGQA_MIN_COVERAGE`) or shares fewer than two distinct terms with it (`REGQA_MIN_TERMS`), refuse. |
| Answering | `regqa/answer.py`, `regqa/llm.py` | Extractive by default; optional Anthropic / OpenAI-compatible backend via stdlib HTTP. |
| Evals | `evals/<pack>.jsonl` | Each case = question + expected clause ids (empty = must refuse). `regqa eval` exits non-zero below threshold, ready for CI. |

Current scores on the bundled sets (83 cases, 8 of them must-refuse): **hit@1 0.97 · hit@k 1.00 · abstain accuracy 1.00**.
The sets are tiny and written by the author — treat them as a regression harness, not a benchmark.

## Sources and licensing

- **KR**: statute text is verbatim from 국가법령정보센터 (law.go.kr); each file's front matter records the 시행일 and 법률 번호. Korean statutes are not copyright-protected (저작권법 제7조).
- **HK**: verbatim *excerpts* of the SFC Code of Conduct (edition noted in the file) and HKMA circulars of 5 Nov 2019 and 19 Aug 2024, reproduced with attribution for non-commercial demonstration. © SFC / HKMA. Read the originals linked in each file; this repo is not legal advice.

## Adding a jurisdiction

1. `mkdir corpora/sg` and drop in Markdown files with the front matter shown in `regqa/corpus.py`.
2. Add `corpora/sg/glossary.json` for the words your users actually type.
3. Add `evals/sg.jsonl` with real questions, including ones that should be refused.
4. `python -m regqa eval --pack sg`.

## Roadmap

- [x] Official texts with version dates (KR: verbatim from law.go.kr; HK: verbatim excerpts of the SFC Code of Conduct and HKMA circulars).
- [ ] Automated ingestion (law.go.kr Open API, SFC / HKMA PDF parsing) instead of hand-picked articles.
- [ ] Hybrid retrieval (BM25 + multilingual embeddings) and a reranker, measured against the same evals.
- [ ] LLM-judged faithfulness eval (does each sentence follow from its cited clause?).
- [ ] Small web UI + container image for a cloud deploy.
- [ ] Cross-jurisdiction mode: "how does KR vs HK treat AI disclosure?" with side-by-side citations.

---

## 한국어

**근거 조항을 댈 수 있을 때만 답하고, 없으면 «모른다»고 말하는 규제 Q&A 에이전트.**
엔진은 하나, 문서는 두 벌 — 한국판(식약처 식품표시광고법·전자상거래법)과 홍콩판(SFC 행위규범·HKMA AI 소비자보호 원칙).

- **인용**: 답의 모든 문장 끝에 `[n]` — 어느 조·항인지 바로 아래 출처로 연결.
- **기권**: 실린 규정에 근거가 없으면 지어내지 않고 «찾지 못했다»고 답한다.
- **측정**: `evals/` 의 질문 세트로 검색 적중률·기권 정확도를 매번 잰다(지금 83문항 hit@1 0.97, 기권 1.00).
- **이식**: 나라를 늘리는 건 코드가 아니라 문서 폴더 하나(`corpora/<나라>/`)와 용어집 하나.

```bash
python -m regqa ask --pack kr "온라인으로 산 옷, 며칠 안에 반품할 수 있나요?"
python -m regqa eval
```

> 한국어 문서는 **국가법령정보센터(law.go.kr) 법령 원문**(파일마다 시행일 기록), 홍콩 문서는 SFC·HKMA 공식 문서의 **원문 발췌**다. 법률 자문이 아니다 — 답마다 찍히는 공식 출처 링크로 원문을 확인할 것.

## License

Code: MIT (see `LICENSE`).
Bundled rulebooks: Korean statutes are not copyright-protected (저작권법 제7조). HK excerpts remain © SFC / HKMA, reproduced with attribution for non-commercial demonstration.
