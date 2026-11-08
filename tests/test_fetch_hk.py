"""Tests for scripts/fetch_hk.py (HK_QUOTE_FETCH_V1) — no network: urlopen / PDF extraction are faked."""
import contextlib
import importlib.util
import io
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fetch_hk.py"
_spec = importlib.util.spec_from_file_location("fetch_hk", SCRIPT)
fetch_hk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fetch_hk)

SFC_ENDS = ["GP3. Capabilities", "GP6. Conflicts", "5.1A Know your client", "5.2 Know your client",
            "5.3 Know", "5.6 Investor identification", "6.2 Minimum content", "12.2 Employee dealings",
            "12.4 Responsibility"]


def sfc_text(skip=None):
    parts = []
    for i, ((heading, _s, _e), end) in enumerate(zip(fetch_hk.SFC_CLAUSES, SFC_ENDS)):
        if heading != skip:
            parts.append(f"{heading}\nBODY{i} text\n{end}\n")
    return "\n".join(parts)


def hkma_text(doc):
    start = "GenAI, being a subfield" if doc == "genai" else "These guiding principles focus"
    end4 = "Proactive use of BDAI" if doc == "genai" else "Taking into account the views"
    t = (f"{start} SCOPE_{doc}\n\n1. Governance and accountability\nGOV_{doc}\n\n2. Fairness\nFAIR_{doc}\n\n"
         f"3. Transparency\nTRANS_{doc}\n\n4. Data privacy\nPRIV_{doc}\n{end4}\n")
    if doc == "genai":
        t += "BDAI, in particular GenAI, has the potential PROACTIVE\nShould you have any questions\n"
    return t


class TestDownload(unittest.TestCase):
    def _urlopen(self, payload):
        cm = mock.MagicMock()
        cm.__enter__.return_value.read.return_value = payload
        return mock.patch.object(fetch_hk.urllib.request, "urlopen", return_value=cm)

    def test_returns_pdf_bytes(self):
        with self._urlopen(b"%PDF-1.7 data"):
            self.assertEqual(fetch_hk.download("http://x"), b"%PDF-1.7 data")

    def test_rejects_non_pdf(self):
        with self._urlopen(b"<html>nope</html>"):
            with self.assertRaises(RuntimeError):
                fetch_hk.download("http://x")


class TestPdfText(unittest.TestCase):
    def test_joins_pages_and_tolerates_none(self):
        pages = [mock.Mock(extract_text=mock.Mock(return_value=t)) for t in ("alpha", None, "omega")]
        fake = mock.Mock(return_value=mock.Mock(pages=pages))
        # pypdf is an optional install; pdf_text imports it lazily, so a stub module is enough.
        with mock.patch.dict(sys.modules, {"pypdf": mock.Mock(PdfReader=fake)}):
            out = fetch_hk.pdf_text(Path("x.pdf"))
        self.assertIn("alpha", out)
        self.assertIn("omega", out)


class TestCut(unittest.TestCase):
    def test_found(self):
        self.assertEqual(fetch_hk.cut("aa START hello  world END zz", "START", "END"), "hello world")

    def test_start_missing(self):
        self.assertIsNone(fetch_hk.cut("aa hello END", "START", "END"))

    def test_end_missing(self):
        self.assertIsNone(fetch_hk.cut("aa START hello", "START", "END"))

    def test_last_skips_toc(self):
        text = "START toc END\nSTART real body END"
        self.assertEqual(fetch_hk.cut(text, "START", "END", last=True), "real body")
        self.assertEqual(fetch_hk.cut(text, "START", "END"), "toc")


