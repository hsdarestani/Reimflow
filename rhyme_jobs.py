"""Bounded asynchronous server-side rhyme jobs.

A high-quality two-pass rhyme search can exceed one HTTP request timeout.
Keep the quality gate intact and let the browser poll a short-lived job ID.
Job IDs are random, unguessable tokens; no user input is written to logs.
"""
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor


class JobError(Exception):
    def __init__(self, code, message, http_status=502):
        super().__init__(code)
        self.code=code
        self.message=message
        self.http_status=http_status


class BusyError(Exception):
    pass


class Manager:
    def __init__(self, max_jobs=12, max_workers=3, ttl=900):
        self.lock=threading.Lock()
        self.jobs={}
        self.by_key={}
        self.max_jobs=max_jobs
        self.ttl=ttl
        self.pool=ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="reimflow-rhyme")

    def _cleanup(self):
        now=time.monotonic()
        for jid,job in list(self.jobs.items()):
            if job["status"] not in ("done","failed") or now-job["updated"]<=self.ttl:
                continue
            self.jobs.pop(jid,None)
            if self.by_key.get(job["cache_key"])==jid:
                self.by_key.pop(job["cache_key"],None)

    def submit(self, key, worker):
        with self.lock:
            self._cleanup()
            existing_id=self.by_key.get(key)
            if existing_id and existing_id in self.jobs:
                return existing_id
            pending=sum(1 for j in self.jobs.values() if j["status"] in ("queued","working"))
            if pending>=self.max_jobs:
                raise BusyError()
            job_id=secrets.token_urlsafe(24)
            self.jobs[job_id]={
                "cache_key":key, "status":"queued", "stage":"queued",
                "updated":time.monotonic(),"result":None,"error":None
            }
            self.by_key[key]=job_id
        self.pool.submit(self._execute,job_id,worker)
        return job_id

    def _execute(self,job_id,worker):
        self.stage(job_id,"generation")
        try:
            result=worker(job_id)
        except JobError as exc:
            with self.lock:
                j=self.jobs[job_id]
                j.update(status="failed",error={"error":exc.code,"message":exc.message},
                         http_status=exc.http_status,updated=time.monotonic())
        except Exception as exc:
            print("rhyme background failure:",type(exc).__name__,flush=True)
            with self.lock:
                j=self.jobs[job_id]
                j.update(status="failed",error={"error":"AI_UPSTREAM",
                         "message":"Die KI-Suche konnte nicht abgeschlossen werden. Bitte erneut versuchen."},
                         http_status=502,updated=time.monotonic())
        else:
            with self.lock:
                j=self.jobs[job_id]
                j.update(status="done",result=result,stage="done",updated=time.monotonic())

    def stage(self,job_id,stage):
        with self.lock:
            job=self.jobs.get(job_id)
            if job:
                job["stage"]=stage
                job["status"]="working"
                job["updated"]=time.monotonic()

    def get(self,job_id):
        with self.lock:
            self._cleanup()
            job=self.jobs.get(job_id)
            if job is None:return None
            if job["status"]=="done":
                return (200,job["result"])
            if job["status"]=="failed":
                return (job["http_status"],job["error"])
            return (202,{"ok":True,"pending":True,"stage":job["stage"],
                         "job_id":job_id,"poll_after_ms":2000})
