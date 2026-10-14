import importlib.util
import pathlib
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("quality",ROOT/"rhyme-quality.py")
quality=importlib.util.module_from_spec(spec);spec.loader.exec_module(quality)

def candidate(word):
    return {"word":word,"score":85,"confidence":80,"kind":"Near Rhyme","pronunciation":"?",
            "ipa":"?","category":"Nomen","register":"Standard","syllables":3,"explanation":"Fake score"}

class QualityGateTests(unittest.TestCase):
    def test_discards_bad_ferrari_matches_and_ignores_original_scores(self):
        initial={"analysis":{"interpreted_as":"Blue Ferrari"},
                 "rhymes":[candidate(x) for x in ("Toyota","Karaoke","Marinade","Batterie","Calamari","Safari")]}
        report={"review":[{"word":word,"accept":word in ("Calamari","Safari"),
                           "strength":"brauchbar" if word in ("Calamari","Safari") else "schwach",
                           "reason":"Phonetik des betonten Wortendes geprüft"}
                          for word in ("Toyota","Karaoke","Marinade","Batterie","Calamari","Safari")]}
        result=quality.review_and_filter("Blue Ferrari",initial,report)
        self.assertEqual([r["word"] for r in result["rhymes"]],["Calamari","Safari"])
        self.assertTrue(all(r["score"]==0 and r["confidence"]==0 for r in result["rhymes"]))
        self.assertTrue(result["quality_reviewed"])

    def test_not_approved_when_review_is_missing(self):
        result=quality.review_and_filter("blue ferrari",
            {"rhymes":[candidate("Toyota"),candidate("Safari")]},{"review":[]})
        self.assertEqual(result["rhymes"],[])
        self.assertTrue(result["quality_reviewed"])

    def test_zero_results_is_valid_and_no_mandated_minimum(self):
        self.assertEqual(quality.review_and_filter("Blue Ferrari",{"rhymes":[]},{"review":[]})["rhymes"],[])
        import importlib.util
        spec=importlib.util.spec_from_file_location("api",ROOT/"api.py")
        api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
        self.assertEqual(api.RHYME_SCHEMA["properties"]["rhymes"]["minItems"],0)

    def test_casefold_dedup_and_reject_weak_even_if_accepted(self):
        candidate_list={"rhymes":[candidate("Safari"),candidate("SAFARI"),candidate("Toyota")]}
        judgments={"review":[{"word":"safari","accept":True,"strength":"stark","reason":"Passender betonter Reimkern"},
                            {"word":"Toyota","accept":True,"strength":"schwach","reason":"Nur ein Vokal"}]}
        out=quality.review_and_filter("Ferrari",candidate_list,judgments)
        self.assertEqual(len(out["rhymes"]),1)
        self.assertEqual(out["rhymes"][0]["strength"],"stark")

if __name__=="__main__":unittest.main()
