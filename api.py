#!/usr/bin/env python3
import hashlib, json, os, sqlite3, threading, time, urllib.error, urllib.request, importlib.util, email.parser, email.policy
from collections import defaultdict, deque
import platform_api
import rhyme_jobs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST="127.0.0.1"; PORT=int(os.getenv("PORT","8787"))
OPENAI_API_KEY=os.getenv("OPENAI_API_KEY","").strip()
PRIMARY_MODEL=os.getenv("OPENAI_MODEL","gpt-5.6-sol").strip()
# High-quality only. Never silently drop to a cheap mini model for rhyme generation.
FALLBACK_MODELS=list(dict.fromkeys([PRIMARY_MODEL,"gpt-5.5","gpt-5.4"]))
QUALITY_MODEL=os.getenv("RHYME_REVIEW_MODEL","gpt-5.6-terra").strip()
DB_PATH=os.getenv("REIMFLOW_DB","/var/lib/reimflow/reimflow.sqlite3")
_rhyme_jobs=rhyme_jobs.Manager(max_jobs=12,max_workers=3,ttl=900)
CACHE_TTL=60*60*24*7; MAX_QUERY_LEN=120; RATE_LIMIT=24; RATE_WINDOW=60
_lock=threading.Lock(); _rate=defaultdict(deque)

RHYME_SCHEMA={"type":"object","additionalProperties":False,"required":["analysis","rhymes"],"properties":{
"analysis":{"type":"object","additionalProperties":False,"required":["input","interpreted_as","pronunciation","ipa","syllables","language","correction","note"],"properties":{
"input":{"type":"string"},"interpreted_as":{"type":"string"},"pronunciation":{"type":"string"},"ipa":{"type":"string"},"syllables":{"type":"integer","minimum":1,"maximum":20},"language":{"type":"string"},"correction":{"type":["string","null"]},"note":{"type":"string"}}},
"rhymes":{"type":"array","minItems":0,"maxItems":14,"items":{"type":"object","additionalProperties":False,"required":["word","pronunciation","ipa","syllables","category","register","score","confidence","kind","explanation"],"properties":{
"word":{"type":"string"},"pronunciation":{"type":"string"},"ipa":{"type":"string"},"syllables":{"type":"integer","minimum":1,"maximum":20},
"category":{"type":"string","enum":["Nomen","Adjektiv","Verb","Umgangssprache","Sonstiges"]},
"register":{"type":"string","enum":["Standard","Umgangssprache","Slang","Name/Marke"]},
"score":{"type":"integer","minimum":0,"maximum":100},"confidence":{"type":"integer","minimum":0,"maximum":100},
"kind":{"type":"string","enum":["Perfekter Reim","Multi-Silben","Near Rhyme","Assonanz","Slant Rhyme","Phrase"]},"explanation":{"type":"string"}}}}}}

VALIDATE_SCHEMA={"type":"object","additionalProperties":False,"required":["source","target","verdict","score","confidence","source_pronunciation","target_pronunciation","explanation"],"properties":{
"source":{"type":"string"},"target":{"type":"string"},"verdict":{"type":"string","enum":["passt","grenzwertig","passt_nicht"]},"score":{"type":"integer","minimum":0,"maximum":100},"confidence":{"type":"integer","minimum":0,"maximum":100},"source_pronunciation":{"type":"string"},"target_pronunciation":{"type":"string"},"explanation":{"type":"string"}}}

