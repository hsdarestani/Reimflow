"""Regression tests for public diagnostic routes opened by mobile browsers."""
import tempfile
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
                    self.assertEqual(client.result[0],200,path)
                    body=client.result[1]
                    self.assertTrue(body["ok"])
                    self.assertEqual(body["public_research_profiles"],9)
                    self.assertFalse(body["lyrics_included"])
                client=FakeHandler("/api/rhymes/not-a-real-path")
                api.Handler.do_GET(client)
                self.assertEqual(client.result[0],404)
            finally:
                api.DB_PATH=original


if __name__=="__main__":
    unittest.main()
