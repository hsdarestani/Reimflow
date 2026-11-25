"""German pronunciation retrieval; no spelling-based rhyme classification.

Build an immutable SQLite index from pinned, separately licensed resources.
See docs/RHYME_LEXICON.md. The application never downloads data at runtime.
"""
import functools
import csv
import os
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from contextlib import closing
from pathlib import Path
import rhyme_pronunciation as g2p

PATH = Path(os.getenv("REIMFLOW_LEXICON", str(Path(__file__).with_name("rhyme-lexicon.sqlite"))))
VOWELS = set("aeiouyäöüɑɐɒæɛɜəɘɚɝɞɪʊɔœøɵɨʉɯʌ")
EN_ONLY = {"space", "case", "race", "face", "pace", "grace", "base", "place", "trace", "chase", "lace", "embrace", "erase", "replace", "disgrace", "showcase", "interface", "nice", "mouse", "house", "cyberspace"}
PROPER_NAMES = {"klaus", "claus", "emma", "mays", "thais", "kalahari", "karibe", "rastafari", "ali", "marie", "melanie", "geesthacht"}
EXCLUDE = EN_ONLY | PROPER_NAMES | {"jacht", "betracht", "emails"}
FUNCTION_WORDS={"am","an","im","in","und","der","die","das","dem","den","des","ein","eine","ist","sind","zu","mit","für","von","bei","als","dass"}
STANDARD_IPA = {"uni":"ˈuːni", "jury":"ˈʒyːʁi", "tee":"teː", "rum":"ʁʊm"}
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
QUERY_WORD = re.compile(r"[^\W\d_]+(?:[-’'][^\W\d_]+)*", re.UNICODE)
COLLOQUIAL={"krass","geil","digga","digger","alter","kumpel","labern","quatschen","chillen","bock","abchecken","abziehen","zocken","mies","mega","drauf","raus","rein","drin","dreckig","larifari"}


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


def coarse_key(t):
    if not t:return ""
    p=t.split("|"); first=p[0][0]
    groups={"a":"A","ɑ":"A","æ":"A","ɛ":"E","e":"E","ɪ":"I","i":"I","ɔ":"O","o":"O","ʊ":"U","u":"U","y":"Y","ʏ":"Y","ø":"O","œ":"O","ə":"schwa","ɐ":"schwa"}
    if first not in groups:return ""
    coda=re.sub(r"[ːˑ̩̯]","","".join(p[-2:]))
    coda=coda.translate(str.maketrans({"b":"p","d":"t","ɡ":"k","z":"s","v":"f","ʒ":"ʃ","r":"ʁ","ɾ":"ʁ"}))
    return groups[first]+":"+coda[-1:]

