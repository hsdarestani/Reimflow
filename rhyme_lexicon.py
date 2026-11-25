"""German pronunciation retrieval; no spelling-based rhyme classification.

Build an immutable SQLite index from pinned, separately licensed resources.
See docs/RHYME_LEXICON.md. The application never downloads data at runtime.
"""
import functools
import os
import re
import sqlite3
import sys
import unicodedata
from contextlib import closing
from pathlib import Path

PATH = Path(os.getenv("REIMFLOW_LEXICON", str(Path(__file__).with_name("rhyme-lexicon.sqlite"))))
VOWELS = set("aeiouyäöüɑɐɒæɛɜəɘɚɝɞɪʊɔœøɵɨʉɯʌ")
EN_ONLY = {"space", "case", "race", "face", "pace", "grace", "base", "place", "trace", "chase", "lace", "embrace", "erase", "replace", "disgrace", "showcase", "interface", "nice", "mouse", "house", "cyberspace"}
PROPER_NAMES = {"klaus", "claus", "emma", "mays", "thais", "kalahari", "karibe", "rastafari", "ali", "marie", "melanie", "geesthacht"}
EXCLUDE = EN_ONLY | PROPER_NAMES | {"jacht", "betracht", "emails"}
STANDARD_IPA = {"uni":"ˈuːni", "jury":"ˈʒyːʁi", "tee":"teː"}
# Original editorial transcriptions of independently attested German loanwords.
# Calamari: https://www.duden.de/rechtschreibung/Calamari
EDITORIAL_WORDS = {"Calamari":"kalaˈmaːʁi"}
# Original, hand-written natural line fragments, not extracted from lyrics.
# Each has an independently attested end word. Retrieve only after phonetic
# checks and only when its syllable count is close to the full query.
PHRASES = ("für mich kein Thema", "spreng das Schema", "mitten im Dilemma",
    "nachts auf Safari", "roter Sari", "kein Larifari", "durch die Nacht",
    "gegen die Macht", "hat mich zum Lachen gebracht", "gib gut acht",
    "vor dem Haus", "ich will hier raus", "stürmischer Applaus", "mit viel Gefühl",
    "kaltes Spiel", "bis ans Ziel", "über das Ziel", "nichts zu verlieren",
    "in den Gedanken", "ganz ohne Schranken", "zwischen den Zeilen", "nicht zu begreifen",
    "am Ende der Zeit", "jetzt bin ich bereit", "aus tiefstem Herzen", "in einer Welt",
    "mitten im Leben", "unter den Sternen", "auf eigene Kosten", "ich will mehr",
    "keine falsche Hoffnung", "unter Druck", "mit einem Blick", "kein Weg zurück")
FOREIGN = {
    "benzema": "bɛnˈzeːma", "karim benzema": "kaʁim bɛnˈzeːma",
    "pokerface": "ˈpoːkɐˌfɛɪ̯s", "ferrari": "feˈraːri", "blue ferrari": "bluː feˈraːri",
    "ronaldo": "ʁoˈnaldu", "messi": "ˈmesi", "bellingham": "ˈbɛlɪŋəm",
    "lamborghini": "lamborˈɡiːni", "louis vuitton": "lwi vɥiˈtɔ̃",
}
WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def phones(ipa):
    ipa = unicodedata.normalize("NFC", ipa).replace("g", "ɡ").replace("͡", "").replace("͜", "")
    out = []
    for c in ipa:
        if c in " /[].‿":
            continue
        if c in "ːˑ̯̩̃" or unicodedata.combining(c):
            if out:
                out[-1] += c
        else:
            out.append(c)
    return out


def vowel(p):
    return bool(p and p[0] in VOWELS and "̯" not in p)


def syllables(ipa):
    return sum(vowel(p) or "̩" in p for p in phones(ipa))


def tail(ipa):
    """Stress-to-end phonemes (last explicit primary or secondary stress)."""
    p = phones(ipa)
    stress = [i for i, x in enumerate(p) if x in ("ˈ", "ˌ")]
    if not stress and syllables(ipa) != 1:
        return ""
    start = next((i for i in range(stress[-1] + 1 if stress else 0, len(p)) if vowel(p[i])), None)
    return "" if start is None else "|".join(x for x in p[start:] if x not in ("ˈ", "ˌ"))


def near_key(t):
    p = t.split("|")
    if not t or len(p) < 2:
        return ""
    # Only nearby vowel qualities, with the entire remaining coda identical.
    groups = {"e": "E", "ɛ": "E", "i": "I", "ɪ": "I", "o": "O", "ɔ": "O", "u": "U", "ʊ": "U", "a": "A", "ɑ": "A", "ø": "Y", "œ": "Y", "y": "Ü", "ʏ": "Ü"}
    first = groups.get(p[0][0])
    if not first or len(p) < 2 or "̃" in p[0]:
        return ""
    # /ɛɪs/ vs /aɪs/ is a deliberately weak, documented diphthong slant.
    if len(p)>2 and p[1] in ("ɪ̯", "ɪ") and first in ("A", "E"):
        first = "AE"
    return "|".join([first, *("R" if x in ("r", "ʁ", "ɾ") else "S" if x in ("s", "z") else x for x in p[1:])])


