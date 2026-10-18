"""Regression tests: Reimflow never returns English rhymes as suggestions."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rhyme_quality", ROOT / "rhyme-quality.py")
quality = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quality)

class GermanOnlyRhymesTest(unittest.TestCase):
    def test_language_check_is_required(self):
        item = quality.QUALITY_SCHEMA["properties"]["review"]["items"]
        self.assertIn("german_valid", item["required"])

    def test_independent_gate_discards_english_even_with_strong_rhyme(self):
        generated = {"analysis":{"input":"Blue paper"}, "rhymes":[
            {"word":"caper","register":"Standard","score":99},
            {"word":"Zauber","register":"Standard","score":70},
            {"word":"paper","register":"Englisch/Code-Switch","score":99}
        ]}
        verdicts = {"review":[
            {"word":"caper","german_valid":False,"accept":True,"strength":"stark","scope":"end_word","reason":"Englisch"},
            {"word":"Zauber","german_valid":True,"accept":True,"strength":"brauchbar","scope":"end_word","reason":"Deutsch"},
            {"word":"paper","german_valid":True,"accept":True,"strength":"stark","scope":"end_word","reason":"falsch markiert"}
        ]}
        result = quality.review_and_filter("Blue paper", generated, verdicts)
        self.assertEqual([row["word"] for row in result["rhymes"]], ["Zauber"])

    def test_missing_language_verdict_fails_closed(self):
        generated = {"rhymes":[{"word":"night","register":"Standard","score":99}]}
        result = quality.review_and_filter("Nacht", generated, {"review":[
            {"word":"night","accept":True,"strength":"stark","scope":"end_word","reason":"Englisch"}
        ]})
        self.assertEqual(result["rhymes"], [])

    def test_cache_namespace_invalidated_for_multilingual_results(self):
        api_text = (ROOT / "api.py").read_text(encoding="utf-8")
        self.assertIn("rhymes|de-only-v1|", api_text)
        self.assertNotIn('"Englisch/Code-Switch"]}', api_text)

if __name__ == "__main__":
    unittest.main()
