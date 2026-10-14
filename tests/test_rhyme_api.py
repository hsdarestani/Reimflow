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
        self.assertIn("gpt-4o-mini",api.FALLBACK_MODELS)
        self.assertNotIn("gpt-6-luna",api.FALLBACK_MODELS)
        self.assertNotIn("gpt-5.6-terra",api.FALLBACK_MODELS)

    def test_success_after_primary_model_timeout(self):
        original=api.OPENAI_API_KEY
        original_models=api.FALLBACK_MODELS
        attempts=[]
        try:
            api.OPENAI_API_KEY="fake-test-token"
            api.FALLBACK_MODELS=["gpt-4o-mini","gpt-4.1-mini"]
            def respond(req,timeout):
                body=json.loads(req.data)
                attempts.append((body,timeout))
                if len(attempts)==1: raise TimeoutError("synthetic slow response")
                return Response()
            with patch.object(api.urllib.request,"urlopen",side_effect=respond):
                data,model=api.call_openai("Blue Talisman",api.RHYME_SCHEMA,"test_rhymes",api.DEVELOPER_PROMPT)
            self.assertEqual(model,"gpt-4.1-mini")
            self.assertEqual(len(attempts),2)
            self.assertNotIn("reasoning",attempts[0][0])
            self.assertNotIn("reasoning",attempts[1][0])
            self.assertLessEqual(attempts[0][1],23)
            self.assertEqual(data["analysis"]["input"],"Blue Talisman")
        finally:
            api.OPENAI_API_KEY=original
            api.FALLBACK_MODELS=original_models

    def test_no_credentials_stored_in_response(self):
        self.assertNotIn("Authorization",api.RHYME_SCHEMA)
        self.assertNotIn("api_key",api.RHYME_SCHEMA)

if __name__=="__main__": unittest.main()
