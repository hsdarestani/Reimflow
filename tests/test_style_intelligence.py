"""Regression tests for rights-gated artist context and feedback learning."""
import datetime
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import style_intelligence as si

class StyleIntelligenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=str(Path(self.tmp.name)/"db.sqlite3")
        with si.connect(self.db) as c:
            c.execute("CREATE TABLE IF NOT EXISTS rf_users(id INTEGER PRIMARY KEY)")
            c.executemany("INSERT INTO rf_users(id) VALUES(?)", [(1,),(2,),(3,)])
            c.execute("CREATE TABLE IF NOT EXISTS cache(cache_key TEXT PRIMARY KEY,payload TEXT NOT NULL,created_at INTEGER NOT NULL)")
        self.file=Path(self.tmp.name)/"licensed.txt"
        self.file.write_text(
            "Die Nacht wird klar und weit\n"
            "Die Stadt ist wach zur Zeit\n"
            "Wir setzen Worte in Bewegung\n"
            "Die Musik gibt uns die Richtung\n"
            "Unser Takt klingt jetzt noch weiter\n",encoding="utf8")

    def tearDown(self): self.tmp.cleanup()

    def ingest(self,**kwargs):
        values={"db_path":self.db,"artist":"Miami Yacine","title":"Test Composition",
                "source_url":"urn:licensed-test:example","rights_ref":"permit-001",
                "valid_until":(datetime.date.today()+datetime.timedelta(days=14)).isoformat()}
        values.update(kwargs)
        return si.import_licensed(self.file,**values)

    def test_nine_artists_and_alias(self):
        self.assertEqual(len(si.ARTISTS),9)
        self.assertIn("Miami Yacine",si.ARTISTS)
        self.assertIn("Mo Trip",si.ARTISTS)
        self.assertEqual(self.ingest(artist="MoTrip")["artist"],"Mo Trip")

    def test_corpus_is_empty_until_rights_cleared(self):
        summary=si.status(self.db)
        self.assertEqual(summary["licensed_tracks"],0)
        self.assertEqual(summary["public_research_profiles"],9)
        reference=si.context(self.db,"Nacht")["public_editorial_research"]
        self.assertEqual(reference["artist_count"],9)
        self.assertTrue(reference["not_training_material"])
        self.assertTrue(any("multisyllabic" in tag for tag in reference["technique_families"]))
        self.assertFalse(si.context(self.db,"Nacht")["available"])
        with self.assertRaises(ValueError):
            self.ingest(rights_ref="")
        with self.assertRaises(ValueError):
            self.ingest(valid_until="2000-01-01")
        with self.assertRaises(ValueError):
            self.ingest(artist="Unapproved Artist")

    def test_ingest_stores_aggregates_not_lyrics(self):
        result=self.ingest()
        self.assertEqual(result["lines_analyzed"],5)
        self.assertFalse(result["raw_lyrics_stored"])
        context=si.context(self.db,"weit")
        self.assertTrue(context["available"])
        self.assertTrue(context["patterns"])
        with si.connect(self.db) as c:
            raw=json.dumps(c.execute("SELECT * FROM rf_lyric_features").fetchall())
        self.assertNotIn("Die Nacht wird klar und weit",raw)
        self.assertEqual(si.status(self.db)["artists_covered"],1)
        self.assertEqual(si.status(self.db)["licensed_tracks"],1)

    def test_feedback_requires_independent_review_and_three_votes(self):
        from hashlib import sha256
        query="Abendnacht"; word="Pracht"
        key=sha256(("rhymes|de-only-query-v2|"+query.casefold()).encode()).hexdigest()
        with si.connect(self.db) as c:
            c.execute("INSERT INTO cache VALUES(?,?,0)",(key,json.dumps({
                "quality_reviewed":True,"rhymes":[{"word":word,"german_valid":True}]}),))
            c.commit()
            with self.assertRaises(ValueError):
                si.record_feedback(c,user_id=1,query=query,word="wrong",vote=1)
            with self.assertRaises(ValueError):
                si.record_feedback(c,user_id=1,query=query,word=word,vote=0)
            for uid in (1,2,3):
                si.record_feedback(c,user_id=uid,query=query,word=word,vote=1)
            c.commit()
        findings=si.context(self.db,query)
        self.assertEqual(findings["feedback"][0]["positive"],3)
        self.assertEqual(findings["feedback"][0]["negative"],0)
        self.assertEqual(si.status(self.db)["feedback_count"],3)

    def test_license_expiry_excludes_context(self):
        result=self.ingest()
        with si.connect(self.db) as c:
            c.execute("UPDATE rf_lyric_sources SET valid_until='2000-01-01' WHERE source_id=?",(result["source_id"],))
            c.commit()
        self.assertEqual(si.status(self.db)["licensed_tracks"],0)
        self.assertFalse(si.context(self.db,"weit")["available"])

if __name__=="__main__":
    unittest.main()
