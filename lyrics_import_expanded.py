#!/usr/bin/env python3
"""Operator-controlled expansion of Reimflow licensed-lyrics features.

Discovers solo recording TITLES from MusicBrainz (and iTunes fallback), then
uses LRCLIB's structured per-track search to retrieve lyrics in memory.
No lyrics are persisted, printed, committed or redistributed. A discovery hit
is NOT counted as an analyzed song until >=4 valid lines pass feature extraction.

Does not claim artist consent covers co-writers, collaborations, publishing
rights or separate provider terms. Run only after operator rights attestation.
"""
import argparse
import datetime
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import lyrics_import_lrclib as baseline
import style_intelligence as si

MB = "https://musicbrainz.org/ws/2"
ITUNES = "https://itunes.apple.com/search"
LYRICS = "https://lrclib.net/api/search"
UA = "ReimflowLicensedAnalysis/1.1 (https://reimflow.smarbiz.sbs)"
MAX_PAYLOAD = 4*1024*1024
FEATURE_PATTERN = re.compile(
    r"(?i)(?:\bfeat\.?\b|\bft\.?\b|\bfeaturing\b|\bvs\.?\b|\bx\b|\s[&+]\s)")
VERSION_PATTERN = re.compile(r"(?i)\b(?:instrumental|karaoke|remix|live at|live in|acoustic|sped up|slowed|cover)\b")


class SourceUnavailable(Exception):
    pass


def json_get(url, *, opener=None, sleeper=time.sleep, timeout=24, attempts=3):
    opener = opener or urllib.request.urlopen
    request = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept":"application/json"})
    for attempt in range(attempts):
        try:
            with opener(request,timeout=timeout) as response:
                payload = response.read(MAX_PAYLOAD+1)
            if len(payload) > MAX_PAYLOAD:
                raise SourceUnavailable("response_too_large")
            return json.loads(payload.decode("utf8"))
        except urllib.error.HTTPError as error:
            if error.code not in (429,500,502,503,504) or attempt==attempts-1:
                raise SourceUnavailable(f"http_{error.code}") from error
            wait=error.headers.get("Retry-After","")
            try: seconds=min(60,max(1,float(wait)))
            except (ValueError,TypeError): seconds=min(12,2**attempt)
            sleeper(seconds)
        except (urllib.error.URLError,TimeoutError,UnicodeError,ValueError) as error:
            if attempt == attempts-1:
                raise SourceUnavailable(type(error).__name__) from error
            sleeper(min(12,2**attempt))
    raise SourceUnavailable("no_response")


def likely_solo_title(title):
    return (isinstance(title,str) and 2<=len(title.strip())<=150 and
            not FEATURE_PATTERN.search(title) and not VERSION_PATTERN.search(title))


def looks_like_solo_credit(credit, artist):
    return baseline.belongs_to_artist(credit,artist)


def musicbrainz_titles(artist, *, max_titles=140, fetch=json_get, sleeper=time.sleep):
    """Browse paginated recordings, not a capped top-20 keyword search."""
    candidates = []
    terms = baseline.SEARCHES[artist]
    # Alias lookup: compare artist-name exactly, rather than picking the most
    # popular unrelated MusicBrainz entity from a vague search.
    mbid = None
    for alias in terms:
        q = 'artist:"'+alias.replace('"','')+'"'
        url = MB+"/artist?"+urllib.parse.urlencode({"query":q,"fmt":"json","limit":10})
        try:
            payload=fetch(url)
        except SourceUnavailable:
            continue
        for hit in payload.get("artists",[]):
            if (baseline.normalize(hit.get("name","")) == baseline.normalize(alias)
                and hit.get("type") in ("Person","Group",None)):
                mbid=hit.get("id")
                break
        if mbid:break
    if not mbid:
        return []
    seen=set()
    # MusicBrainz browse responses are max 100 records/page. Enumerate up to
    # 5 pages to avoid runaway catalog traversal.
    for offset in range(0,500,100):
        url=MB+"/recording?"+urllib.parse.urlencode({
            "artist":mbid,"fmt":"json","limit":100,"offset":offset})
        try:
            results=fetch(url)
        except SourceUnavailable:
            break
        rows=results.get("recordings",[])
        if not isinstance(rows,list):break
        for row in rows:
            title=row.get("title","")
            # MusicBrainz can return collaborations: only accept solo credits.
            credits=row.get("artist-credit",[])
            if credits:
                performers=[p.get("artist",{}).get("name","") for p in credits if isinstance(p,dict)]
                if len(performers)!=1 or not looks_like_solo_credit(performers[0],artist):
                    continue
            if likely_solo_title(title):
                key=baseline.normalize(title)
                if key not in seen:
                    seen.add(key);candidates.append(title.strip())
        if len(candidates)>=max_titles or len(rows)<100:
            break
        sleeper(1.1)  # MusicBrainz ~1 request/second client rate.
    return candidates[:max_titles]


