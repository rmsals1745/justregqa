"""Fetch the full Hong Kong rulebook texts from the official sources (HK_QUOTE_FETCH_V1).

The repo ships only short quotations of SFC / HKMA material (corpora/hk/*.md). This script
downloads the official PDFs, cuts them into the same clauses (same ``## `` headings, so the same
clause ids), and writes them to corpora/hk/_full/ (git-ignored). When that folder exists the
loader (regqa/corpus.py) prefers it; clauses it lacks fall back to the short quotation.

    pip install pypdf          # only needed for this script
    python scripts/fetch_hk.py

The texts stay (c) SFC / HKMA — they are fetched to your machine, not redistributed by this repo.
"""
from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

HK_DIR = Path(__file__).resolve().parent.parent / "corpora" / "hk"
FULL_DIR = HK_DIR / "_full"

SFC_URL = "https://www.sfc.hk/en/Rules-and-standards/Codes-and-guidelines/Codes/Code-of-Conduct-for-Persons-Licensed"
GENAI_URL = "https://brdr.hkma.gov.hk/eng/doc-ldg/docId/getPdf/20241107-1-EN/20241107-1-EN.pdf"
BDAI_URL = "https://brdr.hkma.gov.hk/eng/doc-ldg/docId/getPdf/20191105-1-EN/20191105-1-EN.pdf"

# (heading exactly as in the short file, start regex, end regex) — whitespace in PDF text is irregular.
SFC_CLAUSES = [
    ("GP2. Diligence", r"GP2\.\s+Diligence", r"GP3\.\s+Capabilities"),
    ("GP5. Information for clients", r"GP5\.\s+Information for clients", r"GP6\.\s+Conflicts"),
    ("5.1 Know your client: in general", r"5\.1\s+Know your client:\s+in general", r"5\.1\s*A\s+Know"),
    ("5.1A Know your client: investor characterization", r"5\.1\s*A\s+Know your client:\s+investor\s+characterization", r"5\.2\s+Know your client"),
    ("5.2 Know your client: reasonable advice", r"5\.2\s+Know your client:\s+reasonable\s+advice", r"5\.3\s+Know"),
    ("5.5 Know your client: complex products", r"5\.5\s+Know your client:\s+complex\s+products", r"5\.6\s+Investor identification"),
    ("6.1 Client agreement in writing", r"6\.1\s+Client agreement\s+in writing", r"6\.2\s+Minimum content"),
    ("12.1 Compliance: in general", r"12\.1\s+Compliance:\s+in general", r"12\.2\s+Employee dealings"),
    ("12.3 Complaints", r"12\.3\s+Complaints", r"12\.4\s+Responsibility"),
]

_H = r"\n\s*{n}\.\s+{t}"
HKMA_CLAUSES = [  # heading, {doc: (start, end)}
    ("Scope: GenAI in customer-facing applications", {
        "genai": (r"GenAI,\s+being a subfield", _H.format(n=1, t="Governance and accountability")),
        "bdai": (r"These guiding principles\s+focus", _H.format(n=1, t="Governance and accountability"))}),
    ("1. Governance and accountability", {
        "genai": (_H.format(n=1, t="Governance and accountability"), _H.format(n=2, t="Fairness")),
        "bdai": (_H.format(n=1, t="Governance and accountability"), _H.format(n=2, t="Fairness"))}),
    ("2. Fairness", {
        "genai": (_H.format(n=2, t="Fairness"), _H.format(n=3, t="Transparency")),
        "bdai": (_H.format(n=2, t="Fairness"), _H.format(n=3, t="Transparency"))}),
    ("3. Transparency and disclosure", {
        "genai": (_H.format(n=3, t="Transparency"), _H.format(n=4, t="Data privacy")),
        "bdai": (_H.format(n=3, t="Transparency"), _H.format(n=4, t="Data privacy"))}),
    ("4. Data privacy and protection", {
        "genai": (_H.format(n=4, t="Data privacy"), r"Proactive use of BDAI"),
        "bdai": (_H.format(n=4, t="Data privacy"), r"Taking into account the views")}),
    ("Proactive use of BDAI and GenAI in enhancing consumer protection", {
        "genai": (r"BDAI,\s+in particular GenAI,\s+has the potential", r"Should you have any questions")}),
]
DOC_LABEL = {"genai": "GenAI circular (19 August 2024)", "bdai": "BDAI circular (5 November 2019)"}
DOC_SOURCE = {"genai": f"Source: {GENAI_URL}, 19 August 2024", "bdai": f"Source: {BDAI_URL}, 5 November 2019"}