DEVELOPER_PROMPT="""Du bist der phonetische Reimkern von Reimflow, einer App für deutschsprachige Rapper.
Finde Reime nach realem Klang, nicht nur nach gleichen Endbuchstaben.
Priorisiere Lautfolge, betonte Silben, Vokale, Konsonanten, Silbenzahl und Rhythmus.
Multi-Silben-Reime, Slant Rhymes, Assonanzen und Reime über Wortgrenzen hinweg sind erlaubt.
SPRACHE DER ERGEBNISSE: Ausschließlich Deutsch. Jeder einzelne Reimvorschlag muss ein tatsächlich gebrauchtes deutsches Wort, eine natürliche deutsche Wortgruppe oder etablierter deutschsprachiger Rap-Slang sein. Keine englischen Reimwörter, keine englischen Phrasen und kein Code-Switching in den Vorschlägen. Erfundene deutsche Wörter sind ebenfalls verboten. Auch Eigennamen oder Marken nicht als Ausweg für englische Kandidaten anbieten.
Die Eingabe darf in jeder Sprache sein (auch englische Namen oder Marken); analysiere sie mit ihrer tatsächlichen Originalaussprache, aber liefere ausschließlich deutsche Reimkandidaten. Wenn kein sinnvoller deutscher Reim existiert, liefere lieber null Treffer als englische Treffer.
Erklärungen, Register und Aussprachehilfen auf Deutsch; etablierte, im Deutschen tatsächlich gebräuchliche Lehnwörter sind nur zulässig, wenn sie im deutschen Sprachgebrauch natürlich verwendet werden.
Erfinde KEINE Fantasiewörter. Nutze reale Wörter, gebräuchliche Phrasen, bekannte Namen/Marken oder klar etablierte Umgangssprache.
Qualität vor Quantität, aber suche umfassend! Gib zuerst 5 bis 8 reale, korrekt ausgesprochene Wörter oder Namen, die zum letzten betonten REIMANKER passen, selbst wenn sie nicht zur ganzen Phrase reimen. Dann 3 bis 6 sinnvolle mehrteilige kreative Lyrik-Phrasen, die Rhythmus und Klang der ganzen Query treffen. Nicht die Anzahl erzwingen, aber nicht nach nur einem Versuch aufgeben.
WICHTIG: analysis.input und analysis.interpreted_as müssen exakt der vom Nutzer eingegebenen, getrimmten Query entsprechen.
Erweitere Eigennamen NIEMALS selbstständig. Aus "Benzema" darf nicht "Karim Benzema" werden. Aus "Ronaldo" darf nicht "Cristiano Ronaldo" werden.
Verkürze mehrteilige Namen oder Phrasen ebenfalls nicht. Analysiere exakt die Zeichenfolge, die der Nutzer eingegeben hat.
Wenn die Eingabe wahrscheinlich falsch geschrieben ist, setze correction nur bei sehr hoher Sicherheit als separaten Vorschlag; ändere interpreted_as trotzdem nicht.
Bei Eigennamen, fremdsprachigen Namen, Marken oder unklarer Aussprache: keine erfundene Betonung behaupten. Unsicherheit kurz in note nennen und bei den Reimtreffern konservativer bewerten.
Bei mehrteiligen Namen oder Phrasen analysierst du ZWEI Ebenen:
A) den Gesamtklang der kompletten Query für echte Phrase- oder Multi-Silben-Reime;
B) den dominanten Reimanker am Ende der Query, meistens das letzte betonte Wort oder die letzten 2 bis 4 betonten Silben.
Wenn für A kaum natürliche Treffer existieren, darfst du starke Treffer für B liefern. Kennzeichne sie ehrlich als Multi-Silben, Near Rhyme, Slant Rhyme, Assonanz oder Phrase und behaupte keinen perfekten Reim.
Ein mehrteiliger Name wie "Karim Benzema" darf also Treffer bekommen, die stark auf "Benzema" oder den Endklang der gesamten Phrase passen. Die Query selbst bleibt trotzdem exakt "Karim Benzema".
pronunciation ist eine leicht lesbare Aussprachehilfe für deutsche Nutzer; ipa ist möglichst korrekte IPA.
Behandle bei mehrteiligen Eingaben drei Reimtypen gleichzeitig:
1) isolierte Endwort-Reime gegen die Originalaussprache des letzten Wortes;
2) natürliche, mehrteilige DEUTSCHE Rap-Phrasen, die Klang und Rhythmus der ganzen Eingabe treffen;
3) kreative, aber sprachlich sinnvolle DEUTSCHE Lyrik-Phrasen.
Bei fremdsprachigen Eingaben darfst du das Eingabewort in seiner Originalsprache analysieren, aber NICHT englische Reimkandidaten oder englische Code-Switch-Phrasen ausgeben.
Endwort-Reime sind valide Treffer und kein schwacher Full-Phrase-Reim.
Nutze mehrere semantische Kategorien, wenn das möglich ist.
Vermeide die häufige Verwechslung von gleicher Silbenzahl/Rhythmus mit einem Reim. Bei "Blue Ferrari" sind Toyota, Karaoke, Marinade, Batterie keine starken Reime. Mögliche Ankerideen wie Safari/Calamari nur prüfen, nicht automatisch akzeptieren. Nicht behaupten, die gesamte Phrase reime sich, wenn nur das Schlusswort ähnlich klingt. Vermeide Duplikate und bloße Flexionsvarianten. Gib bis zu 14 Kandidaten nur wenn plausibel. Erklärungen kurz und konkret, mit konkret passendem betontem Reimkern. Sei phonetisch ehrlich."""

