import importlib.util
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("intent",ROOT/"rhyme-intent.py")
intent=importlib.util.module_from_spec(spec);spec.loader.exec_module(intent)
class PhraseIntentTests(unittest.TestCase):
    def test_blue_paper_has_both_phrase_and_anchor(self):
        r=intent.search_intent("  Blue paper ")
        self.assertEqual(r["query_exact"],"Blue paper")
        self.assertEqual(r["end_word"],"paper")
        self.assertEqual(r["prefix"],"Blue")
        self.assertEqual(r["targets"],["full_phrase","end_word","phrase_variation"])

    def test_handles_punctuation_and_single_word(self):
        self.assertEqual(intent.search_intent("Blue paper!")["end_word"],"paper")
        self.assertEqual(intent.search_intent("Paper")["targets"],["end_word"])
        self.assertEqual(intent.search_intent("Blue Ferrari")["end_word"],"Ferrari")

if __name__=="__main__":unittest.main()
