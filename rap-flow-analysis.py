"""Reimflow Rap Flow Analysis (beta).

Word alignment uses an actual speech transcription with per-word timestamps. All
metrics are descriptive timing estimates, NOT a verdict on rap artistry or vocal
quality. Audio bytes are handled in memory and never stored on disk or in DB.
"""
import json
import math
import re
import secrets
import urllib.error
import urllib.request

TRANSCRIPTION_URL="https://api.openai.com/v1/audio/transcriptions"
MAX_AUDIO_BYTES=4*1024*1024
MIMES={
    "audio/webm":"webm",
    "audio/ogg":"ogg",
    "audio/mp4":"m4a",
    "audio/x-m4a":"m4a",
    "audio/mpeg":"mp3",
    "audio/wav":"wav"
}
VOWELS=re.compile(r"[aeiouyäöü]+",re.IGNORECASE)


def clamp(value,low,high):
    return max(low,min(high,value))


def estimate_syllables(word):
    """Rough syllable count for informational density only, not phonetics."""
    clean=re.sub(r"[^a-zA-ZäöüÄÖÜß]","",str(word)).lower()
    return max(1,len(VOWELS.findall(clean))) if clean else 0


def transcribe_audio(audio,mime,api_key):
    if not api_key:
        raise RuntimeError("AI_NOT_CONFIGURED")
    ext=MIMES.get(mime)
    if not ext:
        raise ValueError("AUDIO_FORMAT")
    if len(audio)<800 or len(audio)>MAX_AUDIO_BYTES:
        raise ValueError("AUDIO_SIZE")
    boundary="rf"+secrets.token_hex(12)
    parts=[]
    def field(name,value):
        parts.append(("--"+boundary+"\r\nContent-Disposition: form-data; name=\""+name+"\"\r\n\r\n"+str(value)+"\r\n").encode())
    field("model","whisper-1")
    field("response_format","verbose_json")
    field("timestamp_granularities[]","word")
    parts.append(("--"+boundary+"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"rap."+ext+"\"\r\nContent-Type: "+mime+"\r\n\r\n").encode())
    parts.append(audio)
    parts.append(("\r\n--"+boundary+"--\r\n").encode())
    payload=b"".join(parts)
    req=urllib.request.Request(
        TRANSCRIPTION_URL,data=payload,method="POST",
        headers={
            "Authorization":"Bearer "+api_key,
            "Content-Type":"multipart/form-data; boundary="+boundary,
            "User-Agent":"Reimflow/rap-flow-beta"
        }
    )
    with urllib.request.urlopen(req,timeout=70) as r:
        data=json.loads(r.read(1024*1024).decode("utf-8"))
    if not isinstance(data,dict):
        raise RuntimeError("INVALID_TRANSCRIPTION")
    return data


