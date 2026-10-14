"""Independent and conservative second-pass rhyme quality gate.

This is a linguistic AI review, NOT an acoustic measurement or calibrated
probability. Reject weak rhymes rather than fill a predetermined count.
"""
import json
import re

QUALITY_SCHEMA = {
    "type":"object","additionalProperties":False,"required":["review"],
    "properties":{"review":{
        "type":"array","items":{
            "type":"object","additionalProperties":False,
            "required":["word","accept","strength","scope","reason"],
            "properties":{
                "word":{"type":"string"},
                "accept":{"type":"boolean"},
                "strength":{"type":"string","enum":["stark","brauchbar","schwach"]},
                "scope":{"type":"string","enum":["full_phrase","end_word","phrase_variation"]},
                "reason":{"type":"string"}
            }
        }
    }}
}
QUALITY_PROMPT = """Du bist unabhängiger, sorgfältiger Reim-Prüfer für deutsch-englische Rap-Phrasen.
Dir werden die originale Query und getrennt das letzte Wort als Reimanker gegeben.
Prüfe Vorschläge nach gesprochener Aussprache, Betonung, Reimkern (letzter
betonter Vokal bis Wortende) und tatsächlicher sprachlicher Bedeutung.

SEHR WICHTIG: Es gibt drei GÜLTIGE, UNTERSCHIEDLICHE Arten:
1) end_word = Reim auf das LETZTE Wort (Anker). Die restliche Eingabe
   muss NICHT komplett klingen wie das Kandidatenwort. Diese Art ist gerade
   bei "Blue paper" -> "caper", "taper", "scraper", "shaper" erwünscht.
2) full_phrase = natürliche mehrteilige Reimphrase, deren gesprochener Rhythmus
   und Endklang den der gesamten Query überzeugend treffen.
3) phrase_variation = sprachlich sinnvolle lyrische Formulierung, z.B.
   "Blue paper" -> "blue vapor", "true caper" (je nach English Accent);
   ungewöhnliche poetische Phrasen wie "clue shaper" allenfalls als brauchbar
   akzeptieren, wenn klar bedeutungsvoll im Rap-Kontext, nie als standardisierte
   gängige Redewendung behaupten.
WICHTIG: Einen guten end_word Reim NICHT verwerfen, weil er nicht die
GANZE Phrase reimt. Seine Art MUSS aber ehrlich als end_word markiert werden.

"Blue Ferrari" -> "Safari" oder "Calamari" können legitime end_word Reime
sein, Toyota/Karaoke/Marinade/Batterie nicht als starker Match.
Reime anhand gleicher Schreibendung/Silbenzahl ohne gemeinsame Klangfolge
ablehnen. Fake/Wortsalat und erfundene Aussprache ebenfalls ablehnen.
Ergebnisse ohne Treffer sind erlaubt, aber nicht automatisch 0 Treffer
nur weil der Gesamtphrasenreim selten ist: Endwort-Reime sinnvoll bewerten.
Ordne jedes akzeptierte Wort einer dieser drei scopes zu. Falls eine Wortform
nicht etabliert ist, erläutere die lyrische/ungewöhnliche Verwendung.
Gib für jeden erhaltenen Kandidaten accept, strength, scope, reason.
Keine Zahlen, keine künstlichen Treffer, kein Ergänzen neuer Kandidaten.
"""
def review_and_filter(query, initial, review):
    """Map accepted AI judgments back to their original suggestions only."""
    candidates=(initial.get("rhymes") or [])[:14]
    seen={}
    for item in review.get("review") or []:
        if not isinstance(item,dict):continue
        key=str(item.get("word","")).strip().casefold()
        if key and key not in seen:
            seen[key]=item
    accepted=[]
    used=set()
    for item in candidates:
        key=str(item.get("word","")).strip().casefold()
        if key in used:continue
        verdict=seen.get(key)
        if not verdict or verdict.get("accept") is not True or verdict.get("strength") not in ("stark","brauchbar"):
            continue
        used.add(key)
        row=dict(item)
        row["strength"]=verdict["strength"]
        row["scope"]=verdict.get("scope","end_word")
        row["explanation"]=str(verdict.get("reason") or row.get("explanation") or "")[:220]
        # Retain numeric fields for schema compatibility only. Not a probability.
        row["confidence"]=0
        row["score"]=0
        accepted.append(row)
    accepted.sort(key=lambda x:(0 if x["scope"] in ("full_phrase","phrase_variation") else 1,
                                0 if x["strength"]=="stark" else 1))
    result=dict(initial)
    result["rhymes"]=accepted
    result["quality_reviewed"]=True
    result["quality_method"]="independent_ai_review"
    return result

def review_input(query,initial):
    return json.dumps({
        "query_exact":query,
        "end_word":re.findall(r"[^\W\d_]+",query)[-1] if re.findall(r"[^\W\d_]+",query) else query,
        "candidate_list":[{"word":w.get("word",""),"claimed_ipa":w.get("ipa",""),
                           "claimed_kind":w.get("kind","")} for w in (initial.get("rhymes") or [])[:14]],
        "instruction":"Ignore candidate quality scores and claimed pronunciations if implausible; judge real sounding rhyme."
    },ensure_ascii=False)