def itunes_titles(artist, *, max_titles=140, fetch=json_get):
    """Independent discovery fallback (metadata only), no iTunes lyrics."""
    names=baseline.SEARCHES[artist]
    titles=[];seen=set()
    for alias in names[:2]:
        url=ITUNES+"?"+urllib.parse.urlencode({
            "term":alias,"country":"de","entity":"song","limit":200})
        try:
            data=fetch(url)
        except SourceUnavailable:
            continue
        for row in data.get("results",[]):
            if row.get("wrapperType")!="track" or row.get("kind")!="song":
                continue
            if not looks_like_solo_credit(row.get("artistName",""),artist):
                continue
            title=row.get("trackName","")
            if not likely_solo_title(title):
                continue
            key=baseline.normalize(title)
            if key not in seen:
                seen.add(key);titles.append(title.strip())
    return titles[:max_titles]


def candidate_titles(artist, *, max_titles=140, mb_fetch=json_get,
                     itunes_fetch=json_get, sleeper=time.sleep):
    mb=musicbrainz_titles(artist,max_titles=max_titles,fetch=mb_fetch,sleeper=sleeper)
    it=itunes_titles(artist,max_titles=max_titles,fetch=itunes_fetch)
    seen=set();out=[]
    # Interleave two independently curated metadata sources: improve coverage
    # without letting whichever lists first monopolize the search budget.
    for i in range(max(len(mb),len(it))):
        for track in (mb[i:i+1]+it[i:i+1]):
            key=baseline.normalize(track)
            if key not in seen:
                seen.add(key);out.append(track)
            if len(out)>=max_titles:return out
    return out


def fetch_track(artist,title, *, fetch=json_get):
    """Structured lookup: verify exact credited artist AND normalized title."""
    best=None;length=-1
    for name in baseline.SEARCHES[artist]:
        url=LYRICS+"?"+urllib.parse.urlencode({
            "track_name":title,"artist_name":name})
        try: rows=fetch(url)
        except SourceUnavailable: continue
        if not isinstance(rows,list):continue
        for row in rows[:20]:
            if not isinstance(row,dict) or row.get("instrumental"):continue
            if not looks_like_solo_credit(row.get("artistName",""),artist):continue
            if baseline.normalize(row.get("trackName",""))!=baseline.normalize(title):continue
            if not isinstance(row.get("id"),int) or row["id"]<=0:continue
            lyrics=baseline.lyrics_from_result(row)
            if lyrics is None:continue
            # Choose the best available transcription by valid line count.
            try: _,lines=si.analyze(lyrics)
            except ValueError:continue
            if lines>length:
                best=(row["id"],row["trackName"],lyrics)
                length=lines
        if best:return best
    return None


def _already_imported(db_path):
    try:
        with si.connect(db_path) as conn:
            return {(artist,baseline.normalize(title))
                    for artist,title in conn.execute("SELECT artist,title FROM rf_lyric_sources")}
    except sqlite3.Error:
        return set()


