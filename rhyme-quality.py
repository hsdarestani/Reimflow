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
            "required":["word","accept","strength","reason"],
            "properties":{
                "word":{"type":"string"},
                "accept":{"type":"boolean"},
                "strength":{"type":"string","enum":["stark","brauchbar","schwach"]},
                "reason":{"type":"string"}
            }
        }
    }}
}
QUALITY_PROMPT = """Du bist ein UNABHÄNGIGER strenger Phonetik-Prüfer für deutsche und
mehrsprachige Rap-Reime. Du siehst die Query und möglicherweise fehlerhafte
Vorschläge einer anderen KI. Deine Aufgabe ist AUSSCHLIESSLICH die Prüfung.

Prüfe den hörbaren betonten Reimkern ab dem letzten betonten Vokal bis zum Ende,
einschließlich Koda, auf Basis tatsächlich plausibler Aussprache. Bei einer
mehrteiligen Query prüfe getrennt a) die ganze Phrase und b) den letzten
dominanten Reimanker. Ein Treffer nur für b) darf als brauchbar gelten,
aber nicht als Vollphrasen-Reim. Sprache und Accent unbedingt beachten;
deutsche Buchstaben-/Silbengleichheit reicht nicht aus.
WICHTIG: Weist der Vorschlag den Reimanker NICHT auf, lehne ihn AB, selbst
wenn nur ähnliche Silbenzahl, Rhythmus oder allgemeine Vokale vorhanden sind.
Beispiel: Auf 'Blue Ferrari' sind 'Toyota', 'Karaoke', 'Marinade', 'Batterie'
und 'Fabriki' keine belastbaren starken Reime. Auch ein zweisilbiges Ende
allein beweist nichts. Bei 'Ferrari' können 'Safari' und 'Calamari' bei
passender Aussprache als brauchbar gelten, aber nie als sicher perfekte
Vollphrasen-Reime. Prüfe tatsächliche Sprache und Akzent.
Phonetisch fragwürdige, erfundene oder nicht etablierte Wörter ablehnen.
Niemals Reime hinzufügen, immer nur Kandidaten bewerten. Sei kritisch!
Es ist ausdrücklich korrekt, ALLE Kandidaten abzulehnen, wenn keine guten
existieren. Gib in JSON pro Wort genau ein Urteil zurück. Die Felder
accept und strength müssen logisch zusammenpassen. Die Gründe kurz Deutsch.
"""
def review_and_filter(query, initial, review):
    """Map accepted AI judgments back to their original suggestions only."""
    candidates=(initial.get("rhymes") or [])[:8]
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
        row["explanation"]=str(verdict.get("reason") or row.get("explanation") or "")[:220]
        # Retain numeric fields for schema compatibility only. Not a probability.
        row["confidence"]=0
        row["score"]=0
        accepted.append(row)
    accepted.sort(key=lambda x:0 if x["strength"]=="stark" else 1)
    result=dict(initial)
    result["rhymes"]=accepted
    result["quality_reviewed"]=True
    result["quality_method"]="independent_ai_review"
    return result

def review_input(query,initial):
    return json.dumps({
        "query_exact":query,
        "candidate_list":[{"word":w.get("word",""),"claimed_ipa":w.get("ipa",""),
                           "claimed_kind":w.get("kind","")} for w in (initial.get("rhymes") or [])[:8]],
        "instruction":"Ignore candidate quality scores and claimed pronunciations if implausible; judge real sounding rhyme."
    },ensure_ascii=False)