VALIDATE_PROMPT="""Du bist ein strenger Reim-Tester für eine deutschsprachige Rap-Community.
Prüfe zwei Wörter oder Phrasen nach realer Aussprache, betonten Silben, Vokalen, Konsonanten, Silbenzahl und Rap-Tauglichkeit.
Rechtschreibung allein ist kein Beweis. Multi-Silben- und Slant-Rhymes dürfen passen.
Sei streng und erfinde keine Aussprache, um einen Match zu erzwingen."""

def db():
    os.makedirs(os.path.dirname(DB_PATH),exist_ok=True)
    c=sqlite3.connect(DB_PATH,timeout=10)
    c.execute("CREATE TABLE IF NOT EXISTS cache (cache_key TEXT PRIMARY KEY,payload TEXT NOT NULL,created_at INTEGER NOT NULL)")
    c.commit(); return c

def cache_get(key):
    try:
        with db() as c: row=c.execute("SELECT payload,created_at FROM cache WHERE cache_key=?",(key,)).fetchone()
        if not row or int(time.time())-row[1]>CACHE_TTL: return None
        data=json.loads(row[0]); data["cached"]=True; return data
    except Exception: return None

def cache_put(key,payload):
    try:
        clean=dict(payload); clean.pop("cached",None)
        with db() as c:
            c.execute("INSERT OR REPLACE INTO cache(cache_key,payload,created_at) VALUES(?,?,?)",(key,json.dumps(clean,ensure_ascii=False),int(time.time())))
            c.commit()
    except Exception: pass

def client_allowed(ip):
    now=time.time()
    with _lock:
        q=_rate[ip]
        while q and now-q[0]>RATE_WINDOW: q.popleft()
        if len(q)>=RATE_LIMIT: return False
        q.append(now); return True


_intent_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),"rhyme-intent.py")
_intent_spec=importlib.util.spec_from_file_location("reimflow_rhyme_intent",_intent_path)
rhyme_intent=importlib.util.module_from_spec(_intent_spec)
_intent_spec.loader.exec_module(rhyme_intent)

# Strict second-pass review, loaded from deployed code without extra dependencies.
_quality_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),"rhyme-quality.py")
_quality_spec=importlib.util.spec_from_file_location("reimflow_rhyme_quality",_quality_path)
rhyme_quality=importlib.util.module_from_spec(_quality_spec)
_quality_spec.loader.exec_module(rhyme_quality)

# Voice analysis is isolated from the rhyme cache and never persisted.
_module_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),"rap-flow-analysis.py")
_spec=importlib.util.spec_from_file_location("reimflow_rap_flow",_module_path)
rap_flow=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rap_flow)
_flow_rate=defaultdict(deque)
FLOW_RATE_WINDOW=600
FLOW_RATE_LIMIT=4

