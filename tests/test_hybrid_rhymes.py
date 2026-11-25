"""Real pinned lexical data plus deterministic and mocked pipeline regressions."""
import json, pathlib, tempfile, threading, time, unittest
from unittest.mock import patch
import api
import rhyme_lexicon as lex
import rhyme_jobs

QUERIES = ["Nacht","Haus","Liebe","Straße","Gedanken","Leidenschaft","Benzema","Karim Benzema",
"Cristiano Ronaldo","Jude Bellingham","Lionel Messi","Pokerface","Blue Ferrari","Lamborghini","Mercedes",
"Louis Vuitton","Coca-Cola","Instagram","TikTok","Alexanderplatz","Licht","Macht","Kraft","Wasser",
"Feuer","Herz","Schmerz","Zeit","Geld","Welt","Morgen","Sonne","Mond","Winter","Regen","Berlin",
"Hoffnung","Freiheit","Einsamkeit","Melodie","Revolution","Straßenbahn","harter Kampf","kalter Wind",
"New York","Ronaldo","Messi","Leidenshaft","Gednaken","Merkel"]

class Request:
    command="POST";path="/api/rhymes";headers={};client_address=("127.0.0.98",22)
    def __init__(self,query,category="Alle"):self.query=query;self.category=category;self.response=None
    def read_json(self):return {"query":self.query,"category":self.category}
    def send_json(self,status,data):self.response=(status,data)

@unittest.skipUnless(lex.available(),"Build pinned lexicon first")
class HybridTests(unittest.TestCase):
    def test_index_benchmark_and_phonetics(self):
        times=[]; counts={}
        for query in QUERIES:
            started=time.perf_counter(); ipa=lex.pronunciation(query)
            results=lex.retrieve(query,ipa.split()[-1]) if ipa else []
            times.append((time.perf_counter()-started)*1000)
            words=[r["word"].casefold() for r in results]
            self.assertEqual(len(words),len(set(words)),query)
            self.assertFalse(set(words)&lex.EXCLUDE,query)
            for row in results:
                self.assertTrue(row["german_valid"])
                self.assertTrue(lex.lookup(row["word"]))
                if row["strength"]=="stark":self.assertEqual(lex.tail(ipa.split()[-1]),lex.tail(row["ipa"]))
            counts[query]=len(results)
        print("LOCAL INDEX (50 queries, no AI):",json.dumps(counts,ensure_ascii=False))
        print("LOCAL INDEX latency ms median/P95",round(sorted(times)[len(times)//2],2),round(sorted(times)[int(.95*len(times))-1],2))
        self.assertGreaterEqual(counts["Nacht"],20)
        self.assertGreaterEqual(counts["Haus"],18)
        self.assertGreaterEqual(counts["Pokerface"],15)
        self.assertNotEqual(lex.match("fɛɪ̯s","pʁaɪ̯s")[1],"stark")
        for word in ("Toyota","Karaoke","Batterie","Marinade"):
            self.assertIsNone(lex.validate_word(word,"feˈraːri"))
        self.assertIsNone(lex.match("ˈlaɪ̯dn̩ʃaft","ˈvɪsn̩ʃaft"))
        self.assertEqual(lex.match("ˈlaɪ̯dn̩ʃaft","ˈaɪ̯ɡn̩ʃaft")[1],"brauchbar")

    def test_http_zero_ai_warm_and_filter(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(api,"DB_PATH",tmp+"/cache.sqlite"),patch.object(api,"OPENAI_API_KEY","mock"),patch.object(api,"call_openai") as ai:
            for query in ("Nacht","Haus","Pokerface"):
                cold=Request(query);start=time.perf_counter();api.Handler.do_POST(cold)
                cold_ms=(time.perf_counter()-start)*1000
                self.assertEqual(cold.response[0],200);self.assertFalse(cold.response[1]["cached"])
                warm=Request(query,"Nomen");start=time.perf_counter();api.Handler.do_POST(warm)
                self.assertTrue(warm.response[1]["cached"])
                print("HTTP local/DB benchmark",query,"cold_ms",round(cold_ms,2),"warm_ms",round((time.perf_counter()-start)*1000,2),"count",len(cold.response[1]["rhymes"]),"AI tokens 0")
            ai.assert_not_called()

    def test_progressive_foreign_and_review(self):
        manager=rhyme_jobs.Manager(max_workers=1); wait=threading.Event(); calls=[]
        def ai(prompt,schema,name,*args,**kwargs):
            calls.append(name)
            if name=="reimflow_hybrid_candidates":
                wait.wait(2)
                return {"ipa":"bɛnˈzeːma","words":["kein Thema","altes Schema","Space","Case","Race","Toyota","Karaoke"]},"mock"
            candidates=json.loads(prompt)["candidate_list"]
            return {"review":[{"word":r["word"],"accept":True,"german_valid":True,"strength":"stark","scope":"full_phrase","reason":"Test"} for r in candidates]},"mock-review"
        try:
            with tempfile.TemporaryDirectory() as tmp,patch.object(api,"DB_PATH",tmp+"/cache.sqlite"),patch.object(api,"OPENAI_API_KEY","mock"),patch.object(api,"_rhyme_jobs",manager),patch.object(api,"call_openai",side_effect=ai):
                r=Request("Karim Benzema");api.Handler.do_POST(r)
                self.assertEqual(r.response[0],202);self.assertTrue(r.response[1]["partial"]["quality_reviewed"])
                duplicate=Request("Karim Benzema","Nomen");api.Handler.do_POST(duplicate)
                jid=r.response[1]["job_id"];self.assertEqual(jid,duplicate.response[1]["job_id"])
                wait.set()
                for _ in range(100):
                    status,data=manager.get(jid)
                    if status!=202:break
                    time.sleep(.02)
                self.assertEqual(status,200);self.assertEqual(data["analysis"]["input"],"Karim Benzema")
                self.assertEqual(data["analysis"]["interpreted_as"],"Karim Benzema")
                self.assertTrue(data["quality_reviewed"])
                self.assertFalse({"space","case","race","toyota","karaoke"}&{x["word"].casefold() for x in data["rhymes"]})
                self.assertLessEqual(len(calls),2)
        finally:manager.pool.shutdown(wait=True)

    def test_exact_query_and_no_fake_perfect(self):
        self.assertEqual(lex.analysis("Benzema",lex.pronunciation("Benzema"))["input"],"Benzema")
        self.assertNotEqual(lex.analysis("Benzema",lex.pronunciation("Benzema"))["input"],"Karim Benzema")
        raw={"analysis":{"ipa":"feˈraːri"},"rhymes":[{"word":"Toyota"},{"word":"Karaoke"},{"word":"Space"}]}
        self.assertEqual(api.hybrid_candidates("Blue Ferrari",raw,"bluː feˈraːri"),([],[]))