_PAGE_NOISE = re.compile(r"(?m)^\s*(?:–\s*\d+\s*–|(?:[A-Z][a-z]+ \d{4}\s+)?\d{1,3}[a-z]?)\s*$")


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "justregqa-fetch/0.1 (+research demo)"})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = r.read()
    if not data.startswith(b"%PDF"):
        raise RuntimeError(f"{url} did not return a PDF (got {data[:20]!r})")
    return data


def pdf_text(pdf: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise SystemExit("pypdf is required to extract the PDFs: pip install pypdf")
    text = "\n".join((p.extract_text() or "") for p in PdfReader(str(pdf)).pages)
    return _PAGE_NOISE.sub("", text)


def _clean(s: str) -> str:
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n\s*\n\s*(?:\n\s*)+", "\n\n", s).strip()


def cut(text: str, start: str, end: str, *, last: bool = False) -> str | None:
    """Text from ``start`` up to the next ``end`` match; ``last`` skips a table of contents."""
    start, end = (x.replace(" ", r"\s+") for x in (start, end))  # PDF line wraps and double spaces
    starts = list(re.finditer(start, text))
    if not starts:
        return None
    m = starts[-1] if last else starts[0]
    e = re.search(end, text[m.end():])
    if not e:
        return None
    return _clean(text[m.end():m.end() + e.start()])


def front_matter(short_file: Path) -> str:
    raw = short_file.read_text(encoding="utf-8")
    end = raw.find("\n---", 3)
    fm = raw[:end + 4]
    return re.sub(r"(?m)^notice:.*$", "notice: Full text fetched from the official source by scripts/fetch_hk.py (not redistributed by this repo). (c) the issuing authority — rely on the official text.", fm)


def build_sfc(text: str) -> tuple[str, int]:
    out, ok = [], 0
    for heading, start, end in SFC_CLAUSES:
        body = cut(text, start, end, last=True)
        if not body:
            print(f"  ! SFC clause not found, keeping short quote: {heading}", file=sys.stderr)
            continue
        out.append(f"## {heading}\n{body}\n\nSource: {SFC_URL}\n")
        ok += 1
    return "\n".join(out), ok


def build_hkma(texts: dict[str, str]) -> tuple[str, int]:
    out, ok = [], 0
    for heading, parts in HKMA_CLAUSES:
        blocks, srcs = [], []
        for doc, (start, end) in parts.items():
            body = cut(texts[doc], start, end)
            if body:
                blocks.append(f"{DOC_LABEL[doc]}:\n{body}")
                srcs.append(DOC_SOURCE[doc])
        if not blocks:
            print(f"  ! HKMA clause not found, keeping short quote: {heading}", file=sys.stderr)
            continue
        out.append(f"## {heading}\n" + "\n\n".join(blocks) + "\n\n" + "\n".join(srcs) + "\n")
        ok += 1
    return "\n".join(out), ok


def main() -> int:
    FULL_DIR.mkdir(exist_ok=True)
    pdfs = {"sfc": SFC_URL, "genai": GENAI_URL, "bdai": BDAI_URL}
    texts: dict[str, str] = {}
    for key, url in pdfs.items():
        path = FULL_DIR / f"{key}.pdf"
        print(f"fetching {url}")
        path.write_bytes(download(url))
        texts[key] = pdf_text(path)

    for fname, (body, ok) in {
        "sfc_code_of_conduct.md": build_sfc(texts["sfc"]),
        "hkma_genai_consumer.md": build_hkma(texts),
    }.items():
        if not ok:
            print(f"  ! nothing extracted for {fname}; not writing it", file=sys.stderr)
            continue
        (FULL_DIR / fname).write_text(front_matter(HK_DIR / fname) + "\n" + body, encoding="utf-8", newline="\n")
        print(f"wrote corpora/hk/_full/{fname} ({ok} clauses)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
