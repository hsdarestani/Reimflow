"""Exercise upstream socket timeouts without external network calls."""
import json
import unittest
from unittest.mock import patch
import api


class TimeoutSwitchTests(unittest.TestCase):
    def test_socket_timeout_retries_next_full_quality_model(self):
        previous=api.OPENAI_API_KEY
        api.OPENAI_API_KEY="unit-test"
        attempts=[]
        class Stub:
            def __enter__(self):return self
            def __exit__(self,*_):return False
            def read(self,size=-1):
                return json.dumps({"output":[{"type":"message","content":[{"type":"output_text",
                 "text":json.dumps({"analysis":{"input":"Jude Bellingham"},"rhymes":[]})}]}]}).encode()
        def stub(req,timeout):
            attempts.append(timeout)
            if len(attempts)==1:raise TimeoutError("timed out")
            return Stub()
        try:
            with patch.object(api.urllib.request,"urlopen",side_effect=stub):
                response,model=api.call_openai("Jude Bellingham",
                    api.RHYME_SCHEMA,"unit_rhyme","Quality test",
                    models=["gpt-5.6-sol","gpt-5.5"],timeout=65)
            self.assertEqual(model,"gpt-5.5")
            self.assertEqual(attempts,[65,45])
        finally:
            api.OPENAI_API_KEY=previous


if __name__=="__main__":unittest.main()