def flow_allowed(ip):
    now=time.time()
    with _lock:
        q=_flow_rate[ip]
        while q and now-q[0]>FLOW_RATE_WINDOW: q.popleft()
        if len(q)>=FLOW_RATE_LIMIT: return False
        q.append(now)
        return True

def parse_voice_form(headers, stream):
    """Bounded multipart parsing. Audio remains ephemeral in memory only."""
    try:
        length=int(headers.get("Content-Length","0"))
    except (ValueError,TypeError):
        raise ValueError("INVALID_SIZE")
    if length<=0 or length>rap_flow.MAX_AUDIO_BYTES+8192:
        raise ValueError("INVALID_SIZE")
    ctype=headers.get("Content-Type","")
    if not ctype.startswith("multipart/form-data;") or "boundary=" not in ctype:
        raise ValueError("INVALID_MULTIPART")
    wire=stream.read(length)
    if len(wire)!=length:
        raise ValueError("INCOMPLETE_UPLOAD")
    message=email.parser.BytesParser(policy=email.policy.default).parsebytes(
        b"MIME-Version: 1.0\r\nContent-Type: "+ctype.encode("ascii","ignore")+b"\r\n\r\n"+wire
    )
    if not message.is_multipart():
        raise ValueError("INVALID_MULTIPART")
    fields={}
    audio=None; mime=None
    for part in message.iter_parts():
        name=part.get_param("name",header="content-disposition")
        if name=="audio":
            if audio is not None: raise ValueError("DUPLICATE_AUDIO")
            audio=part.get_payload(decode=True)
            mime=part.get_content_type()
        elif name in ("bpm","bars","beat_offset") and name not in fields:
            data=part.get_payload(decode=True)
            if len(data)>64: raise ValueError("INVALID_FIELD")
            fields[name]=data.decode("ascii","strict")
    if not audio or len(audio)>rap_flow.MAX_AUDIO_BYTES:
        raise ValueError("INVALID_AUDIO")
    if mime not in rap_flow.MIMES:
        raise ValueError("AUDIO_FORMAT")
    bpm=int(fields["bpm"])
    bars=int(fields["bars"])
    beat_offset=float(fields["beat_offset"])
    if bpm not in (80,92,110,140) or bars not in (4,8) or not 0<=beat_offset<=8:
        raise ValueError("INVALID_PARAMETERS")
    return audio,mime,bpm,bars,beat_offset

def extract_output_text(response):
    for item in response.get("output",[]):
        if item.get("type")!="message": continue
        for part in item.get("content",[]):
            if part.get("type")=="output_text" and part.get("text"): return part["text"]
    return ""

def call_openai(user_text,schema,schema_name,developer_prompt,models=None,effort="medium",timeout=60):
    """One quality model per request; fallback only for unavailable models/errors."""
    if not OPENAI_API_KEY: raise RuntimeError("AI_NOT_CONFIGURED")
    last=None
    for model in dict.fromkeys(models or FALLBACK_MODELS):
        # Never silently downgrade to low-cost mini models for phonetic decisions.
        body={"model":model,"store":False,
              "input":[
                 {"role":"developer","content":[{"type":"input_text","text":developer_prompt}]},
                 {"role":"user","content":[{"type":"input_text","text":user_text}]}],
              "max_output_tokens":4200,
              "text":{"format":{"type":"json_schema","name":schema_name,"strict":True,"schema":schema}}}
        if model.startswith(("gpt-5","gpt-6")):
            body["reasoning"]={"effort":effort}
        req=urllib.request.Request("https://api.openai.com/v1/responses",
            data=json.dumps(body,ensure_ascii=False).encode("utf-8"),method="POST",
            headers={"Authorization":"Bearer "+OPENAI_API_KEY,"Content-Type":"application/json","User-Agent":"Reimflow/quality-v1"})
        try:
            with urllib.request.urlopen(req,timeout=timeout if model==(list(dict.fromkeys(models or FALLBACK_MODELS))[0]) else min(timeout,45)) as resp:
                raw=json.loads(resp.read(2*1024*1024).decode("utf-8"))
            content=extract_output_text(raw)
            if not content: raise RuntimeError("EMPTY_AI_RESPONSE")
            data=json.loads(content)
            if not isinstance(data,dict): raise RuntimeError("INVALID_AI_RESPONSE")
            return data,model
        except urllib.error.HTTPError as e:
            last=RuntimeError("OPENAI_HTTP_"+str(e.code))
            print("rhyme upstream:",model,"http:",e.code,flush=True)
            # Only invalid/unavailable models should cause fallthrough. Do not
            # retry on rate limits, billing, or auth, and never downgrade quality.
            if e.code in (400,404,422):
                continue
            raise last
        except (TimeoutError,urllib.error.URLError) as e:
            last=RuntimeError("OPENAI_TIMEOUT")
            print("rhyme upstream:",model,"timeout or network",flush=True)
            # A single retry using another full-quality model is allowed on a
            # generation timeout. Never silently substitute cheap mini models.
            if (isinstance(e,TimeoutError) or "timed out" in str(e).lower() or "timeout" in str(e).lower()) and model != list(dict.fromkeys(models or FALLBACK_MODELS))[-1]:
                continue
            raise last
        except (ValueError,RuntimeError) as e:
            last=RuntimeError("OPENAI_BAD_RESPONSE")
            print("rhyme upstream:",model,"invalid response",flush=True)
            raise last
    raise last or RuntimeError("OPENAI_MODEL_UNAVAILABLE")

