"""Regression: hide internal lyric source and generation details from public URLs."""
import tempfile
import io
import json
import unittest
from pathlib import Path

import api
import style_intelligence as si


class FakeHandler:
    command="GET"
    def __init__(self,path):
        self.path=path
        self.result=None
    def send_json(self,status,payload):
        self.result=(status,payload)


class CorpusRoutesTest(unittest.TestCase):
    def test_mobile_context_links_and_status_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            original=api.DB_PATH
            api.DB_PATH=str(Path(tmp)/"db.sqlite3")
            try:
                for path in (
                    "/api/rhymes/context-status",
                    "/api/rhymes/context-status/",
                    "/api/rhymes/context-status?source=mobile",
                    "/api/corpus/status",
                    "/api/corpus/status/",
                ):
                    client=FakeHandler(path)
                    api.Handler.do_GET(client)
                    self.assertEqual(client.result[0],404,path)
                    self.assertEqual(client.result[1],{"error":"NOT_FOUND"})
                client=FakeHandler("/api/rhymes/not-a-real-path")
                api.Handler.do_GET(client)
                self.assertEqual(client.result[0],404)
            finally:
                api.DB_PATH=original


    def test_public_rhyme_payload_hides_corpus_and_model_internals(self):
        class Capture:
            def __init__(self): self.wfile=io.BytesIO()
            def send_response(self,status): self.status=status
            def send_header(self,*args): pass
            def end_headers(self): pass
        response=Capture()
        api.Handler.send_json(response,200,{
            "ok":True,"analysis":{"input":"Nacht"},"rhymes":[{"word":"Macht"}],
            "quality_reviewed":True,"cached":False,
            "knowledge":{"licensed_tracks":85,"artists_covered":9},
            "model":"hidden-generative-model","review_model":"hidden-checker",
            "context_revision":"private-revision",
            "quality_method":"independent_ai_review",
            "timing_ms":{"generation":2000},"intent":{"end_word":"Nacht"}
        })
        public=json.loads(response.wfile.getvalue())
        self.assertEqual(response.status,200)
        self.assertEqual(public["rhymes"][0]["word"],"Macht")
        self.assertTrue(public["quality_reviewed"])
        self.assertEqual(set(public),{"ok","analysis","rhymes","quality_reviewed","cached"})

    def test_shipped_rhyme_client_never_discloses_corpus_or_generation_details(self):
        js=(Path(__file__).resolve().parents[1]/"app.js").read_text(encoding="utf8")
        for sensitive in ("Wissensbasis","lizenzierte Titel","Künstlerprofile",
                          "Klang von KI geprüft","Die zweite KI prüft",
                          "KI Reimsuche"):
            self.assertNotIn(sensitive,js)


if __name__=="__main__":
    unittest.main()