class TestBuild(unittest.TestCase):
    def test_sfc_all_clauses(self):
        out, ok = fetch_hk.build_sfc(sfc_text())
        self.assertEqual(ok, 9)
        for i, (heading, _s, _e) in enumerate(fetch_hk.SFC_CLAUSES):
            self.assertIn(f"## {heading}\nBODY{i} text\n", out)
        self.assertIn(f"Source: {fetch_hk.SFC_URL}", out)

    def test_sfc_missing_and_empty_clause_skipped(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            out, ok = fetch_hk.build_sfc(sfc_text(skip="GP2. Diligence"))
        self.assertEqual(ok, 8)
        self.assertNotIn("## GP2. Diligence", out)
        self.assertIn("GP2. Diligence", err.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            out, ok = fetch_hk.build_sfc("GP2. Diligence\n\nGP3. Capabilities\n")
        self.assertEqual((out, ok), ("", 0))

    def test_hkma_all_clauses(self):
        out, ok = fetch_hk.build_hkma({d: hkma_text(d) for d in ("genai", "bdai")})
        self.assertEqual(ok, 6)
        self.assertIn("GenAI circular (19 August 2024):\nGOV_genai", out)
        self.assertIn("BDAI circular (5 November 2019):\nGOV_bdai", out)
        self.assertIn("## Proactive use of BDAI and GenAI in enhancing consumer protection\n"
                      "GenAI circular (19 August 2024):\nPROACTIVE", out)
        self.assertEqual(out.count("PROACTIVE"), 1)
        self.assertIn(fetch_hk.DOC_SOURCE["genai"], out)

    def test_hkma_partial_and_none(self):
        out, ok = fetch_hk.build_hkma({"genai": hkma_text("genai"), "bdai": ""})
        self.assertEqual(ok, 6)
        self.assertNotIn("BDAI circular", out)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            out, ok = fetch_hk.build_hkma({"genai": "", "bdai": ""})
        self.assertEqual((out, ok), ("", 0))
        self.assertIn("HKMA clause not found", err.getvalue())


class TestMain(unittest.TestCase):
    def _run(self, texts):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        hk = Path(tmp.name)
        for f in ("sfc_code_of_conduct.md", "hkma_genai_consumer.md"):
            (hk / f).write_text("---\nid: x\nnotice: short quote\n---\n## a\nb\n", encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(fetch_hk, "HK_DIR", hk), mock.patch.object(fetch_hk, "FULL_DIR", hk / "_full"), \
                mock.patch.object(fetch_hk, "download", return_value=b"%PDF"), \
                mock.patch.object(fetch_hk, "pdf_text", side_effect=lambda p: texts[Path(p).stem]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = fetch_hk.main()
        return rc, hk / "_full", out.getvalue(), err.getvalue()

    def test_writes_full_files(self):
        texts = {"sfc": sfc_text(), "genai": hkma_text("genai"), "bdai": hkma_text("bdai")}
        rc, full, out, _ = self._run(texts)
        self.assertEqual(rc, 0)
        sfc = (full / "sfc_code_of_conduct.md").read_text(encoding="utf-8")
        self.assertTrue(sfc.startswith("---\nid: x\nnotice: Full text fetched"))
        self.assertIn("## GP2. Diligence\nBODY0 text", sfc)
        self.assertIn("GOV_genai", (full / "hkma_genai_consumer.md").read_text(encoding="utf-8"))
        self.assertIn("(9 clauses)", out)
        self.assertIn("(6 clauses)", out)

    def test_nothing_extracted_not_written(self):
        rc, full, out, err = self._run({"sfc": "", "genai": "", "bdai": ""})
        self.assertEqual(rc, 0)
        self.assertFalse((full / "sfc_code_of_conduct.md").exists())
        self.assertFalse((full / "hkma_genai_consumer.md").exists())
        self.assertIn("nothing extracted for sfc_code_of_conduct.md", err)
        self.assertNotIn("wrote", out)


class TestEntryPoint(unittest.TestCase):
    def test_runs_main_only_as_script(self):
        full = SCRIPT.parent.parent / "corpora" / "hk" / "_full"
        existed = full.exists()
        cm = mock.MagicMock()
        cm.__enter__.return_value.read.return_value = b"not a pdf"
        try:
            with mock.patch("urllib.request.urlopen", return_value=cm), \
                    contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):  # main() ran and download() rejected the body
                    runpy.run_path(str(SCRIPT), run_name="__main__")
                runpy.run_path(str(SCRIPT), run_name="not_main")  # import must not fetch anything
        finally:
            if not existed and full.exists() and not any(full.iterdir()):
                full.rmdir()


if __name__ == "__main__":
    unittest.main()