def sanitize(data, query):
    analysis=data.get("analysis") or {}
    analysis["input"]=query
    analysis["interpreted_as"]=query
    if analysis.get("correction"):
        correction=str(analysis["correction"]).strip()
        if not correction or correction.casefold()==query.casefold():
            analysis["correction"]=None
        else:
            analysis["correction"]=correction[:120]
    seen=set(); clean=[]
    for r in data.get("rhymes") or []:
        word=str(r.get("word","")).strip()
        if not word or word.casefold() in seen or r.get("register")=="Englisch/Code-Switch": continue
        seen.add(word.casefold()); r["word"]=word[:90]
        r["pronunciation"]=str(r.get("pronunciation",""))[:120]; r["ipa"]=str(r.get("ipa",""))[:140]; r["explanation"]=str(r.get("explanation",""))[:220]
        r["score"]=max(0,min(100,int(r.get("score",0)))); r["confidence"]=max(0,min(100,int(r.get("confidence",0)))); r["syllables"]=max(1,min(20,int(r.get("syllables",1))))
        clean.append(r)
    clean.sort(key=lambda x:(x["score"],x["confidence"]),reverse=True)
    return {"analysis":analysis,"rhymes":clean[:14]}

class Handler(BaseHTTPRequestHandler):
    server_version="ReimflowAPI/1.0"
    def log_message(self,fmt,*args): print("%s - %s"%(self.address_string(),fmt%args),flush=True)
    def send_json(self,status,payload):
        body=json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store"); self.send_header("X-Content-Type-Options","nosniff"); self.end_headers(); self.wfile.write(body)
    def read_json(self):
        length=int(self.headers.get("Content-Length","0"))
        if length<=0 or length>32768: raise ValueError()
        return json.loads(self.rfile.read(length).decode())
    def do_GET(self):
        if platform_api.handle(self): return
        if self.path=="/api/health":
            self.send_json(200,{"ok":True,"ai":bool(OPENAI_API_KEY),"model":PRIMARY_MODEL if OPENAI_API_KEY else None,"service":"reimflow-rhyme-engine"}); return
        if self.path.startswith("/api/rhymes/jobs/"):
            job_id=self.path[len("/api/rhymes/jobs/"):]
            if not job_id or len(job_id)>80 or not all(ch.isalnum() or ch in "-_" for ch in job_id):
                self.send_json(404,{"error":"NOT_FOUND"}); return
            response=_rhyme_jobs.get(job_id)
            if not response:
                self.send_json(404,{"error":"JOB_EXPIRED","message":"Diese Suche ist abgelaufen. Bitte erneut suchen."}); return
            self.send_json(*response); return
        self.send_json(404,{"error":"NOT_FOUND"})
    def do_POST(self):
        if platform_api.handle(self): return
        ip=self.headers.get("X-Real-IP") or self.client_address[0]
        if not client_allowed(ip): self.send_json(429,{"error":"RATE_LIMIT","message":"Zu viele Anfragen. Bitte kurz warten."}); return
        if self.path=="/api/flow/analyze":
            # Explicit voice-upload endpoint: no saving of audio, transcript or derived metrics.
            if not OPENAI_API_KEY:
                self.send_json(503,{"error":"AI_UNAVAILABLE","message":"Die Sprachanalyse ist derzeit nicht verfügbar."}); return
            if not flow_allowed(ip):
                self.send_json(429,{"error":"VOICE_LIMIT","message":"Bitte warte einige Minuten vor der nächsten Analyse."}); return
            try:
                audio,mime,bpm,bars,beat_offset=parse_voice_form(self.headers,self.rfile)
            except (KeyError,TypeError,ValueError,UnicodeError) as e:
                self.send_json(400,{"error":"INVALID_AUDIO","message":"Ungültige oder zu große Tonaufnahme. Bitte erneut versuchen."}); return
            try:
                transcript=rap_flow.transcribe_audio(audio,mime,OPENAI_API_KEY)
                del audio
                result=rap_flow.analyze_rap_words(transcript,bpm,bars,beat_offset)
                self.send_json(200,result)
            except urllib.error.HTTPError as e:
                # Never expose upstream error bodies or sensitive audio in logs.
                print("flow transcription upstream code:",e.code,flush=True)
                self.send_json(502,{"error":"TRANSCRIPTION_FAILED","message":"Die Spracherkennung ist gerade nicht erreichbar."})
            except (urllib.error.URLError,TimeoutError) as e:
                print("flow transcription timeout",flush=True)
                self.send_json(504,{"error":"TRANSCRIPTION_TIMEOUT","message":"Die Analyse dauert zu lange. Bitte erneut versuchen."})
            except Exception as e:
                print("flow transcription failed:",type(e).__name__,flush=True)
                self.send_json(502,{"error":"ANALYSIS_FAILED","message":"Die Sprachanalyse ist fehlgeschlagen. Bitte erneut versuchen."})
            return
        try: body=self.read_json()
        except Exception: self.send_json(400,{"error":"BAD_REQUEST","message":"Ungültige Anfrage."}); return
        if self.path=="/api/rhymes":
            query=str(body.get("query","")).strip(); category=str(body.get("category","Alle")).strip(); syllables=str(body.get("syllables","Alle")).strip()
            if not query or len(query)>MAX_QUERY_LEN: self.send_json(400,{"error":"INVALID_QUERY","message":"Bitte ein Wort oder eine kurze Phrase eingeben."}); return
            if category not in {"Alle","Nomen","Adjektiv","Verb","Umgangssprache","Sonstiges"}: category="Alle"
            if syllables not in {"Alle","1","2","3","4+"}: syllables="Alle"
            key=hashlib.sha256(("rhymes|de-only-v1|"+query.casefold()+"|"+category+"|"+syllables).encode()).hexdigest()
            cached=cache_get(key)
            if cached: self.send_json(200,cached); return
            if not OPENAI_API_KEY:
                self.send_json(503,{"error":"AI_CONFIG","message":"Die KI-Suche ist derzeit nicht eingerichtet."}); return
            intent=rhyme_intent.search_intent(query)
            user_text=json.dumps({
                "intent":intent,
                "query":query,
                "filters":{"category":category,"syllables":syllables},
                "instructions":"Erstelle zuerst mehrere solide Wortreime speziell für intent.end_word, unabhängig davon ob sie die Gesamtphrase treffen. Dann zusätzlich echte mehrteilige, sinnhafte Rap-Lines mit ähnlichem Klang und Rhythmus zur ganzen Phrase; keine ausgedachten Wörter oder ungebräuchliche Scheinphrasen. Jede Kategorie soll beim Review getrennt geprüft werden. Klang der Originalsprache und Betonung beachten, aber ausschließlich deutsche Wörter und sinnvolle deutsche Phrasen als Reime ausgeben; niemals englische Wörter oder englische Code-Switch-Ausdrücke vorschlagen."
            },ensure_ascii=False)

            def generate(job_id):
                try:
                    raw,model=call_openai(user_text,RHYME_SCHEMA,
                        "reimflow_quality_candidates",DEVELOPER_PROMPT,
                        effort="medium",timeout=65)
                    raw=sanitize(raw,query)
                    _rhyme_jobs.stage(job_id,"review")
                    reviewed,review_model=call_openai(
                        rhyme_quality.review_input(query,raw),
                        rhyme_quality.QUALITY_SCHEMA,"reimflow_independent_review",
                        rhyme_quality.QUALITY_PROMPT,models=[QUALITY_MODEL],
                        effort="medium",timeout=65)
                    data=rhyme_quality.review_and_filter(query,raw,reviewed)
                    # Never cache suggestions without independent phonetic review.
                    result={"ok":True,"engine":"ai_phonetic","model":model,
                        "intent":intent,"review_model":review_model,"cached":False,**data}
                    print("rhyme quality gate:",len(raw["rhymes"]),
                          "candidates,",len(data["rhymes"]),"accepted",flush=True)
                    cache_put(key,result)
                    return result
                except Exception as exc:
                    reason=str(exc)
                    code=("AI_TIMEOUT" if "TIMEOUT" in reason else
                          "AI_CONFIG" if "NOT_CONFIGURED" in reason else "AI_UPSTREAM")
                    print("rhyme request failed:",code,flush=True)
                    message=("Die KI benötigt gerade länger. Bitte versuche die Suche erneut."
                             if code=="AI_TIMEOUT" else
                             "Die KI-Reimsuche ist vorübergehend nicht erreichbar. Bitte erneut versuchen.")
                    raise rhyme_jobs.JobError(code,message,
                        504 if code=="AI_TIMEOUT" else 503 if code=="AI_CONFIG" else 502) from None

            try:
                job_id=_rhyme_jobs.submit(key,generate)
            except rhyme_jobs.BusyError:
                self.send_json(503,{"error":"AI_BUSY",
                    "message":"Die KI bearbeitet gerade viele Suchen. Bitte in Kürze erneut versuchen."})
                return
            self.send_json(202,{"ok":True,"pending":True,"stage":"queued",
                                "job_id":job_id,"poll_after_ms":1800})
            return
        if self.path=="/api/validate":
            source=str(body.get("source","")).strip(); target=str(body.get("target","")).strip()
            if not source or not target or len(source)>MAX_QUERY_LEN or len(target)>MAX_QUERY_LEN: self.send_json(400,{"error":"INVALID_PAIR"}); return
            key=hashlib.sha256(("validate|v2|"+source.casefold()+"|"+target.casefold()).encode()).hexdigest(); cached=cache_get(key)
            if cached: self.send_json(200,cached); return
            try:
                data,model=call_openai(json.dumps({"source":source,"target":target},ensure_ascii=False),VALIDATE_SCHEMA,"reimflow_validation",VALIDATE_PROMPT)
                result={"ok":True,"model":model,"cached":False,**data}; cache_put(key,result); self.send_json(200,result)
            except Exception as e:
                print("validate error:",str(e)[:600],flush=True); self.send_json(502,{"error":"AI_UNAVAILABLE","message":"AI Check gerade nicht verfügbar."})
            return
        self.send_json(404,{"error":"NOT_FOUND"})

if __name__=="__main__":
    db().close()
    platform_api.initialize()
    print(f"Reimflow API listening on {HOST}:{PORT}; AI={'on' if OPENAI_API_KEY else 'off'}; model={PRIMARY_MODEL}",flush=True)
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
