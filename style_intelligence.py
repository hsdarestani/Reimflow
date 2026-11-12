"""Licensed-corpus rhyme intelligence for Reimflow.

Only operator-supplied, rights-cleared lyrics are ingested. No full lyric text,
lines, or reconstructable snippets are retained or sent to the language model.
Derived features are approximations; independent phonetic review remains required.
"""
import argparse
import collections
import datetime
import hashlib
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

ARTISTS = ("Eko", "Kollegah", "Ali As", "Sadiq", "Shindy", "Bushido", "Mo Trip", "SSIO", "Miami Yacine")
ARTIST_ALIASES = {"MoTrip": "Mo Trip", "Ssio": "SSIO"}
WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", re.UNICODE)
VOWELS = re.compile(r"[aeiouyäöü]+", re.I)
MAX_FILE_BYTES = 2_000_000

def connect(path):
    location = Path(path)
    location.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(location), timeout=12)
    c.execute("PRAGMA busy_timeout=12000")
    c.execute("""CREATE TABLE IF NOT EXISTS rf_lyric_sources (
        source_id TEXT PRIMARY KEY, artist TEXT NOT NULL, title TEXT NOT NULL,
        source_url TEXT NOT NULL, rights_ref TEXT NOT NULL,
        valid_until TEXT NOT NULL, digest TEXT NOT NULL,
        lines_analyzed INTEGER NOT NULL, created_at INTEGER NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS rf_lyric_features (
        source_id TEXT NOT NULL REFERENCES rf_lyric_sources(source_id) ON DELETE CASCADE,
        ending TEXT NOT NULL, word_count INTEGER NOT NULL, syllables_est INTEGER NOT NULL,
        repeated_ending INTEGER NOT NULL, occurrences INTEGER NOT NULL,
        PRIMARY KEY(source_id,ending,word_count,syllables_est,repeated_ending))""")
    c.execute("""CREATE TABLE IF NOT EXISTS rf_rhyme_feedback (
        user_id INTEGER NOT NULL REFERENCES rf_users(id) ON DELETE CASCADE,
        query_hash TEXT NOT NULL, word TEXT NOT NULL,
        vote INTEGER NOT NULL CHECK(vote IN (-1,1)), updated_at INTEGER NOT NULL,
        PRIMARY KEY(user_id,query_hash,word))""")
    c.execute("CREATE INDEX IF NOT EXISTS rf_feedback_query ON rf_rhyme_feedback(query_hash)")
    c.commit()
    return c

def tokens(line):
    return [x.casefold() for x in WORD.findall(line) if len(x) <= 40]

def syllables_est(token):
    n = len(VOWELS.findall(token))
    return max(1, min(12, n))

def ending(token):
    """Orthographic candidate index, NOT an assertion of phonetic rhyme."""
    t = token.casefold()
    return t[-4:] if len(t) >= 4 else t

def analyze(text):
    """Keep only non-reconstructive aggregate line statistics."""
    counts = collections.Counter()
    seen = collections.Counter()
    lines = 0
    for line in text.splitlines()[:20000]:
        words = tokens(line)
        if not 2 <= len(words) <= 60:
            continue
        lines += 1
        suffix = ending(words[-1])
        seen[suffix] += 1
        word_count = min(20, len(words))
        syllables = min(50, sum(syllables_est(w) for w in words))
        # Repeated is a whole-track rhyme family indicator, not a rhyme judgment.
        counts[(suffix, word_count, syllables)] += 1
    if lines < 4:
        raise ValueError("At least four eligible lyric lines are required")
    rows = [(s, w, y, int(seen[s] >= 2), n) for (s, w, y), n in counts.items()]
    return rows, lines