def rhythm_key(t):
    if not t: return ""
    p=t.split("|"); nuclei=[]
    for x in p:
        if vowel(x) or "̩" in x: nuclei.append(x)
        elif "̯" in x and nuclei: nuclei[-1]+=x
    last=next((i for i in range(len(p)-1,-1,-1) if vowel(p[i])),len(p)-1)
    if len(nuclei)<2 or last==len(p)-1: return ""
    return "|".join(nuclei)+":"+"|".join(p[last+1:])


def distance(a,b):
    previous=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        current=[i]
        for j,y in enumerate(b,1):
            current.append(min(previous[j]+1,current[j-1]+1,previous[j-1]+(x!=y)))
        previous=current
    return previous[-1]


def build(ipa_file, frequency_file, output, dictionary_file):
    freq = {}
    with open(frequency_file, encoding="utf8") as f:
        for rank, line in enumerate(f):
            word, _, count = line.strip().rpartition(" ")
            if WORD.fullmatch(word) and count.isdigit():
                freq[word.casefold()] = rank
    # Independent lexical membership check, not copied definitions or affix data.
    # Capitalized entries without inflection flags are often proper names.
    dictionary = set()
    with open(dictionary_file, encoding="iso-8859-1") as f:
        for line in f:
            word, _, flags = line.strip().partition("/")
            if WORD.fullmatch(word) and (word.islower() or flags):
                dictionary.add(word)
    def attested(word):
        if word in dictionary:
            return True
        return any(word.endswith(s) and word[:-len(s)] in dictionary for s in ("e", "en", "er", "n", "s", "es"))
    out = Path(output)
    if out.exists():
        raise FileExistsError(out)
    with closing(sqlite3.connect(out)) as db, db:
        db.executescript("CREATE TABLE lex(word TEXT, folded TEXT, ipa TEXT, tail TEXT, near TEXT, rhythm TEXT, rank INTEGER, PRIMARY KEY(word,ipa));")
        rows = []
        with open(ipa_file, encoding="utf8") as f:
            for line in f:
                word, sep, raw = line.rstrip("\n").partition("\t")
                folded = word.casefold()
                if not sep or len(word)<2 or word.isupper() or folded in EXCLUDE or not WORD.fullmatch(word) or not attested(word):
                    continue
                if folded not in freq and (word not in dictionary or len(word)>13):
                    continue
                for ipa in ([STANDARD_IPA[folded]] if folded in STANDARD_IPA else raw.split(", ")[:1]):
                    ipa = ipa.strip(" /[]")
                    key = tail(ipa)
                    if key:
                        rows.append((word, folded, ipa, key, near_key(key), rhythm_key(key), freq.get(folded, 100000)))
                if len(rows) >= 3000:
                    db.executemany("INSERT OR IGNORE INTO lex VALUES(?,?,?,?,?,?,?)", rows)
                    rows.clear()
        db.executemany("INSERT OR IGNORE INTO lex VALUES(?,?,?,?,?,?,?)", rows)
        for word,ipa in EDITORIAL_WORDS.items():
            k=tail(ipa)
            db.execute("INSERT OR IGNORE INTO lex VALUES(?,?,?,?,?,?,?)",(word,word.casefold(),ipa,k,near_key(k),rhythm_key(k),40000))
        db.executescript("CREATE INDEX lex_folded ON lex(folded,rank); CREATE INDEX lex_tail ON lex(tail,rank); CREATE INDEX lex_near ON lex(near,rank); CREATE INDEX lex_rhythm ON lex(rhythm,rank);")


def available():
    return PATH.is_file()


def connect():
    return sqlite3.connect(PATH.resolve().as_uri()+"?mode=ro&immutable=1", uri=True)


@functools.lru_cache(maxsize=2048)
def lookup(word):
    if not available() or word.casefold() in EXCLUDE:
        return ()
    with closing(connect()) as db:
        rows = db.execute("SELECT word,ipa FROM lex WHERE folded=? ORDER BY word=? DESC,rank LIMIT 12", (word.casefold(), word)).fetchall()
    # Avoid choosing a different pronunciation/meaning solely through case folding.
    exact = tuple((w, i) for w, i in rows if w == word)
    return exact or tuple(rows)


def pronunciation(query):
    if query.casefold() in FOREIGN:
        return FOREIGN[query.casefold()]
    parts = query.split()
    if not parts:
        return ""
    values = []
    for word in parts:
        rows = lookup(word)
        variants = {tail(i) for _, i in rows}
        if not rows:
            return ""
        if len(variants)!=1:
            keys=list(variants)
            # Equivalent consonantal realizations, not heteronyms with different vowels.
            nuclei=lambda k:[p for p in k.split("|") if vowel(p)]
            if not all(nuclei(k)==nuclei(keys[0]) and distance(k.split("|"),keys[0].split("|"))<=1 for k in keys):
                return ""
        values.append(rows[0][1])
    return " ".join(values)


