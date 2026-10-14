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

    def test_no_credentials_stored_in_response(self):
        self.assertNotIn("Authorization",api.RHYME_SCHEMA)
        self.assertNotIn("api_key",api.RHYME_SCHEMA)

if __name__=="__main__": unittest.main()
