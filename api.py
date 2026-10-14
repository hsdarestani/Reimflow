#!/usr/bin/env python3
import hashlib, json, os, sqlite3, threading, time, urllib.error, urllib.request, importlib.util, email.parser, email.policy
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST="127.0.0.1"; PORT=int(os.getenv("PORT","8787"))
OPENAI_API_KEY=os.getenv("OPENAI_API_KEY","").strip()
PRIMARY_MODEL=os.getenv("OPENAI_MODEL","gpt-4o-mini").strip()
# Fast first model for interactive rhyme search; only known API model IDs.
FALLBACK_MODELS=list(dict.fromkeys([PRIMARY_MODEL,"gpt-4.1-mini","gpt-5-mini"]))
DB_PATH=os.getenv("REIMFLOW_DB","/var/lib/reimflow/reimflow.sqlite3")
CACHE_TTL=60*60*24*30; MAX_QUERY_LEN=120; RATE_LIMIT=24; RATE_WINDOW=60
_lock=threading.Lock(); _rate=defaultdict(deque)

RHYME_SCHEMA={"type":"object","additionalProperties":False,"required":["analysis","rhymes"],"properties":{
"analysis":{"type":"object","additionalProperties":False,"required":["input","interpreted_as","pronunciation","ipa","syllables","language","correction","note"],"properties":{
"input":{"type":"string"},"interpreted_as":{"type":"string"},"pronunciation":{"type":"string"},"ipa":{"type":"string"},"syllables":{"type":"integer","minimum":1,"maximum":20},"language":{"type":"string"},"correction":{"type":["string","null"]},"note":{"type":"string"}}},
"rhymes":{"type":"array","minItems":4,"maxItems":10,"items":{"type":"object","additionalProperties":False,"required":["word","pronunciation","ipa","syllables","category","register","score","confidence","kind","explanation"],"properties":{
"word":{"type":"string"},"pronunciation":{"type":"string"},"ipa":{"type":"string"},"syllables":{"type":"integer","minimum":1,"maximum":20},
"category":{"type":"string","enum":["Nomen","Adjektiv","Verb","Umgangssprache","Sonstiges"]},
"register":{"type":"string","enum":["Standard","Umgangssprache","Slang","Name/Marke","Englisch/Code-Switch"]},
"score":{"type":"integer","minimum":0,"maximum":100},"confidence":{"type":"integer","minimum":0,"maximum":100},
"kind":{"type":"string","enum":["Perfekter Reim","Multi-Silben","Near Rhyme","Assonanz","Slant Rhyme","Phrase"]},"explanation":{"type":"string"}}}}}}

VALIDATE_SCHEMA={"type":"object","additionalProperties":False,"required":["source","target","verdict","score","confidence","source_pronunciation","target_pronunciation","explanation"],"properties":{
"source":{"type":"string"},"target":{"type":"string"},"verdict":{"type":"string","enum":["passt","grenzwertig","passt_nicht"]},"score":{"type":"integer","minimum":0,"maximum":100},"confidence":{"type":"integer","minimum":0,"maximum":100},"source_pronunciation":{"type":"string"},"target_pronunciation":{"type":"string"},"explanation":{"type":"string"}}}

DEVELOPER_PROMPT="""Du bist der phonetische Reimkern von Reimflow, einer App für deutschsprachige Rapper.
Finde Reime nach realem Klang, nicht nur nach gleichen Endbuchstaben.
Priorisiere Lautfolge, betonte Silben, Vokale, Konsonanten, Silbenzahl und Rhythmus.
Multi-Silben-Reime, Slant Rhymes, Assonanzen und Reime über Wortgrenzen hinweg sind erlaubt.
Deutsche Umgangssprache, etablierter Slang, Eigennamen, Marken und englische Code-Switches sind erlaubt, wenn sie im Rap plausibel sind.
Erfinde KEINE Fantasiewörter. Nutze reale Wörter, gebräuchliche Phrasen, bekannte Namen/Marken oder klar etablierte Umgangssprache.
Ein Score über 90 ist selten und verlangt einen sehr starken Klang-Match.
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
Erklärungen kurz und konkret. Vermeide Duplikate und bloße Flexionsvarianten. Sei kreativ, aber phonetisch ehrlich."""

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