def analyze_rap_words(raw,bpm,bars,beat_offset):
    """Compute conservative, reproducible stats from real word timestamps."""
    bpm=int(bpm)
    bars=int(bars)
    beat_offset=float(beat_offset)
    if bpm not in (80,92,110,140) or bars not in (4,8):
        raise ValueError("INVALID_TEMPO")
    interval=60.0/bpm
    total_beats=bars*4
    duration=interval*total_beats
    if not (0<=beat_offset<=8.0):
        raise ValueError("INVALID_OFFSET")
    source=raw.get("words") or []
    words=[]
    for item in source[:300]:
        try:
            t=str(item.get("word","")).strip()
            start=float(item.get("start"))
            end=float(item.get("end"))
        except (ValueError,TypeError,AttributeError): continue
        if not t or not (math.isfinite(start) and math.isfinite(end)):
            continue
        if end<start or end>beat_offset+duration+1:
            continue
        # Ignore words spoken in count-in; keep only the scored window.
        if start<beat_offset-0.03:
            continue
        start=clamp(start-beat_offset,0,duration)
        end=clamp(end-beat_offset,start,duration)
        if start>=duration:
            continue
        words.append({"word":t[:72],"start":round(start,3),"end":round(end,3)})
    words.sort(key=lambda w:w["start"])
    syllables=sum(estimate_syllables(w["word"]) for w in words)
    empty_result={
        "ok":True,"status":"no_speech","words":[],"transcript":"","metrics":None,
        "bars":[],"feedback":["Es wurde kein klarer Rapgesang erkannt. Bitte näher am Mikrofon und mit Kopfhörern erneut versuchen."],
        "limits":"Schätzung aus Wort-Zeitmarken, keine Messung von Rapqualität oder Artikulation."
    }
    if len(words)<3:
        return empty_result
    # Speech density per real 4/4 bar, based on estimated syllables, not raw audio notes.
    timeline=[]
    for i in range(bars):
        lo=i*4*interval
        hi=(i+1)*4*interval
        own=[w for w in words if lo<=w["start"]<hi]
        nsyll=sum(estimate_syllables(w["word"]) for w in own)
        timeline.append({"bar":i+1,"words":len(own),"syllables_est":nsyll,
                         "syllables_per_second_est":round(nsyll/(4*interval),2)})
    starts=[w["start"] for w in words]
    # Descriptive onsets: nearby quarter / eighth note grids, not "good rap" accuracy.
    quantized=[]
    tolerance=min(0.11,interval*.17)
    for t in starts:
        nearest=round((t/interval)*2)/2*interval
        quantized.append(abs(t-nearest))
    tight=sum(err<=tolerance for err in quantized)
    sync_ratio=round(100*tight/len(quantized))
    pauses=[]
    for a,b in zip(words,words[1:]):
        gap=b["start"]-a["end"]
        if gap>=0.28:
            pauses.append({"start":a["end"],"end":b["start"],"seconds":round(gap,2)})
    pauses=sorted(pauses,key=lambda p:p["seconds"],reverse=True)[:8]
    densities=[x["syllables_per_second_est"] for x in timeline if x["words"]]
    rate_change=round(max(densities)-min(densities),2) if len(densities)>1 else 0
    spread=round(sum(quantized)/len(quantized)*1000)
    # Intentionally no "ability score": word timestamps are not syllable-onset ground truth.
    feedback=[]
    feedback.append(
        f"{sync_ratio}% der erkannten Worteinsätze liegen in der Nähe des Viertel- oder Achtelrasters. "
        "Das beschreibt die Platzierung, nicht die musikalische Qualität."
    )
    if pauses:
        feedback.append(
            f"Die längste Pause zwischen erkannten Wörtern liegt bei {pauses[0]['seconds']:.2f} Sekunden."
        )
    else:
        feedback.append("Kaum längere Sprechpausen zwischen den erkannten Wörtern.")
    if rate_change>=0.9:
        feedback.append("Die geschätzte Silbendichte verändert sich zwischen den Takten deutlich.")
    else:
        feedback.append("Die geschätzte Silbendichte bleibt zwischen den Takten relativ gleichmäßig.")
    return {
        "ok":True,"status":"analyzed",
        "words":words,
        "transcript":" ".join(w["word"] for w in words)[:2000],
        "metrics":{
            "word_count":len(words),
            "syllables_est":syllables,
            "word_onset_grid_percent":sync_ratio,
            "grid_tolerance_ms":round(tolerance*1000),
            "mean_grid_distance_ms":spread,
            "longest_pause_sec":pauses[0]["seconds"] if pauses else 0,
            "density_change_per_sec_est":rate_change,
            "duration_sec":round(duration,2),
            "bpm":bpm,
            "bars":bars,
            "pause_count":len(pauses),
            "pauses":pauses
        },
        "bars":timeline,
        "feedback":feedback,
        "limits":"Wort-Zeitstempel und Silben sind nur Näherungen. Timing und Flow sind nicht gleichzusetzen; keine Bewertung von Reimkunst, Stimmqualität oder Talent."
    }