def build(ipa_file, frequency_file, output, dictionary_file, morphology_file=None, english_file=None, nouns_file=None):
    freq = {}
    with open(frequency_file, encoding="utf8") as f:
        for rank, line in enumerate(f):
            word, _, count = line.strip().rpartition(" ")
            if WORD.fullmatch(word) and count.isdigit():
                freq[word.casefold()] = rank
    # Independent lexical membership check, not copied definitions or affix data.
    # Capitalized entries without inflection flags are often proper names.
    dictionary = set(); dictionary_flags={}
    with open(dictionary_file, encoding="iso-8859-1") as f:
        for line in f:
            word, _, flags = line.strip().partition("/")
            if WORD.fullmatch(word) and (word.islower() or flags):
                dictionary.add(word)
                dictionary_flags[word]=flags
    def attested(word):
        if word in dictionary:
            return True
        return any(word.endswith(s) and word[:-len(s)] in dictionary for s in ("e", "en", "er", "n", "s", "es"))
    morph=defaultdict(set)
    if morphology_file:
        with open(morphology_file,encoding="utf8") as f:
            for line in f:
                fields=line.rstrip("\n").split("\t")
                if len(fields)!=3:continue
                lemma,form,features=fields; category={"N":"Nomen","V":"Verb","ADJ":"Adjektiv"}.get(features.split(";")[0].split(".")[0])
                if category and WORD.fullmatch(lemma):
                    morph[lemma].add((category,lemma))
                    if WORD.fullmatch(form):morph[form].add((category,lemma))
    english=set()
    if english_file:
        with open(english_file,encoding="utf8") as f:
            for line in f:english.add(line.split("\t",1)[0].casefold())
    common_nouns=set(); proper_nouns=set()
    if nouns_file:
        with open(nouns_file,encoding="utf8",newline="") as f:
            for row in csv.DictReader(f):
                lemma=row['lemma']; tags=set(row['pos'].split(','))
                proper=bool(tags&{"Toponym","Vorname","Nachname","Eigenname","Straßenname"})
                if not WORD.fullmatch(lemma):continue
                if proper:proper_nouns.add(lemma.casefold());continue
                if "Substantiv" not in tags or tags&{"Abkürzung","Symbol","Buchstabe","Affix","Gebundenes Lexem"}:continue
                if not any(row.get(k) for k in ('genus','genus 1','genus 2','genus 3','genus 4')) and lemma not in dictionary and not morph.get(lemma):continue
                forms=[lemma]+[v for k,v in row.items() if k and k.startswith(('nominativ','genitiv','dativ','akkusativ')) and isinstance(v,str) and WORD.fullmatch(v)]
                for form in forms:
                    common_nouns.add(form.casefold());morph[form].add(("Nomen",lemma))
    out = Path(output)
    if out.exists():
        raise FileExistsError(out)
    with closing(sqlite3.connect(out)) as db, db:
        db.executescript("CREATE TABLE lex(word TEXT, folded TEXT, ipa TEXT, tail TEXT, near TEXT, rhythm TEXT, rank INTEGER, coarse TEXT, categories TEXT, lemma TEXT, PRIMARY KEY(word,ipa)); CREATE TABLE pron(word TEXT, folded TEXT, ipa TEXT, lang TEXT, PRIMARY KEY(word,ipa,lang));")
        rows = []; prows=[]
        with open(ipa_file, encoding="utf8") as f:
            for line in f:
                word, sep, raw = line.rstrip("\n").partition("\t")
                folded = word.casefold()
                if sep and QUERY_WORD.fullmatch(word) and len(word)<=60:
                    for p in raw.split(", ")[:3]:
                        p=p.strip(" /[]")
                        if p and syllables(p):prows.append((word,folded,p,"de"))
                if len(prows)>=5000:
                    db.executemany("INSERT OR IGNORE INTO pron VALUES(?,?,?,?)",prows);prows.clear()
                if not sep or len(word)<2 or word.isupper() or folded in EXCLUDE or not WORD.fullmatch(word):
                    continue
                metadata=morph.get(word,set()); categories=sorted({c for c,_ in metadata}); lemmas=sorted({l for _,l in metadata},key=lambda x:(x!=word,len(x),x))
                if folded in proper_nouns and folded not in common_nouns:continue
                if not attested(word) and not (folded in common_nouns and metadata):continue
                # Bare plural-S proper-name entries lack German noun morphology.
                if word[0].isupper() and dictionary_flags.get(word)=="S" and folded not in common_nouns:continue
                if folded in english and not metadata and word not in dictionary:continue
                if folded not in freq and (word not in dictionary or len(word)>13) and not (metadata and len(word)<=18 and any(l.casefold() in freq for _,l in metadata)):
                    continue
                if folded in COLLOQUIAL:categories.append("Umgangssprache")
                for ipa in ([STANDARD_IPA[folded]] if folded in STANDARD_IPA else raw.split(", ")[:1]):
                    ipa = ipa.strip(" /[]")
                    key = tail(ipa)
                    if key:
                        rows.append((word, folded, ipa, key, near_key(key), rhythm_key(key), freq.get(folded, 100000),coarse_key(key),",".join(categories),lemmas[0] if lemmas else word))
                if len(rows) >= 3000:
                    db.executemany("INSERT OR IGNORE INTO lex VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
                    rows.clear()
        db.executemany("INSERT OR IGNORE INTO lex VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
        db.executemany("INSERT OR IGNORE INTO pron VALUES(?,?,?,?)",prows);prows.clear()
        if english_file:
            with open(english_file,encoding="utf8") as f:
                for line in f:
                    word,sep,raw=line.rstrip("\n").partition("\t")
                    if sep and QUERY_WORD.fullmatch(word):
                        for p in raw.split(", ")[:2]:prows.append((word,word.casefold(),p.strip(" /[]"),"en"))
                    if len(prows)>=5000:db.executemany("INSERT OR IGNORE INTO pron VALUES(?,?,?,?)",prows);prows.clear()
            db.executemany("INSERT OR IGNORE INTO pron VALUES(?,?,?,?)",prows)
        for word,ipa in EDITORIAL_WORDS.items():
            k=tail(ipa)
            db.execute("INSERT OR IGNORE INTO lex VALUES(?,?,?,?,?,?,?,?,?,?)",(word,word.casefold(),ipa,k,near_key(k),rhythm_key(k),40000,coarse_key(k),"Nomen",word))
        db.executescript("CREATE INDEX lex_folded ON lex(folded,rank); CREATE INDEX lex_tail ON lex(tail,rank); CREATE INDEX lex_near ON lex(near,rank); CREATE INDEX lex_rhythm ON lex(rhythm,rank); CREATE INDEX lex_coarse ON lex(coarse,rank); CREATE INDEX pron_folded ON pron(folded,lang);")


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


@functools.lru_cache(maxsize=4096)
def query_lookup(word):
    if not available(): return ()
    with closing(connect()) as db:
        try:return tuple(db.execute("SELECT word,ipa,lang FROM pron WHERE folded=? ORDER BY word=? DESC,rowid LIMIT 18",(word.casefold(),word)))
        except sqlite3.OperationalError:return ()

@functools.lru_cache(maxsize=4096)
def pronunciation_info(query):
    """Return pronunciation hypotheses and provenance; query-only entries never become candidates."""
    if query.casefold() in FOREIGN:
        return (FOREIGN[query.casefold()],),"editorial"
    parts = QUERY_WORD.findall(query)
    if not parts:
        return (),"unsupported"
    english_context=any(g2p.language_hypotheses(w)[0]=="en-us" for w in parts)
    if len(parts)>1 and not english_context:
        english_context=any(any(lang=="en" for _,_,lang in query_lookup(w)) and not any(lang=="de" for _,_,lang in query_lookup(w)) for w in parts)
    primary=[]; alternative=[]; inferred=False; ambiguous=False
    context_voices=[g2p.language_hypotheses(w)[0] for w in parts if g2p.language_hypotheses(w)[0] not in ("de","en-us")]
    for word in parts:
        rows=lookup(word); readings=query_lookup(word)
        voices=g2p.language_hypotheses(word,english_context)
        if voices==("de",) and context_voices and not rows:voices=(context_voices[0],"de")
        preferred="en" if voices[0]=="en-us" else "de"
        variants=[p for w,p,l in readings if l==preferred and w==word] or [p for w,p,l in readings if l==preferred]
        if preferred=="de" and rows:
            variants=[rows[0][1]]+variants
        if not variants and preferred=="de":variants=[p for _,p,l in readings if l=="en"]
        if voices[0] not in ("de","en-us") and not rows:
            inferred=True;variants=[g2p.phonemize(word,v) for v in voices[:2]]+variants
        if not variants:
            inferred=True; variants=[g2p.phonemize(word,v) for v in voices[:2]]
        if preferred=="en" and word[0].isupper():inferred=True
        if variants and preferred=="de" and not rows and len(parts)==1:
            alternate=g2p.phonemize(word,"de")
            if alternate and tail(alternate)!=tail(variants[0]):
                variants=[variants[0],alternate]+variants[1:];ambiguous=True
        variants=list(dict.fromkeys(p for p in variants if p and tail(p)))
        if word.casefold() in FOREIGN:
            variants=[FOREIGN[word.casefold()]]+[p for p in variants if p!=FOREIGN[word.casefold()]];inferred=True
        if not variants:return (),"unsupported"
        primary.append(variants[0]); alternative.append(variants[1] if len(variants)>1 else variants[0])
        if len(variants)>1 and tail(variants[0])!=tail(variants[1]):ambiguous=True
    values=tuple(dict.fromkeys((" ".join(primary)," ".join(alternative))))
    return values,"inferred" if inferred else "variant" if ambiguous else "dictionary"

def pronunciation(query):
    values,_=pronunciation_info(query)
    return values[0] if values else ""


def analysis(query, ipa):
    variants,source=pronunciation_info(query)
    note=("Lokal geschätzte Aussprache; Varianten möglich, Treffer sind Klangannäherungen." if source in ("inferred","variant") else "Deutschsprachige Rap-Aussprache als Annäherung; Originalaussprache kann abweichen." if source=="editorial" else "Wörterbuchbasierter Klang; Aussprachevarianten möglich.")
    if len(variants)>1:note+=" Alternative: /"+variants[1]+"/."
    return {"input":query, "interpreted_as":query, "ipa":ipa, "pronunciation":ipa,
            "syllables":syllables(ipa), "language":"Deutsch / Originalaussprache", "correction":None,
            "pronunciation_source":source,"pronunciation_variants":list(variants),"note":note}

_VOICE_GROUPS=(set("bp"),set("dt"),set("ɡk"),set("sz"),set("fv"),set("ʃʒ"),set("rʁɾɹ"),set("mnŋ"),set("aɑæ"),set("eɛ"),set("iɪ"),set("oɔ"),set("uʊ"),set("yʏ"),set("øœ"),set("əɐ"))

def substitution(a,b):
    if a==b:return 0.
    if not a or not b:return 1.
    if a[0]==b[0]:return .35 if ("̃" in a)==("̃" in b) else .9
    if vowel(a)!=vowel(b):return 1.75
    if any(a[0] in g and b[0] in g for g in _VOICE_GROUPS):return .45 if vowel(a) else .35
    if {a[0],b[0]} in ({"ɔ","œ"},{"o","ø"}):return .6
    return 1.3 if vowel(a) else .85

def weighted_distance(a,b):
    previous=[0.]
    for p in b:previous.append(previous[-1]+(1.3 if vowel(p) else .8))
    for x in a:
        cost=1.3 if vowel(x) else .8; current=[previous[0]+cost]
        for j,y in enumerate(b,1):current.append(min(previous[j]+cost,current[j-1]+(1.3 if vowel(y) else .8),previous[j-1]+substitution(x,y)))
        previous=current
    return previous[-1]


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
    if coarse_key(a) and coarse_key(a)==coarse_key(b):
        x,y=a.split("|"),b.split("|")
        # Require stressed vowel compatibility and close full tail, not merely coda.
        dip=lambda p:len(p)>1 and "̯" in p[1]
        if dip(x)!=dip(y) or vowel(x[-1]) or vowel(y[-1]):return None
        if substitution(x[0],y[0])<=.65 and abs(syllables(a.replace("|",""))-syllables(b.replace("|","")))<=1:
            d=weighted_distance(x,y)
            if d<=min(1.65,max(.55,max(len(x),len(y))*.28)):
                return ("Near Rhyme","brauchbar",1)
    return None


@functools.lru_cache(maxsize=4096)
def grammatical_categories(word):
    if not available():return ()
    with closing(connect()) as db:
        try:rows=db.execute("SELECT categories FROM lex WHERE folded=? AND word=?",(word.casefold(),word)).fetchall()
        except sqlite3.OperationalError:return ()
    return tuple(dict.fromkeys(c for row in rows for c in row[0].split(",") if c))

def candidate(word, ipa, target, category=None, categories=None):
    m = match(target, ipa)
    if not m:
        return None
    kind, strength, _ = m
    cats=list(categories if categories is not None else grammatical_categories(word))
    if category:cats=[category]
    if not cats:cats=["Sonstiges"]
    return {"word":word, "ipa":ipa, "pronunciation":ipa, "syllables":syllables(ipa),
            "category":cats[0],"categories":cats,"register":"Umgangssprache" if "Umgangssprache" in cats else "Standard",
            "kind":kind, "strength":strength, "scope":"end_word", "german_valid":True,
            "score":0, "confidence":0, "explanation":"Reimkern /"+tail(ipa).replace("|", "")+"/; "+("gleicher Klang" if strength=="stark" else "ähnliche betonte Lautfolge, kein exakter Reim")+"."}


def retrieve(query, ipa, limit=40):
    if not available() or not tail(ipa):
        return []
    key = tail(ipa)
    with closing(connect()) as db:
        fields="word,ipa,rank,categories,lemma"
        rows = db.execute(f"SELECT {fields} FROM lex WHERE tail=? ORDER BY rank LIMIT 600", (key,)).fetchall()
        nk = near_key(key)
        if nk:
            rows += db.execute(f"SELECT {fields} FROM lex WHERE near=? AND tail!=? ORDER BY rank LIMIT 300", (nk,key)).fetchall()
        rk=rhythm_key(key)
        if rk:
            rows += db.execute(f"SELECT {fields} FROM lex WHERE rhythm=? AND tail!=? ORDER BY rank LIMIT 300", (rk,key)).fetchall()
        if len(rows)<70 and coarse_key(key):
            rows += db.execute(f"SELECT {fields} FROM lex WHERE coarse=? AND tail!=? ORDER BY rank LIMIT 350",(coarse_key(key),key)).fetchall()
    anchor = query.split()[-1].casefold()
    result, seen = [], {anchor}; families=defaultdict(int); endings=defaultdict(int)
    # Prefer ordinary words and varied sound families over many prefix compounds.
    rows.sort(key=lambda x:(tail(x[1])!=key,x[2]+max(0,len(x[0])-5)*1700))
    for word, phonetic, rank, categories, lemma in rows:
        folded = word.casefold()
        # Avoid trivial prefix compounds of the query and conservative English exclusions.
        if folded in seen or folded in EXCLUDE or folded in FUNCTION_WORDS or (len(anchor)>3 and folded.endswith(anchor) and folded[:-len(anchor)] in {"ge","be","ver","ent","er","un","ur","hin","her","mit","vor","nach","auf","ab","an","aus","ein","zu","über","unter"}):
            continue
        if len(anchor)>3 and folded.endswith(anchor) and lookup(folded[:-len(anchor)]):continue
        family=lemma.casefold()
        if families[family]>=1:continue
        ending=folded[-5:] if len(folded)>5 and folded[-5] not in "aeiouäöü" else folded[-6:]
        if endings[ending]>=3:continue
        if any(len(s)>4 and (folded.startswith(s) and len(folded)-len(s)<=2 or s.startswith(folded) and len(s)-len(folded)<=2) for s in seen):
            continue
        cats=tuple(c for c in categories.split(",") if c)
        if folded in COLLOQUIAL and "Umgangssprache" not in cats:cats+=('Umgangssprache',)
        row = candidate(word, phonetic, ipa,categories=cats)
        if row:
            if rank>=100000 and row['strength']!='stark' and folded not in COLLOQUIAL:continue
            seen.add(folded)
            families[family]+=1
            endings[ending]+=1
            result.append(row)
        if len(result)>=limit:
            break
    return result

def retrieve_variants(query, variants, source, limit=40):
    if source in ("inferred","variant"):limit=min(limit,25)
    result=[]; seen=set()
    for i,ipa in enumerate(variants[:2]):
        for row in retrieve(query,ipa.split()[-1],limit):
            if row["word"].casefold() in seen:continue
            if source=="inferred" or i:
                row={**row,"strength":"brauchbar","kind":"Slant Rhyme","explanation":row["explanation"]+" Gilt für Aussprachevariante /"+ipa+"/."}
            result.append(row);seen.add(row["word"].casefold())
    if len(result)<8 and len(query.split())==1 and variants:
        component=compound_anchor(query,variants[0])
        if component:
            for row in retrieve(query,component,limit):
                if row["word"].casefold() in seen:continue
                result.append({**row,"strength":"brauchbar","kind":"Slant Rhyme","scope":"end_word","explanation":row["explanation"]+" Nur das abschließende Kompositionsglied."});seen.add(row["word"].casefold())
    return sorted(result,key=lambda r:r["strength"]!="stark")[:limit]

@functools.lru_cache(maxsize=1024)
def compound_anchor(word,ipa):
    """Find a lexically attested two-part compound and check the actual G2P ending."""
    if len(word)<8 or not WORD.fullmatch(word):return ""
    full=[p for p in phones(ipa) if p not in ("ˈ","ˌ")]
    for split in range(3,len(word)-3):
        left,right=word[:split],word[split:]; entries=lookup(right)
        if not entries or not (lookup(left) or query_lookup(left) or left.endswith('s') and lookup(left[:-1])):continue
        for _,p in entries:
            end=[x for x in phones(p) if x not in ("ˈ","ˌ")]
            if end and len(full)>=len(end) and weighted_distance(full[-len(end):],end)<=.65:return p
    return ""


def validate_word(word, target):
    if not WORD.fullmatch(word) or word.casefold() in EXCLUDE:
        return None
    return next((r for w, ipa in lookup(word) if (r:=candidate(w, ipa, target))), None)


def phrase_lexical(word):
    parts = word.split()
    return len(parts)>1 and all(WORD.fullmatch(p) and lookup(p) for p in parts)

def lexical_phrase_ipa(word):
    rows=[lookup(p) for p in word.split()]
    return " ".join(r[0][1] for r in rows) if rows and all(rows) else ""


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
    """Require cross-word stress, nuclei and consonant alignment beyond end rhyme."""
    if len(target.split())<2 or len(candidate_ipa.split())<2:return False
    a=[p for p in phones(target) if p not in ("ˈ","ˌ")]; b=[p for p in phones(candidate_ipa) if p not in ("ˈ","ˌ")]
    x=[p for p in a if vowel(p)];y=[p for p in b if vowel(p)]
    if len(x)!=len(y) or len(x)<3 or any(substitution(p,q)>.55 for p,q in zip(x,y)):return False
    # Prefix alignment prevents terminal word coincidence from being enough.
    prefix_a=[p for p in phones(" ".join(target.split()[:-1])) if p not in ("ˈ","ˌ")]
    prefix_b=[p for p in phones(" ".join(candidate_ipa.split()[:-1])) if p not in ("ˈ","ˌ")]
    return bool(prefix_a and prefix_b and weighted_distance(prefix_a,prefix_b)<=max(1.0,max(len(prefix_a),len(prefix_b))*.32) and weighted_distance(a,b)<=max(len(a),len(b))*.30)

def constructed_phrases(query,ipa,rows):
    """Reusable, grammatical infinitive/predicative templates; only common lemmas."""
    if len(query.split())<2:return []
    count=syllables(ipa); output=[]
    for row in rows:
        word=row['word'];cats=row.get('categories',[])
        if word.islower() and "Verb" in cats and word.endswith(('en','ern','eln')):prefix="ich will "
        elif word.islower() and "Adjektiv" in cats and not word.endswith(('e','em','en','er','es')):prefix="ich bin "
        else:continue
        with closing(connect()) as db:
            record=db.execute("SELECT rank,lemma FROM lex WHERE word=? LIMIT 1",(word,)).fetchone()
        if not record or record[0]>12000 or record[1]!=word:continue
        phrase=prefix+word;p=lexical_phrase_ipa(phrase)
        if not p or abs(syllables(p)-count)>1:continue
        output.append({**row,"word":phrase,"ipa":p,"pronunciation":p,"syllables":syllables(p),"category":"Sonstiges","categories":["Sonstiges"],"kind":"Phrase","scope":"phrase_variation","explanation":row["explanation"]+" Grammatisch gebildete Endwortvariation."})
        if len(output)>=4:break
    return output


if __name__ == "__main__":
    build(*sys.argv[1:])
