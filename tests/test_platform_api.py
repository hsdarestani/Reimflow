"""Reimflow persistent platform regression tests (isolated SQLite database)."""
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from http.client import HTTPConnection
from pathlib import Path
import platform_api
import api

class PlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        platform_api.DATABASE=str(Path(cls.temp.name)/"test.sqlite")
        platform_api.MEDIA_DIR=Path(cls.temp.name)/"media"
        platform_api.initialize()
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),api.Handler)
        cls.port=cls.server.server_address[1]
        os.environ["REIMFLOW_DEV_ORIGIN"]="http://127.0.0.1:"+str(cls.port)
        cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp.cleanup()
        os.environ.pop("REIMFLOW_DEV_ORIGIN",None)

    def send(self,route,payload=None,cookie=None,method="POST"):
        c=HTTPConnection("127.0.0.1",self.port,timeout=5)
        head={"X-Reimflow-Client":"1","Content-Type":"application/json",
              "Origin":"http://127.0.0.1:"+str(self.port)}
        if cookie: head["Cookie"]=cookie
        c.request(method,route,json.dumps(payload or {}).encode() if method=="POST" else None,head)
        response=c.getresponse()
        status=response.status
        token=response.getheader("Set-Cookie","").split(";",1)[0]
        data=json.loads(response.read())
        c.close()
        return status,data,token

    def test_accounts_permissions_and_deletion(self):
        password="test"+"Password"+"0123456789"
        status,_,member=self.send("/api/platform/register",
            {"username":"test_member","email":"member@example.test","password":password})
        self.assertEqual(status,201)
        self.assertEqual(self.send("/api/platform/submissions",
            {"source":"Berlin","target":"Gewinn","category":"Nomen",
             "syllables":"2","pronunciation":"win"},member)[0],201)
        status,data,_=self.send("/api/platform/bootstrap",cookie=member,method="GET")
        self.assertEqual(status,200)
        self.assertEqual(len(data["feed"]),1)
        self.assertEqual(data["user"]["role"],"member")
        entry=data["feed"][0]["id"]
        self.assertEqual(self.send("/api/platform/review",
            {"id":entry,"decision":"accepted"},member)[0],403)
        status,_,tester=self.send("/api/platform/register",
            {"username":"test_tester","email":"tester@example.test","password":password})
        self.assertEqual(status,201)
        with platform_api.connection() as c:
            c.execute("UPDATE rf_users SET role='tester' WHERE username='test_tester'")
        self.assertEqual(self.send("/api/platform/review",
            {"id":entry,"decision":"accepted"},tester)[0],200)
        self.assertEqual(self.send("/api/platform/review",
            {"id":entry,"decision":"accepted"},tester)[0],409)
        self.assertEqual(self.send("/api/platform/bootstrap",cookie=member,method="GET")[1]["user"]["points"],10)
        self.assertEqual(self.send("/api/platform/favorites",{"word":"Gewinn"},member)[0],200)
        self.assertEqual(self.send("/api/platform/scores",{"bpm":92,"mode":"tap","score":87},member)[0],200)
        self.assertEqual(self.send("/api/platform/delete-account",{"password":password},member)[0],200)
        self.assertIsNone(self.send("/api/platform/bootstrap",cookie=member,method="GET")[1]["user"])

    def test_bad_input(self):
        self.assertEqual(self.send("/api/platform/register",
            {"username":"x","email":"not_an_email","password":"short"})[0],400)
        self.assertEqual(self.send("/api/platform/submissions",
            {"source":"A","target":"B"})[0],401)

if __name__=="__main__":
    unittest.main()
