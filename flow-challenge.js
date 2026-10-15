/* Reimflow Arcade / Flow Challenge — no uploads, API calls or external dependencies.
   Timing game with 4-beat count-in, 16 scored beats, Web Audio drum synth,
   keyboard/touch input and optional local-only microphone onset detection. */
(()=>{
"use strict";
const T=window.ReimflowTiming;
const page=document.querySelector('[data-page="flow"]');
if(!T||!page)return;
const $=id=>document.getElementById(id);
const el={
  stage:$("flowStage"),bpm:$("flowBpm"),start:$("flowStart"),stop:$("flowStop"),
  tap:$("flowTap"),share:$("flowShare"),hint:$("flowHint"),padHint:$("flowPadHint"),
  score:$("flowScore"),rank:$("flowRank"),perfect:$("flowPerfect"),good:$("flowGood"),
  combo:$("flowCombo"),best:$("flowBest"),count:$("flowCount"),orbit:$("flowOrbit"),
  judgement:$("flowJudgement"),stageLabel:$("flowStageLabel"),barCount:$("flowBarCount")
};
const cells=[...document.querySelectorAll("#flowBeatStrip .flow-beat")];
const modeButtons=[...document.querySelectorAll("[data-flow-mode]")];
const PERIOD_WINDOW=T.WINDOW_MS;
let mode="tap",running=false,starting=false;
let ctx=null,noise=null,master=null,micStream=null,micSource=null,analyser=null;
let analyserBytes=null,signalEMA=.015,lastRms=0,lastOnsetMs=-Infinity;
let timer=0,animation=0,startPerf=0,beatStart=0,interval=0;
let nextBeat=0,nextAudio=0,currentIndex=-999,combo=0,maxCombo=0,perfect=0,good=0;
let hits=[],lastTap=-Infinity,latestScore=null,selectedBpm=92,selectedMode="tap";
const keyFor=(b,m)=>"reimflow_flow_best_v1_"+b+"_"+m;
const store={
  get:(k)=>{try{return localStorage.getItem(k)}catch{return null}},
  set:(k,v)=>{try{localStorage.setItem(k,String(v))}catch{}}
};
function setText(node,s){if(node)node.textContent=String(s)}
function setButtonMode(next){
  if(running||starting)return;
  mode=next;
  for(const b of modeButtons){const active=b.dataset.flowMode===mode;b.classList.toggle("active",active);b.setAttribute("aria-pressed",String(active))}
  setText(el.padHint,mode==="mic"?"Rap oder klatsch zum Beat · Kopfhörer nutzen":"Oder die Leertaste drücken");
  setText(el.hint,mode==="mic"?"Der Mikrofontest erkennt Lautstärkeimpulse nur auf deinem Gerät. Bitte Kopfhörer verwenden.":"Der Ton startet nach dem Start. Tippe oder drücke die Leertaste.");
  showBest();
}
function showBest(){
  const best=store.get(keyFor(Number(el.bpm.value),mode));
  setText(el.best,best===null?"--":best+"/100");
}
function notify(s){setText(el.judgement,s)}
function setControls(active){
  el.bpm.disabled=active;el.start.disabled=active;el.stop.disabled=!active;
  el.tap.disabled=!active||mode==="mic";
  modeButtons.forEach(b=>b.disabled=active);
  el.share.hidden=active||!latestScore;
  el.start.textContent=active?"⚡ LÄUFT…":"⚡ Spiel starten →";
}
function resetVisual(){
  cells.forEach(c=>{c.className="flow-beat"});
  el.stage.classList.remove("playing","counting","finished");
  el.orbit.classList.remove("pulse");
  setText(el.count,"▶");setText(el.stageLabel,"BEREIT FÜR DEN TAKT?");
  setText(el.barCount,"4 TAKTE · 16 SCHLÄGE");
  setText(el.score,"--");setText(el.rank,"Bist du im Takt?");
  setText(el.perfect,"0");setText(el.good,"0");setText(el.combo,"0");
  notify("Drücke Start und folge dem Takt.");
}
function cleanupAudio(){
  if(micSource){try{micSource.disconnect()}catch{}micSource=null}
  if(analyser){try{analyser.disconnect()}catch{}analyser=null}
  if(micStream){micStream.getTracks().forEach(t=>t.stop());micStream=null}
  if(ctx){const old=ctx;ctx=null;old.close().catch(()=>{})}
  master=null;noise=null;analyserBytes=null;
}
function clearPlayback(){
  running=false;starting=false;
  if(timer){clearInterval(timer);timer=0}
  if(animation){cancelAnimationFrame(animation);animation=0}
  cleanupAudio();setControls(false);
}
function stop(manual=true){
  if(!running&&!starting)return;
  clearPlayback();
  el.stage.classList.remove("counting","playing");
  if(manual){setText(el.stageLabel,"RUNDE ABGEBROCHEN");notify("Bereit für einen neuen Versuch.");setText(el.count,"■")}
}
function makeNoise(){
  const buffer=ctx.createBuffer(1,Math.ceil(ctx.sampleRate*.12),ctx.sampleRate);
  const data=buffer.getChannelData(0);
  // Deterministic pseudo-noise keeps transients consistent across runs.
  let seed=8349271;
  for(let i=0;i<data.length;i++){seed=(Math.imul(seed,1664525)+1013904223)>>>0;data[i]=(seed/4294967296*2)-1}
  noise=buffer;
}
function oscAt(time,freq,volume,duration,type="sine",slide=null){
  const osc=ctx.createOscillator(),env=ctx.createGain();
  osc.type=type;
  osc.frequency.setValueAtTime(freq,time);
  if(slide)osc.frequency.exponentialRampToValueAtTime(slide,time+duration);
  env.gain.setValueAtTime(.0001,time);
  env.gain.exponentialRampToValueAtTime(Math.max(.001,volume),time+.006);
  env.gain.exponentialRampToValueAtTime(.0001,time+duration);
  osc.connect(env);env.connect(master);
  osc.start(time);osc.stop(time+duration+.015);
}
function noiseAt(time,volume,filterFreq,duration){
  if(!noise)return;
  const source=ctx.createBufferSource(),filter=ctx.createBiquadFilter(),env=ctx.createGain();
  source.buffer=noise;filter.type="highpass";filter.frequency.value=filterFreq;
  env.gain.setValueAtTime(.0001,time);
  env.gain.exponentialRampToValueAtTime(Math.max(.001,volume),time+.002);
  env.gain.exponentialRampToValueAtTime(.0001,time+duration);
  source.connect(filter);filter.connect(env);env.connect(master);
  source.start(time);source.stop(time+duration+.006);
}
function beatSound(index,time){
  const countIn=index<T.COUNT_IN;
  const measurePos=index%4;
  if(countIn){
    oscAt(time,measurePos===0?1046:720,.09,.055,"sine");
    return;
  }
  const n=index-T.COUNT_IN,beat=n%4;
  // 4/4 backbeat — kick on 1/3, snare on 2/4, 8th-note closed hats.
  if(beat===0||beat===2)oscAt(time,155,.18,.155,"sine",48);
  if(beat===1||beat===3)noiseAt(time,.14,900,.12);
  noiseAt(time,.04,5200,.035);
  noiseAt(time+60/selectedBpm/2,.028,6100,.025);
}
function schedule(){
  if(!running||!ctx)return;
  while(nextBeat<T.COUNT_IN+T.BEATS&&nextAudio<ctx.currentTime+.15){
    beatSound(nextBeat,nextAudio);
    nextBeat++;nextAudio+=interval/1000;
  }
}
function updateStats(){
  setText(el.perfect,perfect);setText(el.good,good);setText(el.combo,combo);
}
function record(i,res){
  if(!running||i<0||i>=T.BEATS||hits[i])return false;
  hits[i]=res;
  cells[i].classList.remove("now");
  cells[i].classList.add(res.kind);
  if(res.kind==="miss")combo=0;
  else {combo++;maxCombo=Math.max(combo,maxCombo)}
  if(res.kind==="perfect")perfect++;
  if(res.kind==="good")good++;
  updateStats();
  if(res.kind!=="miss"){
    notify(res.label+(res.kind==="perfect"?" ✦":res.kind==="good"?" ✓":""));
    el.stage.classList.remove("hit");void el.stage.offsetWidth;el.stage.classList.add("hit");
  }
  return true;
}
function inputHit(at=performance.now()){
  if(!running||at-lastTap<95)return;
  const i=Math.round((at-beatStart)/interval);
  if(i<0||i>=T.BEATS)return;
  const offset=at-(beatStart+i*interval);
  if(Math.abs(offset)>PERIOD_WINDOW){if(at<beatStart)notify("Gleich geht's los!");return}
  if(hits[i])return;
  lastTap=at;
  record(i,T.judgeOffset(offset));
}
function finish(){
  if(!running)return;
  for(let i=0;i<T.BEATS;i++)if(!hits[i])record(i,{kind:"miss",points:0,label:"VERPASST"});
  const result=T.scoreRound(hits);latestScore={...result,bpm:selectedBpm,mode:selectedMode};
  clearPlayback();
  el.stage.classList.add("finished");el.stage.classList.remove("playing","counting");
  setText(el.count,String(result.score));setText(el.stageLabel,"RUNDE BEENDET");
  setText(el.score,result.score);setText(el.rank,result.title);
  notify(result.subtitle);
  setText(el.barCount,result.miss+" VERPASST · "+result.maxCombo+" BESTE SERIE");
  el.share.hidden=false;
  const key=keyFor(selectedBpm,selectedMode),prior=Number(store.get(key)||0);
  if(result.score>prior)store.set(key,result.score);
  showBest();
  window.ReimflowPlatform?.saveScore?.(latestScore);
}
function animate(){
  if(!running)return;
  const now=performance.now(),pos=(now-beatStart)/interval;
  if(pos<0){
    const countIndex=Math.min(T.COUNT_IN-1,Math.max(0,Math.floor((now-startPerf)/interval)));
    if(currentIndex!==-T.COUNT_IN+countIndex){
      currentIndex=-T.COUNT_IN+countIndex;
      setText(el.count,String(T.COUNT_IN-countIndex));
      setText(el.stageLabel,"EINZÄHLEN · TAKT FINDEN");
      setText(el.barCount,"GLEICH GEHT ES LOS");
      notify("Bereit? Hör erst den Einzähler.");
      el.stage.classList.add("counting");
    }
  }else{
    const i=Math.min(T.BEATS-1,Math.floor(pos));
    if(i!==currentIndex){
      if(currentIndex>=0&&currentIndex<T.BEATS&&(!hits[currentIndex])&&now>(beatStart+currentIndex*interval+PERIOD_WINDOW))record(currentIndex,{kind:"miss",points:0,label:"VERPASST"});
      currentIndex=i;
      el.stage.classList.remove("counting");el.stage.classList.add("playing");
      setText(el.count,String(i+1).padStart(2,"0"));
      setText(el.stageLabel,"TRIFF DEN TAKT!");
      setText(el.barCount,"TAKT "+(Math.floor(i/4)+1)+" / 4");
      cells.forEach((c,j)=>c.classList.toggle("now",j===i&&!hits[j]));
      el.orbit.classList.remove("pulse");void el.orbit.offsetWidth;el.orbit.classList.add("pulse");
    }
    for(let j=0;j<=i;j++){
      if(!hits[j]&&now>(beatStart+j*interval+PERIOD_WINDOW))record(j,{kind:"miss",points:0,label:"VERPASST"});
    }
    if(mode==="mic")sampleMic(now);
  }
  if(now>beatStart+(T.BEATS-1)*interval+PERIOD_WINDOW+200){finish();return}
  animation=requestAnimationFrame(animate);
}
function sampleMic(now){
  if(!analyser||!analyserBytes)return;
  analyser.getByteTimeDomainData(analyserBytes);
  let sum=0;
  for(let i=0;i<analyserBytes.length;i++){const v=(analyserBytes[i]-128)/128;sum+=v*v}
  const rms=Math.sqrt(sum/analyserBytes.length);
  const base=Math.max(.018,signalEMA*1.7);
  // Relative onset & refractory period, not voice recognition. Headphones prevent
  // the metronome audio from contaminating the detection.
  if(rms>base&&rms>lastRms*1.18&&rms-lastRms>.005&&now-lastOnsetMs>160){
    lastOnsetMs=now;inputHit(now);
  }
  signalEMA=signalEMA*.985+rms*.015;
  lastRms=rms;
}
async function activateMic(){
  if(!navigator.mediaDevices?.getUserMedia)throw Error("Mikrofon im Browser nicht verfügbar");
  micStream=await navigator.mediaDevices.getUserMedia({audio:{
    echoCancellation:true,noiseSuppression:true,autoGainControl:false
  },video:false});
  if(!ctx)throw Error("Audio wurde unterbrochen");
  analyser=ctx.createAnalyser();analyser.fftSize=1024;analyser.smoothingTimeConstant=.1;
  analyserBytes=new Uint8Array(analyser.fftSize);
  micSource=ctx.createMediaStreamSource(micStream);
  micSource.connect(analyser); // Never connect microphone to speakers, never record/upload.
  signalEMA=.018;lastRms=0;lastOnsetMs=-Infinity;
}
async function start(){
  if(starting||running)return;
  starting=true;selectedBpm=Number(el.bpm.value)||92;selectedMode=mode;
  interval=60000/selectedBpm;
  latestScore=null;el.share.hidden=true;resetVisual();
  setText(el.hint,"Audio wird vorbereitet…");
  setControls(true);
  try{
    const Audio=window.AudioContext||window.webkitAudioContext;
    if(!Audio)throw Error("Web Audio wird von diesem Browser nicht unterstützt.");
    ctx=new Audio();await ctx.resume();
    if(ctx.state!=="running")throw Error("Audio konnte nicht gestartet werden.");
    master=ctx.createGain();master.gain.value=.72;master.connect(ctx.destination);makeNoise();
    if(mode==="mic"){
      try{await activateMic()}
      catch(err){
        cleanupAudio();
        mode="tap";setButtonMode("tap");
        throw Error("Mikrofon nicht verfügbar. Bitte auf Tippen umstellen.");
      }
    }
    hits=Array.from({length:T.BEATS},()=>null);combo=0;maxCombo=0;perfect=0;good=0;
    currentIndex=-999;nextBeat=0;lastTap=-Infinity;
    const offset=.32;
    nextAudio=ctx.currentTime+offset;
    startPerf=performance.now()+(nextAudio-ctx.currentTime)*1000;
    beatStart=startPerf+T.COUNT_IN*interval;
    running=true;starting=false;
    setControls(true);
    el.stage.classList.add("counting");
    setText(el.hint,mode==="mic"?"Mikrofontest aktiv. Sprich oder klatsche deutlich im Takt.":"Tippe mit dem Finger oder drücke die Leertaste im Takt.");
    schedule();timer=setInterval(schedule,25);animation=requestAnimationFrame(animate);
  }catch(err){
    clearPlayback();latestScore=null;setControls(false);
    setText(el.stageLabel,"AUDIO NICHT VERFÜGBAR");
    notify(err?.message||"Audio konnte nicht gestartet werden.");
    setText(el.hint,"Tippe erneut auf Start, sobald Audio verfügbar ist.");
  }
}
async function share(){
  if(!latestScore)return;
  const x=latestScore;
  const text="🎤 Reimflow Rhythmusspiel: "+x.score+"/100 · "+x.title+" · "+x.bpm+" BPM · "+x.maxCombo+" Treffer in Folge. Schaffst du mehr? https://reimflow.smarbiz.sbs/";
  try{
    if(navigator.share)await navigator.share({title:"Reimflow Rhythmusspiel",text});
    else if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(text);notify("Ergebnis kopiert! ✦")}
    else notify(text);
  }catch(e){if(e?.name!=="AbortError")notify("Teilen im Browser nicht möglich.")}
}
modeButtons.forEach(b=>b.addEventListener("click",()=>setButtonMode(b.dataset.flowMode)));
el.bpm.addEventListener("change",showBest);
el.start.addEventListener("click",start);
el.stop.addEventListener("click",()=>stop(true));
el.share.addEventListener("click",share);
el.tap.addEventListener("pointerdown",e=>{
  if(e.button!==undefined&&e.button!==0)return;
  e.preventDefault();inputHit();
});
el.tap.addEventListener("click",e=>{
  // Keyboard activation or VoiceOver synthetic click, never double-score touch.
  if(e.detail===0)inputHit();
});
document.addEventListener("keydown",e=>{
  if(!running||mode!=="tap"||e.code!=="Space"||e.repeat)return;
  if(!page.classList.contains("active"))return;
  if(e.altKey||e.ctrlKey||e.metaKey)return;
  if(document.querySelector("dialog[open]"))return;
  if(["INPUT","TEXTAREA","SELECT","BUTTON"].includes(document.activeElement?.tagName))return;
  e.preventDefault();inputHit();
});
document.addEventListener("visibilitychange",()=>{if(document.hidden)stop(true)});
window.addEventListener("pagehide",()=>stop(true));
window.ReimflowFlowChallenge={
  onPageChange:(p)=>{if(p!=="flow")stop(true)},
  stop:()=>stop(true)
};
setButtonMode("tap");resetVisual();showBest();
})();
