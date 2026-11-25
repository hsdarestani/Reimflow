"""Opt-in, two-query real-model acceptance gate using an isolated scratch DB.

Requires configured OPENAI_API_KEY; never accesses production user data.
"""
import json, pathlib, sys, tempfile, time
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import api
import rhyme_jobs

class Request:
    command="POST"; path="/api/rhymes"; headers={}; client_address=("127.0.0.99",1)
    def __init__(self,query): self.query=query;self.response=None
    def read_json(self):return {"query":self.query}
    def send_json(self,status,data):self.response=status,data

def main():
    assert api.OPENAI_API_KEY,"OpenAI API key required for selected live acceptance test"
    assert api.rhyme_lexicon.available(),"Build the IPA index before benchmarking"
    manager=rhyme_jobs.Manager(max_workers=1)
    try:
        with tempfile.TemporaryDirectory() as temp,patch.object(api,"DB_PATH",temp+"/cache.sqlite"),patch.object(api,"_rhyme_jobs",manager):
            for query,min_count in (("Karim Benzema",10),("Blue Ferrari",7)):
                with patch.object(api,"call_openai",wraps=api.call_openai) as calls:
                    start=time.perf_counter();req=Request(query);api.Handler.do_POST(req)
                    status,initial=req.response
                    first=time.perf_counter()-start
                    if status==200:result=initial
                    else:
                        assert status==202 and initial["partial"]["quality_reviewed"],initial
                        while time.perf_counter()-start<20:
                            status,result=manager.get(initial["job_id"])
                            if status!=202:break
                            time.sleep(.08)
                    elapsed=time.perf_counter()-start
                    assert status==200,result
                    rows=result["rhymes"]; words=[r["word"].casefold() for r in rows]
                    print("REAL PREDEPLOY BENCHMARK",json.dumps({"query":query,"first_seconds":round(first,3),"complete_seconds":round(elapsed,3),"calls":calls.call_count,"count":len(rows),"words":words,"timing_ms":result.get("timing_ms")},ensure_ascii=False),flush=True)
                    if calls.call_count:assert result.get("model") and result.get("timing_ms"),"AI request did not complete; retaining prior release"
                    assert first<1 and elapsed<11,"Constrained generation must not materially regress v3 completion"
                    assert len(rows)>=min_count and len(words)==len(set(words)),"No count/duplicate regression"
                    assert sum(r.get("kind")=="Phrase" for r in rows)>=2,"Natural phrase variants missing"
                    assert all(r.get("german_valid") is True for r in rows)
                    assert all(not ({"space","case","race","toyota","karaoke"}&set(w.split())) for w in words)
                    assert result["analysis"]["input"]==query
                    assert 0<=calls.call_count<=2
                    if query=="Karim Benzema":assert calls.call_count==0 and elapsed<1,"Sufficient local matches must avoid AI"
            with patch.object(api,"call_openai",side_effect=AssertionError("Local search must not use AI")):
                req=Request("Jude Bellingham");started=time.perf_counter();api.Handler.do_POST(req)
                status,data=req.response;assert status==200 and len(data["rhymes"])>=5
                assert all(x["strength"]=="brauchbar" for x in data["rhymes"])
                print("REAL PREDEPLOY LOCAL NAME",round((time.perf_counter()-started)*1000,2),"ms",len(data["rhymes"]),"AI calls 0",flush=True)
    finally:manager.pool.shutdown(wait=True)

if __name__=="__main__":main()