def import_licensed(path, *, db_path, artist, title, source_url, rights_ref, valid_until):
    artist = ARTIST_ALIASES.get(artist, artist)
    if artist not in ARTISTS:
        raise ValueError("Unsupported artist")
    if not all(isinstance(v, str) and v.strip() for v in (title,source_url,rights_ref)):
        raise ValueError("Provenance and rights reference are required")
    if not source_url.startswith(("https://", "urn:")):
        raise ValueError("Use an HTTPS source or rights registry URN")
    until = datetime.date.fromisoformat(valid_until)
    if until < datetime.date.today():
        raise ValueError("The license has expired")
    if str(path) == "-":
        data = sys.stdin.buffer.read(MAX_FILE_BYTES+1)
        if not data or len(data)>MAX_FILE_BYTES:
            raise ValueError("Invalid or oversized UTF-8 input")
    else:
        source = Path(path)
        if source.suffix.lower() != ".txt" or not source.is_file() or source.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("Only a local UTF-8 .txt file up to 2MB is accepted")
        data = source.read_bytes()
    text = data.decode("utf-8-sig")
    rows, lines = analyze(text)
    digest = hashlib.sha256(data).hexdigest()
    source_id = hashlib.sha256((artist+"\0"+title+"\0"+source_url).encode()).hexdigest()[:32]
    with connect(db_path) as c:
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("DELETE FROM rf_lyric_features WHERE source_id=?", (source_id,))
        c.execute("""INSERT INTO rf_lyric_sources
            (source_id,artist,title,source_url,rights_ref,valid_until,digest,lines_analyzed,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(source_id) DO UPDATE SET artist=excluded.artist,title=excluded.title,
            source_url=excluded.source_url,rights_ref=excluded.rights_ref,
            valid_until=excluded.valid_until,digest=excluded.digest,
            lines_analyzed=excluded.lines_analyzed,created_at=excluded.created_at""",
            (source_id,artist,title,source_url,rights_ref,valid_until,digest,lines,time.time_ns()))
        c.executemany("""INSERT INTO rf_lyric_features
            (source_id,ending,word_count,syllables_est,repeated_ending,occurrences)
            VALUES(?,?,?,?,?,?)""", ((source_id,*row) for row in rows))
        c.commit()
    return {"source_id":source_id,"artist":artist,"lines_analyzed":lines,
            "feature_rows":len(rows),"raw_lyrics_stored":False}

def _query_hash(query):
    return hashlib.sha256(query.strip().casefold().encode("utf-8")).hexdigest()

def status(path):
    try:
        with connect(path) as c:
            active = c.execute("""SELECT COUNT(*),COUNT(DISTINCT artist),COALESCE(SUM(lines_analyzed),0),
                COALESCE(MAX(created_at),0) FROM rf_lyric_sources WHERE valid_until>=date('now')""").fetchone()
            count = c.execute("SELECT COUNT(*),COALESCE(MAX(updated_at),0) FROM rf_rhyme_feedback").fetchone()
        return {"licensed_tracks":active[0],"artists_covered":active[1],"lines_analyzed":active[2],
                "feedback_count":count[0],"_latest":max(active[3] * 1_000_000_000, count[1])}
    except sqlite3.Error:
        return {"licensed_tracks":0,"artists_covered":0,"lines_analyzed":0,"feedback_count":0,"_latest":0}

