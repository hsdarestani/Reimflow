"""Synthetic offline checks for expanded catalog discovery and rights-gated import."""
import datetime
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs,urlparse

import lyrics_import_expanded as expanded
import style_intelligence as si


TEXT=(
    "Der Morgen zeigt uns einen neuen Weg\n"
    "Im dunklen Himmel steht der Morgenstern\n"
    "Ein einziger Moment und alles dreht\n"
    "In dieser Straße liegt die Stadt ganz fern\n"
    "Der Rhythmus trägt uns weiter durch die Nacht\n"
)

class ExpandTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=str(Path(self.tmp.name)/"test.sqlite3")
        self.date=(datetime.date.today()+datetime.timedelta(days=30)).isoformat()
    def tearDown(self):
        self.tmp.cleanup()

    def test_catalog_interleaves_discovery_feeds_without_duplicates(self):
        def mb(artist,*,max_titles):
            return ["Nacht","Großstadt","Sommernacht"]
        def it(artist,*,max_titles):
            return ["Nacht","Winter","Großstadt"]
        # The helper functions accept injected fetch functions. It is enough to
        # test their behavior independently with source-specific fake JSON.
        def fake_mb(url):
            if "/artist?" in url:
                return {"artists":[{"name":"Kollegah","type":"Person","id":"fake-mbid"}]}
            return {"recordings":[
                {"title":"Nacht","artist-credit":[{"artist":{"name":"Kollegah"}}]},
                {"title":"Dunkle Stadt","artist-credit":[{"artist":{"name":"Kollegah"}}]},
                {"title":"Mix feat. Guest","artist-credit":[{"artist":{"name":"Kollegah"}}]},
                {"title":"Duett","artist-credit":[{"artist":{"name":"Kollegah"}},{"artist":{"name":"Other"}}]}
            ]}
        self.assertEqual(expanded.musicbrainz_titles("Kollegah",fetch=fake_mb,sleeper=lambda _:None),
                         ["Nacht","Dunkle Stadt"])
        def fake_itunes(url):
            return {"results":[
                {"wrapperType":"track","kind":"song","artistName":"Kollegah","trackName":"Nacht"},
                {"wrapperType":"track","kind":"song","artistName":"Kollegah","trackName":"Winter"},
                {"wrapperType":"track","kind":"song","artistName":"Other","trackName":"Unrelated"}
            ]}
        self.assertEqual(expanded.itunes_titles("Kollegah",fetch=fake_itunes),["Nacht","Winter"])
        titles=expanded.candidate_titles("Kollegah",max_titles=4,
                                         mb_fetch=fake_mb,itunes_fetch=fake_itunes,
                                         sleeper=lambda _:None)
        self.assertEqual(titles,["Nacht","Dunkle Stadt","Winter"])

    def test_lrclib_requires_exact_artist_and_title(self):
        def fake_fetch(url):
            q=parse_qs(urlparse(url).query)
            self.assertEqual(q["artist_name"],["Kollegah"])
            self.assertEqual(q["track_name"],["Nacht"])
            return [
                {"artistName":"Other","trackName":"Nacht","id":12,"plainLyrics":TEXT},
                {"artistName":"Kollegah","trackName":"Nachts","id":13,"plainLyrics":TEXT},
                {"artistName":"Kollegah feat. Other","trackName":"Nacht","id":14,"plainLyrics":TEXT},
                {"artistName":"Kollegah","trackName":"Nacht","id":15,"plainLyrics":TEXT}
            ]
        item=expanded.fetch_track("Kollegah","Nacht",fetch=fake_fetch)
        self.assertEqual(item[0],15)
        self.assertEqual(item[1],"Nacht")
        self.assertEqual(item[2].strip(),TEXT.strip())

    def test_import_dedup_and_revocation_controls(self):
        calls=[]
        def discover(artist,*,max_titles):
            return ["Nacht","Winter"] if artist=="Eko" else []
        def fetch(artist,title):
            calls.append((artist,title))
            return (101 if title=="Nacht" else 102,title,TEXT)
        first=expanded.expand(self.db,rights_ref="confirmed-test",review_due=self.date,
                              max_candidates_per_artist=5,target_total=2,
                              time_budget_seconds=60,request_pause=0,
                              discovery=discover,get_track=fetch,sleeper=lambda _:None)
        self.assertEqual(first["new_tracks"],2)
        self.assertEqual(first["current_tracks"],2)
        self.assertEqual(first["current_artists"],1)
        self.assertFalse(first["raw_lyrics_stored"])
        self.assertEqual(len(calls),2)
        again=expanded.expand(self.db,rights_ref="confirmed-test",review_due=self.date,
                              max_candidates_per_artist=5,target_total=4,
                              time_budget_seconds=60,request_pause=0,
                              discovery=discover,get_track=fetch,sleeper=lambda _:None)
        self.assertEqual(again["new_tracks"],0)
        self.assertEqual(again["current_tracks"],2)
        self.assertEqual(len(calls),2)
        with si.connect(self.db) as conn:
            texts=json.dumps(conn.execute("SELECT * FROM rf_lyric_sources").fetchall())
        self.assertNotIn("Der Morgen zeigt",texts)
        self.assertGreater(si.status(self.db)["lines_analyzed"],4)

    def test_invalid_rights_dates_fail(self):
        with self.assertRaises(ValueError):
            expanded.expand(self.db,rights_ref="",review_due=self.date)
        with self.assertRaises(ValueError):
            expanded.expand(self.db,rights_ref="asserted",review_due="2000-01-01")


if __name__=="__main__":
    unittest.main()
