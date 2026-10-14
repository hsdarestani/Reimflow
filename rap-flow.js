/* Reimflow Rap Flow Analyse Beta.
 * Microphone → MediaRecorder (local) → optional explicit upload → Whisper word timing.
 * No localStorage, no automatic uploading, no recording saved to server.
 */
(()=>{
"use strict";
const page=document.querySelector('[data-page="flow"]');
if(!page)return;
const el=id=>document.getElementById(id);
const nodes={
  tapTab:el("flowShowTap"),rapTab:el("flowShowRap"),tapPanel:el("tapGamePanel"),rapPanel:el("rapPanel"),
  consent:el("rapConsent"),bpm:el("rapBpm"),bars:el("rapBars"),start:el("rapStart"),stop:el("rapStop"),discard:el("rapDiscard"),analyze:el("rapAnalyze"),
  studio:el("rapStudio"),counter:el("rapCounter"),status:el("rapStatus"),subStatus:el("rapSubStatus"),
  clock:el("rapClock"),progress:el("rapProgress"),wave:el("rapWave"),preview:el("rapPreview"),
  player:el("rapAudioPreview"),results:el("rapResults"),grid:el("rapGrid"),pause:el("rapPause"),
  syllables:el("rapSyllables"),density:el("rapDensity"),barsVisual:el("rapBarsVisual"),
  wordTimeline:el("rapWordTimeline"),feedback:el("rapFeedback"),transcript:el("rapTranscript"),
  limitNote:el("rapLimitNote"),share:el("rapShare"),resultTitle:el("rapResultTitle"),analysisState:el("rapAnalysisState")
};
const TOTAL_COUNTIN=4,MAX_BYTES=4*1024*1024;
let phase="idle",context=null,media=null,recorder=null,recorded=null,previewUrl=null,chunks=[],currentResult=null;
let timer=0,animation=0,nextBeat=0,nextBeatAudio=0,startPerf=0,rapZeroPerf=0,rapDuration=0;
let captureBeatOffset=0,bpm=92,bars=8,beatSeconds=0,noiseBuffer=null,output=null,abortUpload=null;
let runId=0;
const $status=(title,detail)=>{nodes.status.textContent=title;nodes.subStatus.textContent=detail};
function updateAnalysisState(type,message){
  const box=nodes.analysisState;
  if(!box)return;
  box.hidden=!message;
  box.className="rap-analysis-state"+(type?" "+type:"");
  box.textContent=message||"";
}
function setMode(name){
  if(phase==="recording"||phase==="preparing"||phase==="uploading")return;
  const isRap=name==="rap";
  if(isRap)window.ReimflowFlowChallenge?.stop();
  nodes.tapPanel.hidden=isRap;
  nodes.rapPanel.hidden=!isRap;
  nodes.tapTab.classList.toggle("active",!isRap);
  nodes.rapTab.classList.toggle("active",isRap);
  nodes.tapTab.setAttribute("aria-selected",String(!isRap));
  nodes.rapTab.setAttribute("aria-selected",String(isRap));
  if(isRap)nodes.rapPanel.scrollIntoView({block:"nearest",behavior:"smooth"});
}
function formatClock(seconds){
  const s=Math.max(0,Math.floor(seconds));
  return String(Math.floor(s/60)).padStart(2,"0")+":"+String(s%60).padStart(2,"0");
}
function selectedMime(){
  if(!window.MediaRecorder)return null;
  const prefs=["audio/webm;codecs=opus","audio/mp4","audio/webm","audio/ogg;codecs=opus"];
  return prefs.find(type=>MediaRecorder.isTypeSupported(type))||"";
}
function clearWave(){
  nodes.wave.querySelectorAll("span").forEach((child,i)=>{child.style.height=(16+i%3*5)+"px"});
}
function closeResources(){
  if(timer){clearInterval(timer);timer=0}
  if(animation){cancelAnimationFrame(animation);animation=0}
  if(media){media.getTracks().forEach(track=>track.stop());media=null}
  if(context){const old=context;context=null;old.close().catch(()=>{})}
  output=null;noiseBuffer=null;
  nodes.studio.classList.remove("recording","counting");
  nodes.start.disabled=false;nodes.stop.disabled=true;
  nodes.bpm.disabled=false;nodes.bars.disabled=false;
}
function discard(){
  if(phase==="recording"||phase==="preparing")return;
  if(abortUpload){abortUpload.abort();abortUpload=null}
  if(previewUrl){URL.revokeObjectURL(previewUrl);previewUrl=null}
  nodes.player.removeAttribute("src");nodes.player.load();
  recorded=null;currentResult=null;chunks=[];
  updateAnalysisState("",null);
  nodes.preview.hidden=true;nodes.results.hidden=true;nodes.discard.hidden=true;
  nodes.analyze.disabled=false;nodes.analyze.textContent="✦ Mit KI auswerten";
  nodes.progress.style.width="0%";nodes.counter.textContent="🎙";nodes.clock.textContent="00:00";
  phase="idle";clearWave();
  $status("Bereit für deine Aufnahme","Vier Schläge zum Einzählen, danach startet dein Part.");
}
function tone(t,frequency,length=.1,volume=.1,kind="sine",lastFrequency=null){
  if(!context||!output)return;
  const o=context.createOscillator(),g=context.createGain();
  o.type=kind;o.frequency.setValueAtTime(frequency,t);
  if(lastFrequency)o.frequency.exponentialRampToValueAtTime(lastFrequency,t+length);
  g.gain.setValueAtTime(.0001,t);
  g.gain.exponentialRampToValueAtTime(volume,t+.006);
  g.gain.exponentialRampToValueAtTime(.0001,t+length);
  o.connect(g);g.connect(output);o.start(t);o.stop(t+length+.01);
}
function noise(t,volume,length=.07){
  if(!context||!noiseBuffer)return;
  const src=context.createBufferSource(),env=context.createGain(),filter=context.createBiquadFilter();
  src.buffer=noiseBuffer;filter.type="highpass";filter.frequency.value=1800;
  env.gain.setValueAtTime(.0001,t);
  env.gain.linearRampToValueAtTime(volume,t+.003);
  env.gain.exponentialRampToValueAtTime(.0001,t+length);
  src.connect(filter);filter.connect(env);env.connect(output);
  src.start(t);src.stop(t+length+.01);
}
function buildNoise(){
  const buffer=context.createBuffer(1,Math.round(context.sampleRate*.12),context.sampleRate);
  const data=buffer.getChannelData(0);
  let seed=44179;
  for(let i=0;i<data.length;i++){seed=(Math.imul(seed,1664525)+1013904223)>>>0;data[i]=seed/2147483648-1}
  noiseBuffer=buffer;
}
function playBeat(index,t){
  if(index<TOTAL_COUNTIN){tone(t,index===0?1050:720,.06,.085);return}
  const n=index-TOTAL_COUNTIN;
  const k=n%4;
  if(k===0||k===2)tone(t,140,.16,.16,"sine",43);
  if(k===1||k===3)noise(t,.12,.1);
  noise(t,.04,.03);
  noise(t+beatSeconds/2,.023,.025);
}
function scheduleAudio(){
  if(phase!=="recording"||!context)return;
  const count=TOTAL_COUNTIN+bars*4;
  while(nextBeat<count&&nextBeatAudio<context.currentTime+.16){
    playBeat(nextBeat,nextBeatAudio);
    nextBeat++;nextBeatAudio+=beatSeconds;
  }
}
function tick(){
  if(phase!=="recording")return;
  const now=performance.now();
  const scored=Math.max(0,(now-rapZeroPerf)/1000);
  nodes.clock.textContent=formatClock((now-startPerf)/1000);
  if(now<rapZeroPerf){
    const remaining=Math.max(1,Math.ceil((rapZeroPerf-now)/(beatSeconds*1000)));
    nodes.counter.textContent=String(remaining);
    $status("Einzählen","Gleich geht es los. Folge dem Takt.");
    nodes.studio.classList.add("counting");nodes.studio.classList.remove("recording");
  }else{
    const beat=Math.min(bars*4,Math.floor(scored/beatSeconds)+1);
    nodes.counter.textContent=String(beat).padStart(2,"0");
    $status("Jetzt rappen!","Takt "+(Math.floor((beat-1)/4)+1)+" von "+bars);
    nodes.studio.classList.remove("counting");nodes.studio.classList.add("recording");
    nodes.progress.style.width=(Math.min(100,scored/rapDuration*100))+"%";
    const wave=nodes.wave.querySelectorAll("span");
    wave.forEach((x,i)=>x.style.height=(12+Math.abs(Math.sin(now*.008+i*1.9))*34)+"px");
  }
  if(scored>=rapDuration+.12){void stopRecording(false);return}
  animation=requestAnimationFrame(tick);
}
function recorderStop(){
  return new Promise(resolve=>{
    if(!recorder||recorder.state==="inactive"){resolve();return}
    recorder.addEventListener("stop",resolve,{once:true});
    recorder.stop();
  });
}
async function stopRecording(manual=true){
  if(phase!=="recording")return;
  phase="stopping";
  if(timer){clearInterval(timer);timer=0}
  if(animation){cancelAnimationFrame(animation);animation=0}
  await recorderStop();
  const usedType=recorder?.mimeType||selectedMime()||"audio/webm";
  const blob=new Blob(chunks,{type:usedType});
  closeResources();
  clearWave();
  if(manual||blob.size<800){
    phase="idle";chunks=[];
    $status("Aufnahme beendet",manual?"Du kannst eine neue Runde starten.":"Es wurde zu wenig Ton aufgenommen.");
    nodes.counter.textContent="■";
    return;
  }
  if(blob.size>MAX_BYTES){
    phase="idle";chunks=[];
    $status("Datei zu groß","Bitte eine kürzere Aufnahme versuchen.");
    return;
  }
  recorded=blob;previewUrl=URL.createObjectURL(blob);
  updateAnalysisState("ready","Aufnahme gespeichert. Wenn du „Mit KI auswerten“ drückst, wird die Aufnahme zur Sprachanalyse übertragen.");
  nodes.player.src=previewUrl;
  nodes.preview.hidden=false;nodes.discard.hidden=false;
  phase="preview";
  $status("Aufnahme fertig","Du kannst sie anhören oder mit KI auswerten.");
  nodes.counter.textContent="✓";
  nodes.progress.style.width="100%";
}
async function startRecording(){
  if(!nodes.consent.checked){$status("Einwilligung erforderlich","Bitte zuerst der Verarbeitung der Sprachaufnahme zustimmen.");nodes.consent.focus();return}
  if(phase==="recording"||phase==="preparing"||phase==="uploading")return;
  const mime=selectedMime();
  if(mime===null){$status("Aufnahme nicht unterstützt","Dieser Browser unterstützt keine Tonaufnahme. Bitte Chrome oder Safari aktualisieren.");return}
  discard();
  phase="preparing";
  bpm=Number(nodes.bpm.value);bars=Number(nodes.bars.value);
  if(![80,92,110,140].includes(bpm)||![4,8].includes(bars)){phase="idle";return}
  beatSeconds=60/bpm;rapDuration=bars*4*beatSeconds;
  nodes.start.disabled=true;nodes.stop.disabled=true;nodes.bpm.disabled=true;nodes.bars.disabled=true;
  $status("Mikrofon wird aktiviert","Bitte Mikrofonzugriff erlauben und Kopfhörer tragen.");
  const mine=++runId;
  try{
    if(!navigator.mediaDevices?.getUserMedia)throw Error("Mikrofon im Browser nicht verfügbar.");
    const Audio=window.AudioContext||window.webkitAudioContext;
    if(!Audio||!window.MediaRecorder)throw Error("Dieser Browser unterstützt keine Tonaufnahme.");
    context=new Audio();await context.resume();
    media=await navigator.mediaDevices.getUserMedia({audio:{
      echoCancellation:true,noiseSuppression:true,autoGainControl:true
    },video:false});
    if(mine!==runId){closeResources();return}
    recorder=new MediaRecorder(media,mime?{mimeType:mime}:undefined);
    chunks=[];recorder.addEventListener("dataavailable",event=>{if(event.data?.size)chunks.push(event.data)});
    recorder.addEventListener("error",()=>{if(phase==="recording")void stopRecording(true)});
    output=context.createGain();output.gain.value=.52;output.connect(context.destination);
    buildNoise();
    const fromAudio=context.currentTime;
    const t0=fromAudio+.35;
    startPerf=performance.now();
    captureBeatOffset=(t0-fromAudio)+TOTAL_COUNTIN*beatSeconds;
    rapZeroPerf=startPerf+captureBeatOffset*1000;
    nextBeatAudio=t0;nextBeat=0;
    recorder.start(250);
    phase="recording";
    nodes.stop.disabled=false;
    nodes.studio.classList.add("counting");
    scheduleAudio();timer=setInterval(scheduleAudio,25);
    animation=requestAnimationFrame(tick);
  }catch(error){
    ++runId;closeResources();
    phase="idle";
    $status("Aufnahme konnte nicht starten",error?.name==="NotAllowedError"?"Mikrofonzugriff abgelehnt. Bitte in den Browser-Einstellungen erlauben.":error?.message||"Mikrofon nicht verfügbar.");
  }
}
function addText(parent,tag,text,className){
  const e=document.createElement(tag);e.textContent=String(text);
  if(className)e.className=className;
  parent.append(e);return e;
}
function display(data){
  nodes.results.hidden=false;
  currentResult=data;
  if(data.status==="no_speech"){
    nodes.resultTitle.textContent="Keine verständliche Stimme erkannt";
    nodes.grid.textContent="–";nodes.pause.textContent="–";nodes.syllables.textContent="–";nodes.density.textContent="–";
    nodes.barsVisual.replaceChildren();nodes.wordTimeline.replaceChildren();
  }else{
    const m=data.metrics;
    nodes.resultTitle.textContent="Dein Flow im Zeitraster";
    nodes.grid.textContent=m.word_onset_grid_percent+" %";
    nodes.pause.textContent=m.longest_pause_sec.toFixed(2)+" s";
    nodes.syllables.textContent=String(m.syllables_est);
    nodes.density.textContent=m.density_change_per_sec_est.toFixed(2);
    nodes.barsVisual.replaceChildren();
    const max=Math.max(1,...data.bars.map(b=>b.syllables_est));
    for(const b of data.bars){
      const cell=addText(nodes.barsVisual,"div","","rap-bar");
      addText(cell,"span",String(b.syllables_est),"rap-bar-value");
      const bar=addText(cell,"div","","rap-bar-column");
      bar.style.height=(8+Math.max(0,b.syllables_est)/max*90)+"px";
      addText(cell,"small","T"+b.bar);
    }
    nodes.wordTimeline.replaceChildren();
    const visible=(data.words||[]).slice(0,120);
    for(const w of visible){
      const item=addText(nodes.wordTimeline,"span",w.word,"rap-word-chip");
      item.title=w.start.toFixed(2)+" – "+w.end.toFixed(2)+" Sek.";
    }
  }
  nodes.feedback.replaceChildren();
  for(const line of data.feedback||[])addText(nodes.feedback,"li",line);
  nodes.transcript.textContent=data.transcript||"Keine verlässliche Transkription.";
  nodes.limitNote.textContent=data.limits||"Alle Angaben sind Schätzwerte.";
  nodes.results.scrollIntoView({block:"start",behavior:"smooth"});
}
async function analyze(){
  if(!recorded||phase!=="preview"||!nodes.consent.checked){$status("Einwilligung erforderlich","Bitte der Verarbeitung zustimmen.");return}
  if(recorded.size>MAX_BYTES){$status("Datei zu groß","Bitte neu aufnehmen.");return}
  phase="uploading";
  updateAnalysisState("loading","Die Aufnahme wird analysiert. Bitte warte auf das Ergebnis.");
  nodes.results.hidden=true;
  currentResult=null;
  nodes.analyze.disabled=true;nodes.start.disabled=true;nodes.analyze.textContent="✦ Analyse läuft…";
  $status("KI wertet deine Aufnahme aus","Wörter und ihre Zeitmarken werden erkannt. Das kann etwas dauern.");
  abortUpload=new AbortController();
  const form=new FormData();
  const type=recorded.type.split(";")[0]||"audio/webm";
  const ext=type==="audio/mp4"?"m4a":type==="audio/ogg"?"ogg":type==="audio/wav"?"wav":"webm";
  form.append("audio",recorded,"rap."+ext);
  form.append("bpm",String(bpm));
  form.append("bars",String(bars));
  form.append("beat_offset",captureBeatOffset.toFixed(4));
  const timeout=setTimeout(()=>abortUpload?.abort(),85000);
  let succeeded=false;
  try{
    const response=await fetch("/api/flow/analyze",{method:"POST",body:form,signal:abortUpload.signal,credentials:"same-origin"});
    let result={};
    try{result=await response.json()}catch{throw Error("Der Server hat keine gültige Antwort gesendet.")}
    if(!response.ok)throw Error(result.message||"Analyse nicht möglich. Bitte erneut versuchen.");
    if(!result||result.ok!==true||!["analyzed","no_speech"].includes(result.status))throw Error("Der Server hat kein gültiges Analyseergebnis geliefert.");
    display(result);
    succeeded=true;
    updateAnalysisState(result.status==="no_speech"?"warning":"success",result.status==="no_speech"?"Keine verständliche Stimme erkannt. Die Aufnahme kannst du erneut anhören oder eine neue aufnehmen.":"Analyse abgeschlossen. Die Ergebnisse stehen direkt unter deiner Aufnahme.");
    $status(result.status==="no_speech"?"Keine Stimme erkannt":"Auswertung abgeschlossen","Die Berechnung basiert auf erkannten Wörtern und Zeitmarken.");
  }catch(error){
    const reason=error?.name==="AbortError"?"Die Anfrage dauerte zu lange oder wurde unterbrochen.":error?.message||"Bitte später erneut versuchen.";
    $status("Analyse fehlgeschlagen",reason);
    updateAnalysisState("error","Analyse fehlgeschlagen: "+reason+" Die Aufnahme bleibt auf deinem Gerät und kann erneut gesendet werden.");
    nodes.analysisState?.scrollIntoView({block:"center",behavior:"smooth"});
  }finally{
    clearTimeout(timeout);
    abortUpload=null;
    phase="preview";nodes.analyze.disabled=false;nodes.start.disabled=false;
    nodes.analyze.textContent=succeeded?"✦ Erneut auswerten":"✦ Analyse erneut versuchen";
  }
}
async function share(){
  if(!currentResult?.metrics)return;
  const m=currentResult.metrics;
  const text="🎙 Reimflow Rap Analyse (Beta): "+m.bpm+" BPM, "+m.bars+" Takte · "+
    m.word_onset_grid_percent+" % Wort-Einsätze am Beat-Raster · "+
    m.syllables_est+" geschätzte Silben. Schätzwerte, keine Talentnote. https://reimflow.smarbiz.sbs/";
  try{
    if(navigator.share)await navigator.share({title:"Reimflow Rap Analyse",text});
    else if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(text);$status("Ergebnis kopiert","Du kannst den Text jetzt teilen.")}
    else $status("Ergebnis",text);
  }catch(e){if(e?.name!=="AbortError")$status("Teilen nicht möglich","Bitte das Ergebnis manuell kopieren.")}
}
nodes.tapTab.addEventListener("click",()=>setMode("tap"));
nodes.rapTab.addEventListener("click",()=>setMode("rap"));
nodes.start.addEventListener("click",()=>void startRecording());
nodes.stop.addEventListener("click",()=>void stopRecording(true));
nodes.discard.addEventListener("click",discard);
nodes.analyze.addEventListener("click",()=>void analyze());
nodes.share.addEventListener("click",()=>void share());
document.addEventListener("visibilitychange",()=>{
  if(document.hidden && phase==="recording")void stopRecording(true);
});
window.addEventListener("pagehide",()=>{
  ++runId;if(abortUpload)abortUpload.abort();
  if(phase==="recording")void stopRecording(true);
  if(previewUrl)URL.revokeObjectURL(previewUrl);
  closeResources();
});
window.ReimflowRapFlow={
  onPageChange:(destination)=>{
    if(destination!=="flow"){
      ++runId;
      if(abortUpload)abortUpload.abort();
      if(phase==="recording")void stopRecording(true);
    }
  }
};
})();
