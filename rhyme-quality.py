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
            "required":["word","accept","strength","scope","reason","german_valid"],
            "properties":{
                "word":{"type":"string"},
                "accept":{"type":"boolean"},
                "german_valid":{"type":"boolean"},
                "strength":{"type":"string","enum":["stark","brauchbar","schwach"]},
                "scope":{"type":"string","enum":["full_phrase","end_word","phrase_variation"]},
                "reason":{"type":"string"}
            }
        }
    }}
}
QUALITY_PROMPT = """Du bist unabhängiger, sorgfältiger Reim-Prüfer für ausschließlich DEUTSCHE Rap-Reime. Die Eingabe darf fremdsprachig sein, aber ALLE vorgeschlagenen Reime müssen deutsche Wörter oder natürlich deutschsprachige Phrasen sein.
Dir werden die originale Query und getrennt das letzte Wort als Reimanker gegeben.
Prüfe Vorschläge nach gesprochener Aussprache, Betonung, Reimkern (letzter
betonter Vokal bis Wortende) und tatsächlicher sprachlicher Bedeutung.

Prüfe zwingend zusätzlich die Kandidatensprache: german_valid=true gilt NUR für tatsächlich gebräuchliche deutsche Wörter, natürliche deutsche Wendungen oder etablierten deutschsprachigen Rap-Slang.
Im Deutschen fest etablierte Lehnwörter können zulässig sein, aber reine englische Wörter, englische Phrasen, Code-Switching und fremdsprachige Eigennamen sind NICHT erlaubt.
Bei nicht deutschem Kandidaten: german_valid=false UND accept=false, auch wenn der Reim phonetisch perfekt wäre. Keine Kunstwörter und keine künstlich eingedeutschten Schreibungen.
Die Eingabe darf jede Sprache haben und muss in ihrer echten Originalaussprache interpretiert werden. Die Ergebnisse bleiben ausschließlich DEUTSCH. Alle Erklärungen auf Deutsch.

Drei gültige Reim-Scopes:
1) end_word: natürlicher deutscher Reim auf das letzte betonte Wort der Eingabe, nicht zwingend auf die gesamte Query.
2) full_phrase: natürliche mehrteilige DEUTSCHE Reimphrase, die Rhythmus und Endklang der Query überzeugend trifft.
3) phrase_variation: sinnvolle kreative DEUTSCHE Rap-Formulierung.
Einen guten deutschen end_word-Reim nicht verwerfen, weil er nicht die ganze Phrase reimt. Aber korrekt scope=end_word markieren.
Reime anhand gleicher Schreibendung/Silbenzahl ohne gemeinsame Klangfolge
ablehnen. Fake/Wortsalat und erfundene Aussprache ebenfalls ablehnen.
Ergebnisse ohne Treffer sind erlaubt, aber nicht automatisch 0 Treffer
nur weil der Gesamtphrasenreim selten ist: Endwort-Reime sinnvoll bewerten.
Ordne jedes akzeptierte Wort einer dieser drei scopes zu. Falls eine Wortform
nicht etabliert ist, erläutere die lyrische/ungewöhnliche Verwendung.
Gib für jeden erhaltenen Kandidaten german_valid, accept, strength, scope, reason.
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
        if (not verdict or verdict.get("german_valid") is not True or
                verdict.get("accept") is not True or
                verdict.get("strength") not in ("stark","brauchbar") or
                item.get("register")=="Englisch/Code-Switch"):
            continue
        used.add(key)
        row=dict(item)
        row["german_valid"]=True  # Only second-pass verified German candidates reach the UI.
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
        "instruction":"Only German words and German phrases are allowed. Reject English rhymes and code-switches even when phonetically perfect. Ignore claimed scores and pronunciations if implausible."
    },ensure_ascii=False)
