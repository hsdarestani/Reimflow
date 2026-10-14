import importlib.util
import io
import pathlib
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("reimflow_flow_analysis",ROOT/"rap-flow-analysis.py")
analysis=importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)
from email.message import Message
api_spec=importlib.util.spec_from_file_location("reimflow_api_test",ROOT/"api.py")
api=importlib.util.module_from_spec(api_spec)
api_spec.loader.exec_module(api)


class RapFlowTests(unittest.TestCase):
    def test_syllable_estimates_are_labeled_as_rough(self):
        self.assertEqual(analysis.estimate_syllables("Takt"),1)
        self.assertGreaterEqual(analysis.estimate_syllables("Rhythmus"),1)
        self.assertEqual(analysis.estimate_syllables(""),0)

    def test_word_timing_bar_density_and_pause_are_from_actual_words(self):
        words=[
            {"word":"Hallo","start":3.10,"end":3.35},
            {"word":"wie","start":3.45,"end":3.60},
            {"word":"gehts","start":4.10,"end":4.35},
            {"word":"heute","start":4.9,"end":5.15},
            {"word":"Abend","start":5.85,"end":6.10}
        ]
        out=analysis.analyze_rap_words({"words":words},bpm=80,bars=4,beat_offset=3)
        self.assertTrue(out["ok"])
        self.assertEqual(out["status"],"analyzed")
        self.assertEqual(len(out["words"]),5)
        self.assertEqual(out["bars"][0]["words"],5)
        self.assertEqual(out["metrics"]["bars"],4)
        self.assertEqual(out["metrics"]["word_count"],5)
        self.assertGreater(out["metrics"]["longest_pause_sec"],0)
        self.assertGreaterEqual(out["metrics"]["word_onset_grid_percent"],0)
        self.assertLessEqual(out["metrics"]["word_onset_grid_percent"],100)
        self.assertNotIn("talent",str(out["feedback"]).lower())
        self.assertIn("Näherungen",out["limits"])

    def test_countin_is_ignored_and_no_false_score_without_speech(self):
        out=analysis.analyze_rap_words({"words":[{"word":"Test","start":0.2,"end":0.5}]},
            bpm=92,bars=8,beat_offset=2.61)
        self.assertEqual(out["status"],"no_speech")
        self.assertIsNone(out["metrics"])
        self.assertEqual(out["words"],[])

    def test_untrusted_tempo_or_offset_rejected(self):
        for values in [(999,4,3),(92,100,2),(92,8,-1),(92,8,float("nan"))]:
            with self.subTest(values=values),self.assertRaises(ValueError):
                analysis.analyze_rap_words({"words":[]},*values)

    def test_upload_enforces_content_size_and_format(self):
        message=Message()
        message["Content-Type"]="multipart/form-data; boundary=abc"
        message["Content-Length"]=str(analysis.MAX_AUDIO_BYTES+9000)
        with self.assertRaises(ValueError):
            api.parse_voice_form(message,io.BytesIO(b""))
        wire=b"--abc\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"rap.webm\"\r\nContent-Type: audio/webm\r\n\r\n"+b"\0"*1000+b"\r\n--abc\r\nContent-Disposition: form-data; name=\"bpm\"\r\n\r\n92\r\n--abc\r\nContent-Disposition: form-data; name=\"bars\"\r\n\r\n8\r\n--abc\r\nContent-Disposition: form-data; name=\"beat_offset\"\r\n\r\n2.9\r\n--abc--\r\n"
        msg=Message();msg["Content-Type"]="multipart/form-data; boundary=abc";msg["Content-Length"]=str(len(wire))
        audio,mime,bpm,bars,beat_offset=api.parse_voice_form(msg,io.BytesIO(wire))
        self.assertEqual(audio,b"\0"*1000)
        self.assertEqual((mime,bpm,bars,beat_offset),("audio/webm",92,8,2.9))

    def test_failed_api_call_has_no_database_or_audio_storage(self):
        self.assertFalse(hasattr(analysis,"cache_put"))
        self.assertFalse(hasattr(analysis,"db"))
        self.assertFalse(hasattr(analysis,"open"))
        self.assertNotIn("store=True",(ROOT/"rap-flow-analysis.py").read_text())

    def test_transcriber_uses_word_timestamps_and_approved_audio_format(self):
        captured={}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n=None):return b'{"text":"Hallo Welt","words":[{"word":"Hallo","start":0.2,"end":0.5}]}'
        def fake_open(req,timeout):
            captured["body"]=req.data
            captured["url"]=req.full_url
            captured["timeout"]=timeout
            return Response()
        with patch.object(analysis.urllib.request,"urlopen",fake_open):
            result=analysis.transcribe_audio(b"\0"*1400,"audio/webm","fake-key")
        self.assertEqual(len(result["words"]),1)
        self.assertIn(b'timestamp_granularities[]',captured["body"])
        self.assertIn(b'verbose_json',captured["body"])
        self.assertIn(b"rap.webm",captured["body"])
        self.assertLessEqual(captured["timeout"],75)
        with self.assertRaises(ValueError):
            analysis.transcribe_audio(b"x"*1500,"application/zip","fake")


if __name__=="__main__":
    unittest.main()
