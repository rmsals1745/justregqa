"""Command line: ask a question, or run the eval set.

    python -m regqa ask --pack kr "온라인으로 산 물건, 며칠 안에 반품할 수 있나요?"
    python -m regqa ask --pack hk "Must we tell customers they are talking to a GenAI chatbot?"
    python -m regqa eval --pack all
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import llm
from .answer import RegQA, render
from .corpus import list_packs, load_pack

EVALS_DIR = Path(__file__).resolve().parent.parent / "evals"


def run_eval(pack: str, verbose: bool = False) -> dict:
    packs = list_packs() if pack == "all" else [pack]
    total = hit1 = hitk = abst_ok = abst_n = ans_n = 0
    fails: list[str] = []
    for p in packs:
        qa = RegQA.from_pack(p)
        path = EVALS_DIR / f"{p}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            case = json.loads(line)
            total += 1
            ans = qa.ask(case["q"]) if llm.backend() == "none" else None
            hits = qa.retrieve(case["q"])
            ids = [h.clause.clause_id for h in hits]
            expect = case.get("expect", [])
            if not expect:                                  # out-of-scope question: must abstain
                abst_n += 1
                abstained = (ans.abstained if ans else (not hits or hits[0].coverage < qa.min_coverage))
                abst_ok += abstained
                if not abstained:
                    fails.append(f"[{p}] should abstain: {case['q']}  -> {ids[:1]}")
                continue
            ans_n += 1
            h1 = bool(ids) and ids[0] in expect
            hk = any(i in expect for i in ids)
            hit1 += h1
            hitk += hk
            if not hk:
                fails.append(f"[{p}] miss: {case['q']}  expected {expect} got {ids}")
    res = {
        "cases": total,
        "hit@1": round(hit1 / ans_n, 3) if ans_n else None,
        "hit@k": round(hitk / ans_n, 3) if ans_n else None,
        "abstain_accuracy": round(abst_ok / abst_n, 3) if abst_n else None,
    }
    print(json.dumps(res, ensure_ascii=False))
    if verbose or fails:
        for f in fails:
            print("  " + f)
    return res


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    llm.load_dotenv()
    ap = argparse.ArgumentParser(prog="regqa", description="Citation-first regulatory Q&A (KR / HK).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask", help="ask one question")
    a.add_argument("question")
    a.add_argument("--pack", default="all", help=f"rulebook pack: {', '.join(list_packs())} or all")
    e = sub.add_parser("eval", help="run retrieval + abstention eval")
    e.add_argument("--pack", default="all")
    e.add_argument("-v", "--verbose", action="store_true")
    sub.add_parser("packs", help="list rulebook packs")
    args = ap.parse_args(argv)

    if args.cmd == "packs":
        for p in list_packs():
            print(p, len(load_pack(p)), "clauses")
        return 0
    if args.cmd == "ask":
        try:
            print(render(RegQA.from_pack(args.pack).ask(args.question)))
        except llm.LLMError as err:
            print(f"LLM error: {err}", file=sys.stderr)
            return 2
        return 0
    res = run_eval(args.pack, args.verbose)
    ok = (res["hit@k"] or 0) >= 0.8 and (res["abstain_accuracy"] is None or res["abstain_accuracy"] >= 0.8)
    return 0 if ok else 1   # non-zero exit lets CI fail on a regression


if __name__ == "__main__":
    raise SystemExit(main())
