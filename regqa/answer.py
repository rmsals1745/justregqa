"""Turn retrieved clauses into a cited answer — or an explicit refusal.

Two modes, same contract (every claim carries a [n] pointing at a retrieved clause):
  * extractive (default, offline): quote the most relevant sentences verbatim.
  * llm: let a model write the answer from the numbered clauses, then *check* its citations.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from . import llm
from .corpus import Clause, load_glossary, load_pack
from .retrieve import BM25Index, Hit, expand, tokenize

NOT_FOUND = {
    "ko": "제공된 규제 문서에서 이 질문의 근거 조항을 찾지 못했습니다. 답을 지어내지 않습니다.",
    "en": "I could not find a supporting clause for this question in the loaded rulebook, so I won't guess.",
}

SYSTEM_PROMPT = """You answer regulatory questions ONLY from the numbered clauses provided.
Rules:
- Every sentence that states a rule must end with one or more citations like [1] or [2][3].
- Cite only clause numbers that appear in the context. Never cite anything else.
- If the clauses do not answer the question, reply exactly: NOT_FOUND
- Answer in the same language as the question. Be concise (max ~6 sentences).
- You are not giving legal advice; do not speculate beyond the text."""


@dataclass
class Answer:
    question: str
    text: str
    sources: list[Hit] = field(default_factory=list)
    mode: str = "extractive"
    abstained: bool = False
    warnings: list[str] = field(default_factory=list)


def lang_of(text: str) -> str:
    return "ko" if re.search(r"[가-힣]", text) else "en"


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s*|\n+", text)
    return [p.strip(" -*\t") for p in parts if len(p.strip(" -*\t")) > 8]


def _extractive(question: str, hits: list[Hit], max_sents: int = 4) -> str:
    q = set(tokenize(question))
    scored: list[tuple[float, int, str]] = []
    for n, h in enumerate(hits, 1):
        for s in _sentences(h.clause.text):
            st = set(tokenize(s))
            if not st:
                continue
            overlap = len(q & st) / (len(q) ** 0.5 * len(st) ** 0.5)
            scored.append((overlap * (1.0 / n ** 0.3), n, s))  # gentle preference for top-ranked clauses
    scored.sort(reverse=True)
    if not scored or scored[0][0] <= 0:
        return ""
    floor = scored[0][0] * 0.5          # drop sentences that are only loosely related
    picked = [x for x in scored if x[0] >= floor][:max_sents]
    return "\n".join(f"- {s} [{n}]" for _, n, s in picked)


def _context_block(hits: list[Hit]) -> str:
    return "\n\n".join(f"[{n}] {h.clause.cite}\n{h.clause.text}" for n, h in enumerate(hits, 1))


def check_citations(text: str, n_sources: int) -> list[str]:
    """Guardrail: flag uncited rule sentences and citations to clauses we never supplied."""
    warnings: list[str] = []
    cited = {int(x) for x in re.findall(r"\[(\d+)\]", text)}
    bad = sorted(c for c in cited if c < 1 or c > n_sources)
    if bad:
        warnings.append(f"cites non-existent sources: {bad}")
    if not cited:
        warnings.append("answer has no citations")
    return warnings


class RegQA:
    def __init__(self, clauses: list[Clause], top_k: int | None = None, min_coverage: float | None = None,
                 glossary: dict[str, list[str]] | None = None):
        self.index = BM25Index(clauses)
        self.glossary = glossary or {}
        self.top_k = top_k or int(os.environ.get("REGQA_TOP_K", "4"))
        self.min_coverage = (min_coverage if min_coverage is not None
                             else float(os.environ.get("REGQA_MIN_COVERAGE", "0.15")))

    @classmethod
    def from_pack(cls, pack: str, **kw) -> "RegQA":
        """Same engine, different rulebook: "kr", "hk" or "all"."""
        return cls(load_pack(pack), glossary=load_glossary(pack), **kw)

    def retrieve(self, question: str) -> list[Hit]:
        return self.index.search(question, self.top_k, self.glossary)

    def ask(self, question: str) -> Answer:
        lang = lang_of(question)
        hits = self.retrieve(question)
        if not hits or hits[0].coverage < self.min_coverage:
            return Answer(question, NOT_FOUND[lang], hits, abstained=True)

        if llm.backend() == "none":
            body = _extractive(expand(question, self.glossary), hits)
            if not body:
                return Answer(question, NOT_FOUND[lang], hits, abstained=True)
            head = "근거 조항에서 찾은 내용:" if lang == "ko" else "What the rulebook says:"
            return Answer(question, f"{head}\n{body}", hits, mode="extractive")

        out = llm.complete(SYSTEM_PROMPT, f"Context clauses:\n\n{_context_block(hits)}\n\nQuestion: {question}")
        if out.strip() == "NOT_FOUND":
            return Answer(question, NOT_FOUND[lang], hits, mode=f"llm:{llm.backend()}", abstained=True)
        return Answer(question, out.strip(), hits, mode=f"llm:{llm.backend()}",
                      warnings=check_citations(out, len(hits)))


def render(ans: Answer) -> str:
    lines = [ans.text, ""]
    if ans.sources and not ans.abstained:
        cited = {int(x) for x in re.findall(r"\[(\d+)\]", ans.text)}
        lines.append("Sources:")
        for n, h in enumerate(ans.sources, 1):
            if cited and n not in cited:
                continue
            url = f"  <{h.clause.source_url}>" if h.clause.source_url else ""
            lines.append(f"  [{n}] {h.clause.cite}  ({h.clause.clause_id}){url}")
    for w in ans.warnings:
        lines.append(f"! citation check: {w}")
    lines.append(f"(mode: {ans.mode})")
    return "\n".join(lines)
