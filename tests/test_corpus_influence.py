"""Integration regression: corpus must affect the real rhyme request payload, not UI counts.

The AI network calls are mocked, but Handler.do_POST, SQLite, feature retrieval,
cache revision, generator call payload and independent review wiring are real.
Production data and model weights are never modified.
"""
import datetime
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import api
import style_intelligence as si

TEST_TEXT = (
    "Es ist ein klarer Tag in der Nacht\n"
    "Wir warten bis die Stadt erwacht\n"
    "Die Musik hat uns zum Ziel gebracht\n"
    "Und jeder neue Schritt ist gut bedacht\n"
    "Wir haben diesen Rhythmus mitgemacht\n"
).encode("utf8")


class LocalRequest:
    command = "POST"
    path = "/api/rhymes"
    headers = {}
    client_address = ("127.0.0.31", 3211)

    def __init__(self, query):
        self.query = query
        self.response = None

    def read_json(self):
        return {"query": self.query, "category": "Alle", "syllables": "Alle"}

    def send_json(self, status, payload):
        self.response = (status, payload)


class SynchronousJobManager:
    def __init__(self):
        self.results = []
    def stage(self, job_id, state):
        assert state == "review"
    def submit(self, cache_key, callback):
        self.results.append(callback("local-qa-job"))
        return "local-qa-job"


class CorpusInfluenceTests(unittest.TestCase):
    def test_actual_handler_generates_corpus_context_and_invalidates_cache(self):
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = str(Path(tempdir) / "isolated.sqlite3")
            saved = (api.DB_PATH, api.OPENAI_API_KEY, api._rhyme_jobs, api.call_openai)
            captured = []
            fake_jobs = SynchronousJobManager()

            def fake_ai(user_text, schema, schema_name, developer_prompt, **kwargs):
                if schema_name == "reimflow_quality_candidates":
                    parsed = json.loads(user_text)
                    captured.append(parsed)
                    return {
                        "analysis": {"input": "Nacht", "interpreted_as": "Nacht"},
                        "rhymes": [{
                            "word": "Pracht",
                            "pronunciation": "Pracht", "ipa": "pʁaxt",
                            "syllables": 1, "category": "Nomen", "register": "Standard",
                            "score": 80, "confidence": 80, "kind": "Perfekter Reim",
                            "explanation": "Reim auf Nacht"
                        }]
                    }, "mock-generator"
                if schema_name == "reimflow_independent_review":
                    return {"review": [{
                        "word": "Pracht", "accept": True, "german_valid": True,
                        "strength": "stark", "scope": "end_word",
                        "reason": "Deutsch und phonetisch plausibel"
                    }]}, "mock-independent-reviewer"
                raise AssertionError(schema_name)

            try:
                api.DB_PATH = db_path
                api.OPENAI_API_KEY = "local-mock-key-not-real"
                api._rhyme_jobs = fake_jobs
                api.call_openai = fake_ai

                def invoke():
                    request = LocalRequest("Nacht")
                    api.Handler.do_POST(request)
                    self.assertEqual(request.response[0], 202)
                    result = fake_jobs.results[-1]
                    self.assertTrue(result["quality_reviewed"])
                    self.assertEqual(result["review_model"], "mock-independent-reviewer")
                    self.assertEqual(result["rhymes"][0]["word"], "Pracht")
                    return result

                empty = invoke()
                self.assertFalse(empty["knowledge"]["context_applied"])
                self.assertEqual(empty["knowledge"]["licensed_tracks"], 0)
                self.assertFalse(captured[-1]["licensed_pattern_context"]["available"])

                imported = si.import_licensed_bytes(
                    TEST_TEXT, db_path=db_path, artist="Eko",
                    title="Synthetic QA Song", source_url="urn:qa:synthetic",
                    rights_ref="synthetic-test-no-real-lyrics",
                    valid_until=(datetime.date.today()+datetime.timedelta(days=30)).isoformat()
                )

                populated = invoke()
                self.assertEqual(populated["knowledge"]["licensed_tracks"], 1)
                self.assertTrue(populated["knowledge"]["context_applied"])
                context = captured[-1]["licensed_pattern_context"]
                self.assertTrue(context["available"])
                self.assertTrue(context["patterns"])
                self.assertEqual(context["public_editorial_research"]["artist_count"], 9)
                self.assertNotEqual(empty["context_revision"], populated["context_revision"])
                self.assertIn("nacht", str(context["patterns"]).casefold())
                self.assertNotIn("Die Musik hat uns", json.dumps(context, ensure_ascii=False))

                # After a rights withdrawal, cache revision must change again
                # and the next generator request must NOT receive old patterns.
                self.assertTrue(si.revoke(db_path, imported["source_id"])["revoked"])
                removed = invoke()
                self.assertFalse(removed["knowledge"]["context_applied"])
                self.assertEqual(removed["knowledge"]["licensed_tracks"], 0)
                self.assertFalse(captured[-1]["licensed_pattern_context"]["available"])
                self.assertNotEqual(populated["context_revision"], removed["context_revision"])
            finally:
                api.DB_PATH, api.OPENAI_API_KEY, api._rhyme_jobs, api.call_openai = saved


if __name__ == "__main__":
    unittest.main()