def analysis(query, ipa):
    return {"input":query, "interpreted_as":query, "ipa":ipa, "pronunciation":ipa,
            "syllables":syllables(ipa), "language":"Deutsch / Originalaussprache", "correction":None,
            "note":("Deutschsprachige Rap-Aussprache als Annäherung; Originalaussprache kann abweichen." if query.casefold() in FOREIGN else "Wörterbuchbasierter Klang; Aussprachevarianten möglich.")}


def match(target, candidate):
    a, b = tail(target), tail(candidate)
    if not a or not b:
        return None
    if a == b:
        # A final secondary stress qualifies as an end-word rhyme, not a full phrase.
        return ("Multi-Silben" if syllables(a.replace("|", "")) >= 2 else "Perfekter Reim", "stark", 2)
    if near_key(a) and near_key(a) == near_key(b):
        return ("Slant Rhyme", "brauchbar", 1)
    if rhythm_key(a) and rhythm_key(a)==rhythm_key(b):
        x,y=a.split("|"),b.split("|")
        if distance(x,y)<=min(2,max(len(x),len(y))//3):
            return ("Near Rhyme","brauchbar",1)
    return None


def candidate(word, ipa, target, category=None):
    m = match(target, ipa)
    if not m:
        return None
    kind, strength, _ = m
    return {"word":word, "ipa":ipa, "pronunciation":ipa, "syllables":syllables(ipa),
            "category":category or ("Nomen" if word[0].isupper() else "Sonstiges"), "register":"Standard",
            "kind":kind, "strength":strength, "scope":"end_word", "german_valid":True,
            "score":0, "confidence":0, "explanation":"Reimkern /"+tail(ipa).replace("|", "")+"/; "+("gleicher Klang" if strength=="stark" else "ähnliche betonte Lautfolge, kein exakter Reim")+"."}


def retrieve(query, ipa, limit=40):
    if not available() or not tail(ipa):
        return []
    key = tail(ipa)
    with closing(connect()) as db:
        rows = db.execute("SELECT word,ipa,rank FROM lex WHERE tail=? ORDER BY rank LIMIT 600", (key,)).fetchall()
        nk = near_key(key)
        if nk:
            rows += db.execute("SELECT word,ipa,rank FROM lex WHERE near=? AND tail!=? ORDER BY rank LIMIT 300", (nk,key)).fetchall()
        rk=rhythm_key(key)
        if rk:
            rows += db.execute("SELECT word,ipa,rank FROM lex WHERE rhythm=? AND tail!=? ORDER BY rank LIMIT 300", (rk,key)).fetchall()
    anchor = query.split()[-1].casefold()
    result, seen = [], {anchor}
    # Prefer ordinary words and varied sound families over many prefix compounds.
    rows.sort(key=lambda x:(tail(x[1])!=key,x[2]+max(0,len(x[0])-5)*1700))
    for word, phonetic, rank in rows:
        folded = word.casefold()
        # Avoid trivial prefix compounds of the query and conservative English exclusions.
        if folded in seen or folded in EXCLUDE or (len(anchor)>3 and folded.endswith(anchor)):
            continue
        if any(len(s)>4 and (folded.startswith(s) and len(folded)-len(s)<=2 or s.startswith(folded) and len(s)-len(folded)<=2 or folded.endswith(s) or s.endswith(folded)) for s in seen):
            continue
        row = candidate(word, phonetic, ipa)
        if row:
            seen.add(folded)
            result.append(row)
        if len(result)>=limit:
            break
    return result


def validate_word(word, target):
    if not WORD.fullmatch(word) or word.casefold() in EXCLUDE:
        return None
    return next((r for w, ipa in lookup(word) if (r:=candidate(w, ipa, target))), None)


def phrase_lexical(word):
    parts = word.split()
    return len(parts)>1 and all(WORD.fullmatch(p) and lookup(p) for p in parts)


def curated_phrases(query, ipa):
    if not ipa or len(query.split())<2: return []
    anchor=ipa.split()[-1]; count=syllables(ipa); seen=set(); out=[]
    for phrase in PHRASES:
        endpoint=phrase.split()[-1].casefold()
        if endpoint in seen or endpoint==query.split()[-1].casefold():continue
        p=pronunciation(phrase)
        if not p or abs(syllables(p)-count)>1:continue
        row=candidate(phrase,p.split()[-1],anchor,"Sonstiges")
        if not row:continue
        row.update(ipa=p,pronunciation=p,syllables=syllables(p),kind="Phrase",scope="phrase_variation",
            explanation=row["explanation"]+" Natürliche redaktionelle Wortgruppe, kein behaupteter Vollphrasenreim.")
        out.append(row);seen.add(endpoint)
    return out[:6]


def full_phrase_match(target, candidate_ipa):
    """Conservative extra evidence beyond the terminal rhyme: vowel sequence."""
    a=[p for p in phones(target) if vowel(p)]
    b=[p for p in phones(candidate_ipa) if vowel(p)]
    return len(a)==len(b) and len(a)>=3 and sum(x==y for x,y in zip(a,b))>=len(a)-1


if __name__ == "__main__":
    build(*sys.argv[1:])
