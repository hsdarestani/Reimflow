import importlib.util
import io
import json
import pathlib
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("rhyme_api",ROOT/"api.py")
api=importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class Response:
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,size=-1):
        payload={"output":[{"type":"message","content":[{"type":"output_text","text":json.dumps({"analysis":{"input":"Blue Talisman","interpreted_as":"Blue Talisman"},"rhymes":[]})}]}]}
        return json.dumps(payload).encode()


class RhymeModelsTest(unittest.TestCase):
    def test_model_ids_and_time_budgets(self):
        self.assertIn("gpt-5.6-sol",api.FALLBACK_MODELS)
        self.assertNotIn("gpt-6-luna",api.FALLBACK_MODELS)
        self.assertIn("gpt-5.6-terra",api.QUALITY_MODEL)

    def test_success_after_primary_model_timeout(self):
        original=api.OPENAI_API_KEY
        original_models=api.FALLBACK_MODELS
        attempts=[]
        try:
            api.OPENAI_API_KEY="fake-test-token"
            api.FALLBACK_MODELS=["gpt-5.6-sol","gpt-5.5"]
            def respond(req,timeout):
                body=json.loads(req.data)
                attempts.append((body,timeout))
                if len(attempts)==1: raise api.urllib.error.HTTPError(req.full_url,404,"model unavailable",None,io.BytesIO(b"not found"))
                return Response()
            with patch.object(api.urllib.request,"urlopen",side_effect=respond):
                data,model=api.call_openai("Blue Talisman",api.RHYME_SCHEMA,"test_rhymes",api.DEVELOPER_PROMPT)
            self.assertEqual(model,"gpt-5.5")
            self.assertEqual(len(attempts),2)
            self.assertEqual(attempts[0][0]["reasoning"]["effort"],"medium")
            self.assertEqual(attempts[1][0]["reasoning"]["effort"],"medium")
            self.assertLessEqual(attempts[0][1],65)
            self.assertEqual(data["analysis"]["input"],"Blue Talisman")
        finally:
            api.OPENAI_API_KEY=original
            api.FALLBACK_MODELS=original_models

    def test_incomplete_reasoning_response_retries_quality_model(self):
        previous=api.OPENAI_API_KEY
        calls=[]
        class Incomplete:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self,size=-1):
                return json.dumps({"status":"incomplete","incomplete_details":{"reason":"max_output_tokens"},"output":[{"type":"reasoning"}]}).encode()
        try:
            api.OPENAI_API_KEY="fake-test-token"
            def respond(req,timeout):
                body=json.loads(req.data)
                calls.append((body["model"],body["max_output_tokens"]))
                return Incomplete() if len(calls)==1 else Response()
            with patch.object(api.urllib.request,"urlopen",side_effect=respond):
                data,model=api.call_openai("Blue Talisman",api.RHYME_SCHEMA,
                    "unit_retry","German only",models=["gpt-5.6-sol","gpt-5.5"])
            self.assertEqual(model,"gpt-5.5")
            self.assertEqual(calls,[("gpt-5.6-sol",8500),("gpt-5.5",8500)])
            self.assertEqual(data["analysis"]["input"],"Blue Talisman")
        finally:
            api.OPENAI_API_KEY=previous

    def test_fast_generation_and_compact_independent_review_payloads(self):
        prev=api.OPENAI_API_KEY
        api.OPENAI_API_KEY="mock-for-unit-test"
        requests=[]
        try:
            def spy(req,timeout):
                requests.append(json.loads(req.data))
                return Response()
            with patch.object(api.urllib.request,"urlopen",side_effect=spy):
                api.call_openai("Pokerface",api.RHYME_SCHEMA,
                    "reimflow_quality_candidates",api.DEVELOPER_PROMPT,
                    effort="low",max_output_tokens=4300,
                    models=["gpt-5.6-sol"],service_tier="fast")
                api.call_openai("Pokerface",api.RHYME_SCHEMA,
                    "reimflow_independent_review","German review",
                    effort="low",max_output_tokens=2700,
                    models=["gpt-5.6-terra"],service_tier="fast")
            self.assertEqual([x["max_output_tokens"] for x in requests],[4300,2700])
            self.assertTrue(all(x["service_tier"]=="fast" for x in requests))
            self.assertTrue(all(x["text"]["verbosity"]=="low" for x in requests))
            self.assertTrue(all(x["reasoning"]["effort"]=="low" for x in requests))
        finally:
            api.OPENAI_API_KEY=prev

    def test_transient_rate_limit_has_single_bounded_retry(self):
        prev=api.OPENAI_API_KEY
        api.OPENAI_API_KEY="mock"
        attempts=[]
        try:
            def respond(req,timeout):
                attempts.append(json.loads(req.data))
                if len(attempts)==1:
                    raise api.urllib.error.HTTPError(req.full_url,429,"Too Many Requests",
                        {"Retry-After":"0"},io.BytesIO(b"rate-limited"))
                return Response()
            with patch.object(api.urllib.request,"urlopen",side_effect=respond),patch.object(api.time,"sleep") as sleep:
                result,model=api.call_openai("Pokerface",api.RHYME_SCHEMA,"test","prompt",
                    models=["gpt-5.6-terra"],service_tier="default")
            self.assertEqual(model,"gpt-5.6-terra")
            self.assertEqual(len(attempts),2)
            self.assertNotIn("service_tier",attempts[0])
            self.assertEqual(sleep.call_count,1)
            self.assertLessEqual(sleep.call_args.args[0],5)
        finally:
            api.OPENAI_API_KEY=prev

    def test_persistent_rate_limit_does_not_retry_forever(self):
        prev=api.OPENAI_API_KEY
        api.OPENAI_API_KEY="mock"
        attempts=[]
        try:
            def respond(req,timeout):
                attempts.append(1)
                raise api.urllib.error.HTTPError(req.full_url,429,"Busy",
                    {"Retry-After":"8"},io.BytesIO(b"rate-limited"))
            with patch.object(api.urllib.request,"urlopen",side_effect=respond),patch.object(api.time,"sleep") as sleep:
                with self.assertRaisesRegex(RuntimeError,"OPENAI_HTTP_429"):
                    api.call_openai("Pokerface",api.RHYME_SCHEMA,"test","prompt",
                        models=["gpt-5.6-terra"])
            self.assertEqual(len(attempts),2)
            self.assertEqual(sleep.call_args.args[0],5)
        finally:
            api.OPENAI_API_KEY=prev

    def test_standard_mode_does_not_force_paid_fast_tier(self):
        old=api.OPENAI_API_KEY
        api.OPENAI_API_KEY="mock"
        seen=[]
        try:
            def inspect(req,timeout):
                seen.append(json.loads(req.data))
                return Response()
            with patch.object(api.urllib.request,"urlopen",side_effect=inspect):
                api.call_openai("Nacht",api.RHYME_SCHEMA,"test","prompt",
                    models=["gpt-5.6-sol"],service_tier="default")
            self.assertNotIn("service_tier",seen[0])
        finally:
            api.OPENAI_API_KEY=old

    def test_no_credentials_stored_in_response(self):
        self.assertNotIn("Authorization",api.RHYME_SCHEMA)
        self.assertNotIn("api_key",api.RHYME_SCHEMA)

if __name__=="__main__": unittest.main()
