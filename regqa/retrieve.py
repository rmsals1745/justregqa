"""BM25 retrieval that works for Korean and English with zero dependencies.

Korean has no spaces between many morphemes ("청약철회는" = "청약철회" + "는"), so Hangul
runs are indexed as character bigrams; Latin words and numbers are indexed as whole words
(with a light plural strip). That is crude but surprisingly strong for statute text, and it
keeps the engine identical across both rulebooks — only the documents change.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .corpus import Clause

_HANGUL = re.compile(r"[가-힣]+")
_LATIN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)*")
_STOP = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are", "be", "by",
    "what", "which", "who", "when", "how", "do", "does", "can", "must", "should", "if", "it",
    "with", "as", "at", "that", "this", "i", "we", "my", "our", "any", "there",
}
_KO_STOP = {  # question-ending bigrams that carry no legal meaning
    "무엇", "어떻", "떻게", "하나", "인가", "나요", "는지", "있나", "합니", "니까", "되나", "해도", "까지",
    "어디", "언제", "누가", "내나", "해야", "야하", "받아", "아야", "있을", "을까", "할까", "수있", "도되",
}


def tokenize(text: str) -> list[str]:
    text = text.lower()
    toks: list[str] = []
    for run in _HANGUL.findall(text):
        if len(run) == 1:
            toks.append(run)
        else:
            toks.extend(b for b in (run[i:i + 2] for i in range(len(run) - 1)) if b not in _KO_STOP)
    for w in _LATIN.findall(text):
        if w in _STOP:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        toks.append(w)
    return toks


def expand(query: str, glossary: dict[str, list[str]]) -> str:
    """Append statute terms for any plain-language glossary key found in the query."""
    low = query.lower()
    extra = [t for key, terms in glossary.items() if key in low for t in terms]
    return query + (" " + " ".join(extra) if extra else "")


@dataclass
class Hit:
    clause: Clause
    score: float
    coverage: float   # share of the question's distinct terms found in this clause
    matched: int = 0  # how many distinct question terms this clause contains


class BM25Index:
    def __init__(self, clauses: list[Clause], k1: float = 1.4, b: float = 0.75):
        self.clauses = clauses
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(c.heading + " " + c.heading + " " + c.text)) for c in clauses]
        self.lens = [sum(d.values()) for d in self.docs]
        self.avgdl = (sum(self.lens) / len(self.lens)) if self.lens else 0.0
        df: Counter = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 4, glossary: dict[str, list[str]] | None = None) -> list[Hit]:
        q = tokenize(expand(query, glossary or {}))
        qset = set(q)
        if not qset:
            return []
        hits: list[Hit] = []
        for i, d in enumerate(self.docs):
            s = 0.0
            for t in q:
                tf = d.get(t)
                if not tf:
                    continue
                denom = tf + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avgdl)
                s += self.idf.get(t, 0.0) * tf * (self.k1 + 1) / denom
            if s > 0:
                matched = sum(1 for t in qset if t in d)
                hits.append(Hit(self.clauses[i], s, matched / len(qset), matched))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k]
