"""Independent query set: never used to construct pronunciation or phrase data."""
import json, resource, statistics, time, unittest
from concurrent.futures import ThreadPoolExecutor
import rhyme_lexicon as lex

HOLDOUT=(
    "Brot","Laufen","Kuchen","Wand","Tanz","Sicht","Schnee","Blut","Buch","Nebel",
    "Sommer","Kälte","Traum","Schlange","Wunde","Reise","Schatten","Kuss","Fluss","Fisch",
    "Gedicht","Vertrauen","Verbrechen","Versprechen","Erinnerung","Verzweiflung","Unendlichkeit","Wissenschaft","Freundschaft","Gerechtigkeit",
    "Schmetterling","Fahrradkette","Sonnenuntergang","Bundespräsident","Krankenhaus","Autobahnbrücke","Klimawandel","Wasserflasche","Regenbogen","Schlüsselbund",
    "Bahnhofsvorplatz","Feuerwehrmann","Weihnachtsmarkt","Fußballstadion","Kühlschranktür","Eichhörnchen","Doppelgänger","Zusammenarbeit","Lebensfreude","Bücherregal",
    "Gianluigi Donnarumma","Kylian Mbappé","Erling Haaland","Bukayo Saka","Pedri","Lamine Yamal","Harry Kane","Kevin De Bruyne","Victor Osimhen","Luka Modrić",
    "Antoine Griezmann","Federico Valverde","Virgil van Dijk","Khvicha Kvaratskhelia","Achraf Hakimi","Neymar Junior","Mikel Arteta","Alexander Isak","Florian Wirtz","Jamal Musiala",
    "Pepsi","Microsoft","YouTube","WhatsApp","Samsung","Lacoste","Dior","Gucci","Balenciaga","PlayStation",
    "Midnight Express","Bonne soirée","Dolce vita","hasta mañana","Schwarzer Panther","kalte Nacht","keinen Bock","krass drauf","Schmetterlng","Verzweiflng",
)

def benchmark(module):
    times=[]; covered=0; nonempty=0; counts=[]; inferred=0; unknown=[]; empty=[]
    for query in HOLDOUT:
        start=time.perf_counter()
        if hasattr(module,"pronunciation_info"):
            variants,source=module.pronunciation_info(query);rows=module.retrieve_variants(query,variants,source) if variants else []
        else:
            ipa=module.pronunciation(query);variants=(ipa,) if ipa else ();source="dictionary" if ipa else "unsupported";rows=module.retrieve(query,ipa.split()[-1]) if ipa else []
        times.append((time.perf_counter()-start)*1000);counts.append(len(rows))
        covered+=bool(variants);nonempty+=bool(rows);inferred+=source=="inferred"
        if not variants:unknown.append(query)
        elif not rows:empty.append(query)
    return {"queries":len(HOLDOUT),"pronunciation_covered":covered,"inferred":inferred,"nonempty":nonempty,"zero_results":len(HOLDOUT)-nonempty,"mean_count":round(statistics.mean(counts),2),"median_ms":round(statistics.median(times),3),"p95_ms":round(sorted(times)[int(.95*len(times))-1],3),"unsupported":unknown,"no_local_matches":empty}

@unittest.skipUnless(lex.available(),"Build pinned index first")
class Phase2Holdout(unittest.TestCase):
    def test_holdout_coverage_and_concurrency(self):
        self.assertEqual(len(set(HOLDOUT)),90)
        self.assertTrue(lex.g2p.available(),"Install pinned G2P before acceptance")
        report=benchmark(lex);print("PHASE2 HOLDOUT",json.dumps(report,ensure_ascii=False),flush=True)
        self.assertGreaterEqual(report["pronunciation_covered"],85)
        self.assertGreaterEqual(report["nonempty"],55)
        def search(query):
            p,s=lex.pronunciation_info(query);return tuple(r['word'] for r in lex.retrieve_variants(query,p,s))
        subset=HOLDOUT[:35];start=time.perf_counter();cpu=time.process_time()
        with ThreadPoolExecutor(max_workers=8) as pool:parallel=list(pool.map(search,subset))
        serial=[search(q) for q in subset];self.assertEqual(parallel,serial)
        print("PHASE2 CONCURRENCY",json.dumps({"requests":len(subset),"workers":8,"wall_ms":round((time.perf_counter()-start)*1000,2),"cpu_ms":round((time.process_time()-cpu)*1000,2),"rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}),flush=True)

    def test_independent_grammar_and_rhymes(self):
        for word,cat in (("Baum","Nomen"),("laufen","Verb"),("schön","Adjektiv"),("krass","Umgangssprache"),("gemacht","Verb"),("schnell","Adjektiv"),("Freude","Nomen"),("denken","Verb"),("heiß","Adjektiv")):
            self.assertIn(cat,lex.grammatical_categories(word),(word,lex.grammatical_categories(word)))
        self.assertTrue({'Adjektiv','Verb'}<=set(lex.grammatical_categories('schön')))
        for query,expected in (("Brot","rot"),("Wand","Sand"),("Kuchen","suchen"),("Blut","Mut"),("Buch","Tuch"),("Nebel","Hebel"),("Tanz","Glanz"),("Sicht","Licht"),("Schnee","See"),("Schatten","Latten"),("Wunde","Kunde"),("Fluss","Kuss"),("Fisch","Tisch"),("Traum","Baum")):
            p,s=lex.pronunciation_info(query);row=lex.validate_word(expected,p[0]);self.assertIsNotNone(row,(query,expected));self.assertEqual(row["strength"],"stark",(query,expected))
        self.assertFalse(lex.match("ˈlaɪ̯dn̩ʃaft","ˈmaxn̩ʃaft"))
        self.assertTrue(lex.full_phrase_match("ˈkaltə naxt","ˈhaltə vaxt"))
        self.assertFalse(lex.full_phrase_match("ˈkaltə naxt","ˈɡʁoːsə maxt"))
        for word in ("space","case","race","beautiful","running","Elena","Lena","Helena"):
            self.assertFalse(lex.lookup(word),word)

    def test_uncertain_g2p_never_claims_perfect(self):
        p,s=lex.pronunciation_info("Jude Bellingham");self.assertTrue(p)
        rows=lex.retrieve_variants("Jude Bellingham",p,s);self.assertGreaterEqual(len(rows),5)
        self.assertTrue(all(r["strength"]=="brauchbar" for r in rows))
        self.assertEqual(lex.analysis("Jude Bellingham",p[0])["input"],"Jude Bellingham")
