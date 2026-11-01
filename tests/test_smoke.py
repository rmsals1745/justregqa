"""Smoke tests — run with `python -m unittest` (or pytest). No network, no keys."""
import os
import unittest
from unittest import mock

from regqa import RegQA
from regqa import answer as answer_mod
from regqa.answer import check_citations
from regqa.cli import run_eval
from regqa.retrieve import tokenize


class TestTokenize(unittest.TestCase):
    def test_korean_bigrams_and_english_words(self):
        self.assertIn("청약", tokenize("청약철회는"))
        self.assertIn("suitability", tokenize("Suitability of products"))
        self.assertEqual(tokenize(""), [])


class TestAnswers(unittest.TestCase):
    def setUp(self):
        os.environ["REGQA_LLM"] = "none"

    def test_kr_answer_cites_article_18(self):
        ans = RegQA.from_pack("kr").ask("반품 배송비는 누가 내나요?")
        self.assertFalse(ans.abstained)
        self.assertEqual(ans.sources[0].clause.clause_id, "kr-ecommerce-act#18")
        self.assertIn("[1]", ans.text)

    def test_hk_answer_cites_transparency(self):
        ans = RegQA.from_pack("hk").ask("Must we tell customers they are talking to a GenAI chatbot?")
        self.assertEqual(ans.sources[0].clause.clause_id, "hk-hkma-genai-consumer#3")

    def test_out_of_scope_abstains(self):
        self.assertTrue(RegQA.from_pack("kr").ask("주식 양도소득세 세율은?").abstained)
        self.assertTrue(RegQA.from_pack("hk").ask("How do I apply for a work visa in Hong Kong?").abstained)

    def test_llm_mode_flags_bad_citations(self):
        with mock.patch.dict(os.environ, {"REGQA_LLM": "openai"}), \
             mock.patch.object(answer_mod.llm, "complete", return_value="A written agreement is needed [1][9]."):
            ans = RegQA.from_pack("hk").ask("Is a written client agreement required?")
        self.assertTrue(any("non-existent" in w for w in ans.warnings))

    def test_llm_not_found_becomes_abstain(self):
        with mock.patch.dict(os.environ, {"REGQA_LLM": "openai"}), \
             mock.patch.object(answer_mod.llm, "complete", return_value="NOT_FOUND"):
            self.assertTrue(RegQA.from_pack("hk").ask("Is a written client agreement required?").abstained)

    def test_check_citations(self):
        self.assertEqual(check_citations("rule [1].", 2), [])
        self.assertTrue(check_citations("rule without cite.", 2))


class TestEval(unittest.TestCase):
    def test_eval_thresholds(self):
        os.environ["REGQA_LLM"] = "none"
        res = run_eval("all")
        self.assertGreaterEqual(res["hit@k"], 0.9)
        self.assertGreaterEqual(res["abstain_accuracy"], 0.9)


if __name__ == "__main__":
    unittest.main()
