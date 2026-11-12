"""Offline-only tests for rights-gated public lyrics ingestion."""
import datetime
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs,urlsplit

import lyrics_import_lrclib as provider
import style_intelligence as si

TEXT = (
    "Ein neuer Morgen faengt jetzt an\n"
    "Die Freunde bleiben irgendwann\n"
    "Wir machen heute einen Schritt\n"
    "Die Zeit im Kopf und weiter mit\n"
    "Ein frischer Satz mit anderem Sinn\n"
)

class FakeResponse:
    def __init__(self,rows):
        self.data=json.dumps(rows,ensure_ascii=False).encode("utf8")
    def __enter__(self):return self
    def __exit__(self,*_):return False
    def read(self,maximum):return self.data[:maximum]

class ImportLyricsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=str(Path(self.temp.name)/"lyrics.sqlite3")
        self.review=(datetime.date.today()+datetime.timedelta(days=5)).isoformat()
    def tearDown(self):
        self.temp.cleanup()
    @staticmethod
    def response(req,timeout=None):
        assert req.get_header("User-agent") == provider.UA
        q=parse_qs(urlsplit(req.full_url).query)["q"][0]
        alias={"Eko Fresh":"Eko Fresh","MoTrip":"MoTrip","Mo Trip":"Mo Trip"}
        name=alias.get(q,q)
        return FakeResponse([
            {"artistName":name,"trackName":"Original Composition",
             "albumName":"Synthetic album","id":71,"plainLyrics":TEXT,
             "instrumental":False},
            {"artistName":"Unrelated Performer","trackName":"Wrong Artist",
             "id":72,"plainLyrics":TEXT,"instrumental":False},
            {"artistName":name,"trackName":"No lyrics","id":73,
             "plainLyrics":None,"instrumental":True}
        ])
    def call(self,**kwargs):
        return provider.ingest_catalog(self.db,rights_ref="chat-attested-artists-2026-11-12",
            review_due=self.review,opener=self.response,sleep=lambda _:None,**kwargs)
    def test_imports_nine_artists_without_retaining_original_text(self):
        result=self.call()
        self.assertEqual(result["tracks_imported"],9)
        self.assertEqual(result["artist_count"],9)
        self.assertTrue(result["raw_lyrics_stored"] is False)
        self.assertEqual(si.status(self.db)["licensed_tracks"],9)
        self.assertEqual(si.status(self.db)["artists_covered"],9)
        with si.connect(self.db) as c:
            corpus=json.dumps(c.execute("SELECT * FROM rf_lyric_features").fetchall())
        self.assertNotIn("Ein neuer Morgen", corpus)
        self.assertEqual(sum(x["imported"] for x in result["artists"]),9)
    def test_dry_run_does_not_change_corpus(self):
        result=self.call(dry_run=True)
        self.assertEqual(result["tracks_found"],9)
        self.assertEqual(result["tracks_imported"],0)
        self.assertEqual(si.status(self.db)["licensed_tracks"],0)
    def test_credits_must_be_primary_artist(self):
        self.assertFalse(provider.belongs_to_artist("Eko Fresh feat. Other","Eko"))
        self.assertTrue(provider.belongs_to_artist("Eko Fresh","Eko"))
        self.assertFalse(provider.belongs_to_artist("Other feat. Eko Fresh","Eko"))
        self.assertTrue(provider.belongs_to_artist("MoTrip","Mo Trip"))
        self.assertFalse(provider.belongs_to_artist("Eko","Kollegah"))
        self.assertFalse(provider.belongs_to_artist("SSIO Fake","SSIO"))
    def test_synced_lyrics_can_be_analyzed_without_timestamps(self):
        row={"plainLyrics":None,"syncedLyrics":
             "\n".join(f"[00:0{i}.20] {line}" for i,line in enumerate(TEXT.splitlines()))}
        parsed=provider.lyrics_from_result(row)
        self.assertNotIn("[00:",parsed)
        self.assertEqual(parsed.count("\n"),4)
    def test_missing_rights_reference_is_rejected(self):
        with self.assertRaises(ValueError):
            provider.ingest_catalog(self.db,rights_ref="",review_due=self.review,
                                    opener=self.response,sleep=lambda _:None)

if __name__=="__main__":
    unittest.main()