def call_openai(user_text,schema,schema_name,developer_prompt):
    if not OPENAI_API_KEY: raise RuntimeError("AI_NOT_CONFIGURED")
    last=None
    started=time.monotonic()
    # Cap total synchronous work well below browser and reverse proxy timeouts.
    for model in FALLBACK_MODELS[:3]:
        remaining=44-(time.monotonic()-started)
        if remaining<5: break
        body={"model":model,"store":False,"input":[
            {"role":"developer","content":[{"type":"input_text","text":developer_prompt}]},
            {"role":"user","content":[{"type":"input_text","text":user_text}]}],
            "max_output_tokens":3200,
            "text":{"format":{"type":"json_schema","name":schema_name,"strict":True,"schema":schema}}}
        # GPT-4.x models reject reasoning parameter; GPT-5 supports it.
        if model.startswith("gpt-5"):
            body["reasoning"]={"effort":"minimal"}
        req=urllib.request.Request("https://api.openai.com/v1/responses",
            data=json.dumps(body,ensure_ascii=False).encode("utf-8"),method="POST",
            headers={"Authorization":"Bearer "+OPENAI_API_KEY,"Content-Type":"application/json","User-Agent":"Reimflow/1.1"})
        try:
            with urllib.request.urlopen(req,timeout=min(22,remaining)) as resp:
                raw=json.loads(resp.read(1024*1024).decode("utf-8"))
            text=extract_output_text(raw)
            if not text: raise RuntimeError("EMPTY_AI_RESPONSE")
            parsed=json.loads(text)
            if not isinstance(parsed,dict): raise RuntimeError("INVALID_AI_RESPONSE")
            return parsed,model
        except urllib.error.HTTPError as e:
            # Never write the full upstream body (or the user's query) to logs.
            last=RuntimeError("OPENAI_HTTP_"+str(e.code))
            print("rhyme upstream model:",model,"http:",e.code,flush=True)
            # Invalid model/config: try next valid model; authorization/billing
            # errors will not be solved with additional costly calls.
            if e.code in (400,404,422,429,500,502,503,504): continue
            raise last
        except (TimeoutError,urllib.error.URLError) as e:
            last=RuntimeError("OPENAI_TIMEOUT" if isinstance(e,TimeoutError) else "OPENAI_NETWORK")
            print("rhyme upstream model:",model,"connectivity:",type(e).__name__,flush=True)
            continue
        except (ValueError,RuntimeError) as e:
            last=RuntimeError("OPENAI_BAD_RESPONSE")
            print("rhyme upstream model:",model,"response:",type(e).__name__,flush=True)
            continue
    raise last or RuntimeError("OPENAI_UNAVAILABLE")

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
        if not word or word.casefold() in seen: continue
        seen.add(word.casefold()); r["word"]=word[:90]
        r["pronunciation"]=str(r.get("pronunciation",""))[:120]; r["ipa"]=str(r.get("ipa",""))[:140]; r["explanation"]=str(r.get("explanation",""))[:220]
        r["score"]=max(0,min(100,int(r.get("score",0)))); r["confidence"]=max(0,min(100,int(r.get("confidence",0)))); r["syllables"]=max(1,min(20,int(r.get("syllables",1))))
        clean.append(r)
    clean.sort(key=lambda x:(x["score"],x["confidence"]),reverse=True)
    return {"analysis":analysis,"rhymes":clean[:10]}

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
        if self.path=="/api/health":
            self.send_json(200,{"ok":True,"ai":bool(OPENAI_API_KEY),"model":PRIMARY_MODEL if OPENAI_API_KEY else None,"service":"reimflow-rhyme-engine"}); return
        self.send_json(404,{"error":"NOT_FOUND"})
    def do_POST(self):
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
            key=hashlib.sha256(("rhymes|v8|"+query.casefold()+"|"+category+"|"+syllables).encode()).hexdigest()
            cached=cache_get(key)
            if cached: self.send_json(200,cached); return
            user_text=json.dumps({"query":query,"filters":{"category":category,"syllables":syllables},"instructions":"Erzeuge 8 bis 10 brauchbare Treffer für exakt diese Query. Erweitere oder verkürze Namen niemals. Bei mehrteiligen Namen oder Phrasen zuerst den Gesamtklang prüfen und zusätzlich den dominanten End-Reimanker verwenden, wenn natürliche Vollphrasen-Reime rar sind. Lieber ehrliche Near-, Slant-, Assonanz- oder Phrase-Reime liefern als null Treffer oder erfundene Wörter. Wenn ein Filter gesetzt ist, priorisiere ihn strikt. Bei Alle diversifiziere Wortarten. Bewerte nach realem Klang im Rap. Bei Eigennamen und unsicherer Aussprache konservativ bewerten und keine Betonung erfinden."},ensure_ascii=False)
            try:
                data,model=call_openai(user_text,RHYME_SCHEMA,"reimflow_rhymes",DEVELOPER_PROMPT); data=sanitize(data,query)
                if len(data.get("rhymes",[])) < 4:
                    retry_text=json.dumps({
                        "query":query,
                        "filters":{"category":category,"syllables":syllables},
                        "instructions":"RETRY: Die erste Suche hatte zu wenige Treffer. Behalte die Query exakt unverändert. Nutze für mehrteilige Namen/Phrasen den letzten betonten Klangblock als Reimanker und liefere natürliche Multi-Silben-, Near-, Slant-, Assonanz- oder Phrase-Reime. Keine Fantasiewörter. Mindestens 8 brauchbare Treffer, Qualität ehrlich bewerten."
                    },ensure_ascii=False)
                    retry,model=call_openai(retry_text,RHYME_SCHEMA,"reimflow_rhymes_retry",DEVELOPER_PROMPT)
                    retry=sanitize(retry,query)
                    if len(retry.get("rhymes",[])) > len(data.get("rhymes",[])):
                        data=retry
                result={"ok":True,"engine":"ai_phonetic","model":model,"cached":False,**data}; cache_put(key,result); self.send_json(200,result)
            except Exception as e:
                reason=str(e)
                code="AI_TIMEOUT" if "TIMEOUT" in reason else "AI_CONFIG" if "AI_NOT_CONFIGURED" in reason else "AI_UPSTREAM"
                print("rhyme request failed:",code,flush=True)
                self.send_json(504 if code=="AI_TIMEOUT" else 503 if code=="AI_CONFIG" else 502,
                    {"error":code,"message":"Die KI-Reimsuche ist vorübergehend nicht erreichbar. Du kannst es erneut versuchen."})
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
    print(f"Reimflow API listening on {HOST}:{PORT}; AI={'on' if OPENAI_API_KEY else 'off'}; model={PRIMARY_MODEL}",flush=True)
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
