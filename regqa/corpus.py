"""Load a rulebook pack (a folder of Markdown files) into citable clauses.

File format (one statute / code / circular per file):

    ---
    doc_id: kr-ecommerce-act
    title: Act on the Consumer Protection in Electronic Commerce
    jurisdiction: KR
    source_url: https://...
    ---
    ## Article 17 (Withdrawal of Subscription)
    clause text ...

Every ``## `` heading starts one clause. A clause is the unit we retrieve and cite.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

PACKS_DIR = Path(__file__).resolve().parent.parent / "corpora"


@dataclass
class Clause:
    clause_id: str          # stable id used in citations and evals, e.g. "kr-ecommerce-act#17"
    doc_id: str
    doc_title: str
    jurisdiction: str
    heading: str            # e.g. "제17조 (청약철회등)"
    text: str
    source_url: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def cite(self) -> str:
        return f"{self.doc_title} — {self.heading}"


def _parse_front_matter(raw: str) -> tuple[dict, str]:
    if not raw.startswith("---"):
        return {}, raw
    end = raw.find("\n---", 3)
    if end == -1:
        return {}, raw
    meta = {}
    for line in raw[3:end].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, raw[end + 4:]


def _anchor(heading: str) -> str:
    """Short anchor for a clause id: the first number-ish token of the heading."""
    m = re.search(r"\d+(?:\.\d+)*[A-Za-z]?", heading)
    if m:
        return m.group(0)
    return re.sub(r"\W+", "-", heading.lower()).strip("-")[:40] or "x"


def load_file(path: Path) -> list[Clause]:
    meta, body = _parse_front_matter(path.read_text(encoding="utf-8"))
    doc_id = meta.get("doc_id", path.stem)
    title = meta.get("title", path.stem)
    jur = meta.get("jurisdiction", path.parent.name.upper())
    clauses: list[Clause] = []
    seen: dict[str, int] = {}
    for block in re.split(r"(?m)^## ", body)[1:]:
        heading, _, text = block.partition("\n")
        heading, text = heading.strip(), text.strip()
        if not text:
            continue
        anchor = _anchor(heading)
        seen[anchor] = seen.get(anchor, 0) + 1
        if seen[anchor] > 1:
            anchor = f"{anchor}-{seen[anchor]}"
        clauses.append(Clause(
            clause_id=f"{doc_id}#{anchor}", doc_id=doc_id, doc_title=title,
            jurisdiction=jur, heading=heading, text=text,
            source_url=meta.get("source_url", ""), meta=meta,
        ))
    return clauses


def _with_full(path: Path) -> list[Clause]:
    """Short quotations from ``path``, replaced clause-by-clause by ``_full/<name>`` when fetched.

    ``scripts/fetch_hk.py`` writes the official full text there (git-ignored); any clause it
    lacks keeps the bundled short quotation, so the pack always loads.
    """
    short = load_file(path)
    full_path = path.parent / "_full" / path.name
    if not full_path.is_file():
        return short
    full = {c.clause_id: c for c in load_file(full_path)}
    return [full.get(c.clause_id, c) for c in short]


def list_packs() -> list[str]:
    return sorted(p.name for p in PACKS_DIR.iterdir() if p.is_dir())


def load_pack(pack: str) -> list[Clause]:
    """Load one pack by name ("kr", "hk"), or every pack with "all"."""
    names = list_packs() if pack == "all" else [pack]
    out: list[Clause] = []
    for name in names:
        folder = PACKS_DIR / name
        if not folder.is_dir():
            raise SystemExit(f"unknown pack: {name!r} (available: {', '.join(list_packs())})")
        for f in sorted(folder.glob("*.md")):
            out.extend(_with_full(f))
    return out


def load_glossary(pack: str) -> dict[str, list[str]]:
    """Plain-language -> statute-term map for query expansion (``corpora/<pack>/glossary.json``)."""
    names = list_packs() if pack == "all" else [pack]
    merged: dict[str, list[str]] = {}
    for name in names:
        f = PACKS_DIR / name / "glossary.json"
        if f.exists():
            for k, v in json.loads(f.read_text(encoding="utf-8")).items():
                if not k.startswith("_"):
                    merged.setdefault(k.lower(), []).extend(v)
    return merged
