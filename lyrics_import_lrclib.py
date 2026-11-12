#!/usr/bin/env python3
"""Rights-attested LRCLIB catalog importer. No bulk scraping or persistent lyrics.

LRCLIB has a public search API (max ~20 hits/query). This importer is an
operator-triggered single pass, not a recurring crawl. Artist permission,
third-party source terms, and writer/publisher rights must be checked by the
operator. Runtime logs contain counts only; stored data is statistical.
"""
import argparse
import datetime
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import style_intelligence as si

ENDPOINT = "https://lrclib.net/api/search"
UA = "ReimflowLicensedAnalysis/1.0 (https://reimflow.smarbiz.sbs)"
SEARCHES = {
    "Eko": ("Eko Fresh",),
    "Kollegah": ("Kollegah",),
    "Ali As": ("Ali As",),
    "Sadiq": ("SadiQ",),
    "Shindy": ("Shindy",),
    "Bushido": ("Bushido",),
    "Mo Trip": ("MoTrip", "Mo Trip"),
    "SSIO": ("SSIO",),
    "Miami Yacine": ("Miami Yacine",),
}
MAX_RESPONSE = 4 * 1024 * 1024
SYNC_TIME = re.compile(r"^\s*(?:\[(?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d+)?\]\s*)+")
BRACKET_LABEL = re.compile(r"^\s*\[[^\]]{1,50}\]\s*$")

def normalize(value):
    value = unicodedata.normalize("NFKD", str(value)).casefold()
    return re.sub(r"[^a-z0-9]+", "", value)

def belongs_to_artist(credited_name, canonical):
    """Limit imports to a clearly credited primary rapper, not guest mentions."""
    credited = str(credited_name or "").strip()
    if not credited:
        return False
    # User-attested licenses cover the selected rappers, not necessarily guests.
    # Exclude collaborations until the other lyric writers are cleared as well.
    return normalize(credited) in {normalize(s) for s in SEARCHES[canonical]}

def lyrics_from_result(row):
    text = row.get("plainLyrics")
    if not isinstance(text, str) or not text.strip():
        synced = row.get("syncedLyrics")
        if not isinstance(synced, str):
            return None
        text = "\n".join(SYNC_TIME.sub("", line) for line in synced.splitlines())
    # Strip clear verse/chorus labels and timestamps; never infer missing lyrics.
    text = "\n".join(line for line in text.splitlines()
                     if not BRACKET_LABEL.fullmatch(line.strip()))
    if not text.strip():
        return None
    try:
        si.analyze(text)
    except ValueError:
        return None
    return text

def search(q, *, timeout=18, opener=None, sleep=time.sleep):
    opener = opener or urllib.request.urlopen
    url = ENDPOINT + "?" + urllib.parse.urlencode({"q": q})
    req = urllib.request.Request(url, headers={"User-Agent":UA,"Accept":"application/json"})
    for attempt in range(3):
        try:
            with opener(req, timeout=timeout) as response:
                raw = response.read(MAX_RESPONSE + 1)
            if len(raw)>MAX_RESPONSE:
                raise ValueError("Oversized upstream response")
            rows = json.loads(raw.decode("utf-8"))
            if not isinstance(rows, list):
                raise ValueError("Unexpected upstream JSON")
            return rows[:20]
        except urllib.error.HTTPError as error:
            if error.code != 429 or attempt == 2:
                raise
            retry = error.headers.get("Retry-After","2")
            try:
                pause = min(60,max(1,float(retry)))
            except ValueError:
                pause = 2
            sleep(pause)
    return []

def ingest_catalog(db_path, *, rights_ref, review_due, max_per_artist=20,
                   pause=0.8, dry_run=False, opener=None, sleep=time.sleep):
    if not rights_ref or not isinstance(rights_ref,str) or len(rights_ref)>180:
        raise ValueError("Rights reference is required")
    if datetime.date.fromisoformat(review_due) < datetime.date.today():
        raise ValueError("Rights review deadline already passed")
    if not 1<=max_per_artist<=20:
        raise ValueError("Limit should be 1..20 per artist")
    summary = []
    visited = set()
    for artist, queries in SEARCHES.items():
        imported = available = 0
        failures = []
        for query in queries:
            try:
                rows = search(query, opener=opener, sleep=sleep)
            except (urllib.error.URLError,TimeoutError,ValueError,json.JSONDecodeError) as error:
                failures.append(type(error).__name__)
                continue
            for row in rows:
                if not isinstance(row, dict) or row.get("instrumental"):
                    continue
                if not belongs_to_artist(row.get("artistName"), artist):
                    continue
                title = str(row.get("trackName") or "").strip()[:180]
                rid = row.get("id")
                if not title or not isinstance(rid,int) or rid<=0:
                    continue
                # Avoid remixes/duplicates from overlapping searches and credits.
                identity = (artist, normalize(title))
                if identity in visited:
                    continue
                text = lyrics_from_result(row)
                if text is None:
                    continue
                visited.add(identity)
                available += 1
                if not dry_run:
                    try:
                        si.import_licensed_bytes(text.encode("utf8"),db_path=db_path,
                            artist=artist,title=title,rights_ref=rights_ref,
                            source_url=f"https://lrclib.net/api/get/{rid}",
                            valid_until=review_due)
                        imported += 1
                    except (ValueError,UnicodeError,OverflowError):
                        failures.append("invalid_lyrics")
                if available>=max_per_artist:
                    break
            if available>=max_per_artist:
                break
            sleep(max(0.6,pause))
        summary.append({"artist":artist,"found":available,"imported":imported,
                        "errors":sorted(set(failures))})
    result={"source":"LRCLIB public API","artist_count":len(SEARCHES),
            "tracks_found":sum(s["found"] for s in summary),
            "tracks_imported":sum(s["imported"] for s in summary),
            "dry_run":dry_run,"rights_review_due":review_due,"artists":summary,
            "source_caveat":"Public API may lack tracks and caps search at 20 hits; not a complete catalog.",
            "raw_lyrics_stored":False}
    return result

def cli():
    p=argparse.ArgumentParser(description="One-time rights-attested lyrics analysis via LRCLIB API")
    p.add_argument("--db",default="/var/lib/reimflow/reimflow.sqlite3")
    p.add_argument("--rights-ref",required=True,help="Operator record of artist and songwriter rights")
    p.add_argument("--review-due",required=True,help="Internal recheck date YYYY-MM-DD, not legal license end date")
    p.add_argument("--rights-confirmed",action="store_true")
    p.add_argument("--source-terms-confirmed",action="store_true")
    p.add_argument("--max-per-artist",type=int,default=20)
    p.add_argument("--dry-run",action="store_true")
    args=p.parse_args()
    if not (args.rights_confirmed and args.source_terms_confirmed):
        p.error("Both --rights-confirmed and --source-terms-confirmed must be passed")
    result=ingest_catalog(args.db,rights_ref=args.rights_ref,review_due=args.review_due,
                          max_per_artist=args.max_per_artist,dry_run=args.dry_run)
    print(json.dumps(result,ensure_ascii=False))
    if result["tracks_found"]==0:
        sys.exit(2)

if __name__=="__main__":
    cli()
