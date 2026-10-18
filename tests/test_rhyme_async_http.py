"""Regression tests for long-running, independently reviewed rhyme jobs."""
import http.client
import json
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import api
import rhyme_jobs


class AsyncRhymeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.original_db=api.DB_PATH
        cls.original_key=api.OPENAI_API_KEY
        api.DB_PATH=str(Path(cls.tmp.name)/"rhyme-cache.sqlite")
        api.OPENAI_API_KEY="isolated-test-key"
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),api.Handler)
        cls.port=cls.server.server_address[1]
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close()
        cls.thread.join(timeout=5)
        api.DB_PATH=cls.original_db
        api.OPENAI_API_KEY=cls.original_key
        cls.tmp.cleanup()

    def request(self,path,body=None):
        con=http.client.HTTPConnection("127.0.0.1",self.port,timeout=4)
        headers={"Content-Type":"application/json"}
        if body is None:con.request("GET",path)
        else:con.request("POST",path,json.dumps(body).encode(),headers)
        res=con.getresponse()
        status=res.status;data=json.loads(res.read())
        con.close()
        return status,data

    def await_result(self,path):
        for _ in range(80):
            status,data=self.request(path)
            if status!=202:return status,data
            time.sleep(.025)
        self.fail("Rhyme job never finished")

    def test_jude_bellingham_uses_two_models_without_blocking_post(self):
        calls=[]
        raw={"analysis":{"input":"Jude Bellingham","interpreted_as":"Jude Bellingham",
              "correction":None},"rhymes":[{"word":"Telegramm","score":83,
              "confidence":79,"syllables":3,"explanation":"Klang ähnlich"}]}
        def model(user_text,schema,name,prompt,**kwargs):
            calls.append(name)
            time.sleep(.04)
            return (raw,"quality-test-model") if len(calls)==1 else ({"decisions":[]},"review-test-model")
        with patch.object(api,"call_openai",side_effect=model),patch.object(
            api.rhyme_quality,"review_and_filter",
            return_value={"quality_reviewed":True,"rhymes":[{"word":"Telegramm",
                "strength":"brauchbar","score":0,"confidence":0}],"analysis":raw["analysis"]}):
            status,result=self.request("/api/rhymes",{
                "query":"Jude Bellingham","category":"Alle","syllables":"Alle"})
            self.assertEqual(status,202,result)
            self.assertTrue(result["pending"])
            jid=result["job_id"]
            status,result=self.await_result("/api/rhymes/jobs/"+jid)
            self.assertEqual(status,200,result)
            self.assertTrue(result["quality_reviewed"])
            self.assertEqual(result["rhymes"][0]["word"],"Telegramm")
            self.assertEqual(len(calls),2)
            self.assertEqual(self.request("/api/rhymes",{
                "query":"Jude Bellingham","category":"Alle","syllables":"Alle"})[0],200)
            # Switching filters must reuse the single, language-reviewed AI response.
            status,filtered=self.request("/api/rhymes",{
                "query":"Jude Bellingham","category":"Nomen","syllables":"2"})
            self.assertEqual(status,200)
            self.assertEqual(filtered["quality_reviewed"],True)
            self.assertEqual(len(calls),2,"Filter changes must not start another AI generation/review")


    def test_timeout_never_returns_unreviewed_suggestions(self):
        def model(*args,**kwargs):
            raise RuntimeError("OPENAI_TIMEOUT")
        with patch.object(api,"call_openai",side_effect=model):
            status,result=self.request("/api/rhymes",{"query":"unique timeout QA 83912"})
            self.assertEqual(status,202,result)
            status,result=self.await_result("/api/rhymes/jobs/"+result["job_id"])
            self.assertEqual(status,504,result)
            self.assertEqual(result["error"],"AI_TIMEOUT")
            self.assertNotIn("rhymes",result)

    def test_failed_job_can_retry_immediately(self):
        manager=rhyme_jobs.Manager(max_jobs=2,max_workers=1)
        def bad(_):
            raise rhyme_jobs.JobError("AI_TIMEOUT","Timed out",504)
        first=manager.submit("retry",bad)
        for _ in range(80):
            if manager.get(first)[0]!=202:break
            time.sleep(.025)
        self.assertEqual(manager.get(first)[0],504)
        second=manager.submit("retry",lambda _:{"ok":True})
        self.assertNotEqual(first,second)
        for _ in range(80):
            if manager.get(second)[0]==200:break
            time.sleep(.025)
        self.assertEqual(manager.get(second)[0],200)
        manager.pool.shutdown(wait=True)

    def test_jobs_cannot_be_enumerated(self):
        self.assertEqual(self.request("/api/rhymes/jobs/invalid")[0],404)

    def test_queue_deduplicates_and_limits(self):
        manager=rhyme_jobs.Manager(max_jobs=1,max_workers=1)
        gate=threading.Event()
        one=manager.submit("same",lambda _:gate.wait(2) or {"ok":True})
        self.assertEqual(manager.submit("same",lambda _:{}),one)
        with self.assertRaises(rhyme_jobs.BusyError):
            manager.submit("different",lambda _:{"ok":True})
        gate.set()
        for _ in range(80):
            if manager.get(one)[0]==200:break
            time.sleep(.025)
        self.assertEqual(manager.get(one)[0],200)
        manager.pool.shutdown(wait=True)


if __name__=="__main__":
    unittest.main()