def revision(path, query):
    """Per-query feedback revision plus licensed-corpus fingerprint; no global vote cache bust."""
    try:
        with connect(path) as c:
            sources=c.execute("""SELECT source_id,digest,valid_until
                FROM rf_lyric_sources WHERE valid_until>=date('now')
                ORDER BY source_id""").fetchall()
            votes=c.execute("""SELECT COUNT(*),COALESCE(MAX(updated_at),0)
                FROM rf_rhyme_feedback WHERE query_hash=?""",(_query_hash(query),)).fetchone()
        blob=json.dumps([sources, votes],ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf8")).hexdigest()[:24]
    except sqlite3.Error:
        return "no-database"

def context(path, query):
    """Return only aggregate pattern information. Never output lyrics or artist imitation."""
    query_words = tokens(query)
    if not query_words:
        return {"available":False,"patterns":[],"feedback":[]}
    tail = ending(query_words[-1])
    qhash = _query_hash(query)
    try:
        with connect(path) as c:
            rows = c.execute("""SELECT f.ending,COUNT(DISTINCT f.source_id),
                        SUM(f.occurrences),ROUND(AVG(f.word_count),1),
                        ROUND(AVG(f.syllables_est),1),SUM(f.repeated_ending)
                FROM rf_lyric_features f JOIN rf_lyric_sources s ON s.source_id=f.source_id
                WHERE s.valid_until>=date('now')
                GROUP BY f.ending
                ORDER BY CASE WHEN f.ending=? THEN 0
                              WHEN substr(f.ending,-2)=substr(?,-2) THEN 1 ELSE 2 END,
                         SUM(f.occurrences) DESC LIMIT 6""", (tail,tail)).fetchall()
            feedback = c.execute("""SELECT word,SUM(CASE WHEN vote=1 THEN 1 ELSE 0 END),
                       SUM(CASE WHEN vote=-1 THEN 1 ELSE 0 END)
                       FROM rf_rhyme_feedback WHERE query_hash=?
                       GROUP BY word HAVING COUNT(*)>=3 ORDER BY COUNT(*) DESC LIMIT 6""",
                       (qhash,)).fetchall()
        return {"available":bool(rows),"patterns":[
            {"orthographic_ending":x[0],"tracks":x[1],"line_occurrences":x[2],
             "avg_words_per_line_est":x[3],"avg_syllables_per_line_est":x[4],
             "repeated_ending_rows":x[5]} for x in rows],
            "feedback":[{"word":w,"positive":p,"negative":n} for w,p,n in feedback],
            "limitations":"Schreibungsbasierte Muster und Silbenzahlschätzungen; kein phonetischer Beweis.",
            "usage":"Nutze nur abstrakte Strukturhinweise. Erzeuge originelle Vorschläge, keine Songzeilen, keine enge Nachahmung bestimmter Künstler."}
    except sqlite3.Error:
        return {"available":False,"patterns":[],"feedback":[]}

def record_feedback(db_connection, *, user_id, query, word, vote):
    if vote not in (1,-1) or not isinstance(query,str) or not 1<=len(query)<=120:
        raise ValueError("Invalid feedback")
    if not isinstance(word,str) or not 1<=len(word)<=90 or "\n" in word:
        raise ValueError("Invalid candidate")
    # Only already independently reviewed and cached suggestions are eligible.
    key = hashlib.sha256(("rhymes|de-only-query-v2|"+query.strip().casefold()).encode()).hexdigest()
    row = db_connection.execute("SELECT payload FROM cache WHERE cache_key=?", (key,)).fetchone()
    if not row:
        raise ValueError("Only verified search results can be rated")
    result = json.loads(row[0])
    if not result.get("quality_reviewed") or not any(
            x.get("word","").casefold()==word.casefold() and x.get("german_valid") is True
            for x in (result.get("rhymes") or [])):
        raise ValueError("Candidate not approved")
    # Created only for authenticated users by the platform API.
    db_connection.execute("""INSERT INTO rf_rhyme_feedback(user_id,query_hash,word,vote,updated_at)
        VALUES(?,?,?,?,?)
        ON CONFLICT(user_id,query_hash,word)
        DO UPDATE SET vote=excluded.vote, updated_at=excluded.updated_at""",
        (user_id,_query_hash(query),word.casefold(),vote,time.time_ns()))

def revoke(path, source_id):
    if not re.fullmatch(r"[a-f0-9]{32}",source_id or ""):
        raise ValueError("Invalid source ID")
    with connect(path) as c:
        c.execute("PRAGMA foreign_keys=ON")
        removed=c.execute("DELETE FROM rf_lyric_sources WHERE source_id=?",(source_id,)).rowcount
        c.commit()
    return {"source_id":source_id,"revoked":removed==1}

def cli():
    parser = argparse.ArgumentParser(description="Import licensed lyric text as NON-reconstructive features")
    parser.add_argument("command",choices=["ingest","status","revoke"])
    parser.add_argument("--db",default="/var/lib/reimflow/reimflow.sqlite3")
    parser.add_argument("--file")
    parser.add_argument("--source-id")
    parser.add_argument("--artist", choices=ARTISTS + tuple(ARTIST_ALIASES))
    parser.add_argument("--title")
    parser.add_argument("--source-url")
    parser.add_argument("--rights-ref")
    parser.add_argument("--valid-until")
    parser.add_argument("--rights-confirmed",action="store_true")
    args=parser.parse_args()
    if args.command=="status":
        print(json.dumps(status(args.db),ensure_ascii=False)); return
    if args.command=="revoke":
        print(json.dumps(revoke(args.db,args.source_id),ensure_ascii=False)); return
    if not args.rights_confirmed:
        parser.error("--rights-confirmed is mandatory: operator must verify training/analysis rights")
    if not all([args.file,args.artist,args.title,args.source_url,args.rights_ref,args.valid_until]):
        parser.error("All ingestion and provenance fields are required")
    print(json.dumps(import_licensed(args.file,db_path=args.db,artist=args.artist,
        title=args.title,source_url=args.source_url,rights_ref=args.rights_ref,
        valid_until=args.valid_until),ensure_ascii=False))

if __name__=="__main__":
    cli()