def expand(db_path, *, rights_ref, review_due,
           max_candidates_per_artist=140, target_total=330,
           request_pause=0.65, time_budget_seconds=1200,
           discovery=candidate_titles, get_track=fetch_track,
           sleeper=time.sleep, clock=time.monotonic, dry_run=False):
    """Bounded import, no silent substitute of metadata for text analysis."""
    if not rights_ref or len(rights_ref)>180:
        raise ValueError("Operator rights reference required")
    if datetime.date.fromisoformat(review_due)<datetime.date.today():
        raise ValueError("Rights review date must be in future")
    if not 1<=max_candidates_per_artist<=500 or target_total<1:
        raise ValueError("Invalid catalog limits")
    if time_budget_seconds<5:
        raise ValueError("Invalid time budget")
    existing=_already_imported(db_path)
    initial_count=si.status(db_path)["licensed_tracks"]
    found=0;imported=0;skipped=0;not_found=0;errors=[]
    summary=[]
    started=clock()
    for artist in baseline.SEARCHES:
        artist_stats={"artist":artist,"catalog_candidates":0,"new_analyses":0,
                      "already_present":0,"unavailable_lyrics":0,"errors":0}
        try:
            titles=discovery(artist,max_titles=max_candidates_per_artist)
        except (SourceUnavailable,urllib.error.URLError,ValueError) as error:
            errors.append(artist+":"+type(error).__name__)
            titles=[]
        artist_stats["catalog_candidates"]=len(titles)
        for title in titles:
            if clock()-started>=time_budget_seconds or initial_count+imported>=target_total:
                break
            key=(artist,baseline.normalize(title))
            if key in existing:
                artist_stats["already_present"]+=1
                skipped+=1
                continue
            try:
                track=get_track(artist,title)
            except (SourceUnavailable,ValueError,UnicodeError):
                artist_stats["errors"]+=1
                sleeper(request_pause)
                continue
            if track is None:
                artist_stats["unavailable_lyrics"]+=1
                not_found+=1
                sleeper(request_pause)
                continue
            rid,matched_title,lyrics=track
            found+=1
            if not dry_run:
                try:
                    si.import_licensed_bytes(
                        lyrics.encode("utf8"),db_path=db_path,artist=artist,
                        title=matched_title,
                        source_url=f"https://lrclib.net/api/get/{rid}",
                        rights_ref=rights_ref,valid_until=review_due)
                except (ValueError,UnicodeError,OverflowError):
                    artist_stats["errors"]+=1
                    continue
                existing.add(key)
                artist_stats["new_analyses"]+=1
                imported+=1
            sleeper(request_pause)
        summary.append(artist_stats)
        # Progress must remain metadata-only, no lyric text or raw responses.
        print("CATALOG_PROGRESS "+json.dumps(artist_stats,ensure_ascii=False),flush=True)
        if clock()-started>=time_budget_seconds or initial_count+imported>=target_total:
            break
    after=si.status(db_path)
    return {"previous_tracks":initial_count,"new_tracks":imported,
            "current_tracks":after["licensed_tracks"],
            "current_artists":after["artists_covered"],
            "lines_analyzed":after["lines_analyzed"],
            "target_total":target_total,
            "target_reached":after["licensed_tracks"]>=target_total,
            "matched_unimported_dry_run":found if dry_run else 0,
            "already_present_skipped":skipped,"missing_lyrics":not_found,
            "elapsed_seconds":round(clock()-started,1),
            "artists":summary,"discovery_errors":errors[:15],
            "raw_lyrics_stored":False,
            "scope":"first-pass catalog expansion; not all songs in existence",
            "rights_note":"Operator attested artist consent; collaborator/co-writer/provider permissions require separate review."}


def main():
    p=argparse.ArgumentParser(description="Expand authorized Reimflow rhyme corpus using track-level searches")
    p.add_argument("--db",default="/var/lib/reimflow/reimflow.sqlite3")
    p.add_argument("--rights-ref",required=True)
    p.add_argument("--review-due",required=True)
    p.add_argument("--rights-confirmed",action="store_true")
    p.add_argument("--source-terms-confirmed",action="store_true")
    p.add_argument("--max-candidates-per-artist",type=int,default=140)
    p.add_argument("--target-total",type=int,default=330)
    p.add_argument("--time-budget-seconds",type=int,default=1200)
    p.add_argument("--dry-run",action="store_true")
    args=p.parse_args()
    if not (args.rights_confirmed and args.source_terms_confirmed):
        p.error("Explicit review of rights and source terms is required")
    out=expand(args.db,rights_ref=args.rights_ref,review_due=args.review_due,
               max_candidates_per_artist=args.max_candidates_per_artist,
               target_total=args.target_total,time_budget_seconds=args.time_budget_seconds,
               dry_run=args.dry_run)
    print("CATALOG_EXPANSION_RESULT "+json.dumps(out,ensure_ascii=False),flush=True)
    if out["new_tracks"]==0 and not args.dry_run:
        sys.exit(2)

if __name__=="__main__":
    main()
