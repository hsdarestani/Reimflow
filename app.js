const curatedFallback = {
  "berlin": {
    analysis:{input:"Berlin",interpreted_as:"Berlin",pronunciation:"ber-LIIN",ipa:"bɛʁˈliːn",syllables:2,language:"Deutsch",correction:null,note:"Betonung auf der zweiten Silbe."},
    rhymes:[
      {word:"Gewinn",pronunciation:"ge-WINN",ipa:"ɡəˈvɪn",syllables:2,category:"Nomen",register:"Standard",score:91,confidence:96,kind:"Near Rhyme",explanation:"Starker Schlussklang mit betonter i Silbe."},
      {word:"mittendrin",pronunciation:"mitten-DRIN",ipa:"ˌmɪtn̩ˈdʁɪn",syllables:3,category:"Umgangssprache",register:"Standard",score:90,confidence:95,kind:"Multi-Silben",explanation:"Sehr rap-tauglicher Endklang über mehrere Silben."},
      {word:"zieh hin",pronunciation:"ZII hin",ipa:"tsiː hɪn",syllables:2,category:"Verb",register:"Umgangssprache",score:83,confidence:91,kind:"Phrase",explanation:"Phrase mit gutem rhythmischem i Schluss."}
    ]
  },
  "mission": {
    analysis:{input:"Mission",interpreted_as:"Mission",pronunciation:"mis-SJON",ipa:"mɪˈsi̯oːn",syllables:2,language:"Deutsch",correction:null,note:"Deutsche Aussprache mit Betonung am Ende."},
    rhymes:[
      {word:"Vision",pronunciation:"vi-SJON",ipa:"viˈzi̯oːn",syllables:2,category:"Nomen",register:"Standard",score:97,confidence:99,kind:"Perfekter Reim",explanation:"Sehr starker gemeinsamer Schlussklang."},
      {word:"Position",pronunciation:"po-zi-ZJON",ipa:"poziˈtsi̯oːn",syllables:3,category:"Nomen",register:"Standard",score:94,confidence:98,kind:"Multi-Silben",explanation:"Langer gemeinsamer Klangkern vor der Endsilbe."},
      {word:"Million",pronunciation:"mil-JON",ipa:"mɪlˈjoːn",syllables:2,category:"Nomen",register:"Standard",score:88,confidence:95,kind:"Near Rhyme",explanation:"Guter offener Endklang für Rap."}
    ]
  }
};

const starterSubmissions=[
{id:"s1",source:"Bellingham",target:"Telegramm",category:"Nomen",syllables:"3",pronunciation:"te le gram",status:"pending",user:"@linefactory",age:"vor 4 Min."},
{id:"s2",source:"Berlin",target:"mittendrin",category:"Umgangssprache",syllables:"3",pronunciation:"mit ten drin",status:"accepted",user:"@nachtstudio",age:"vor 12 Min."},
{id:"s3",source:"Mission",target:"Position",category:"Nomen",syllables:"3",pronunciation:"po zi tsi on",status:"accepted",user:"@mickönig",age:"vor 18 Min."}
];

const starterBeats=[
{id:"b1",title:"Purple Steps",producer:"Nachtstudio",type:"Beat",bpm:92,license:"Free Use",art:"art-violet",plays:"1.2k"},
{id:"b2",title:"Golden Loop",producer:"Milo Keys",type:"Sample",bpm:76,license:"Non Commercial",art:"art-yellow",plays:"860"},
{id:"b3",title:"City Bounce",producer:"Westblock",type:"Beat",bpm:104,license:"Commercial License",art:"art-mint",plays:"2.4k"},
{id:"b4",title:"Velvet Vox",producer:"Lina.wav",type:"Sample",bpm:88,license:"Free Use",art:"art-violet",plays:"640"},
{id:"b5",title:"Late Train",producer:"92BPM",type:"Beat",bpm:92,license:"Non Commercial",art:"art-yellow",plays:"1.7k"},
{id:"b6",title:"Glass Keys",producer:"Ari Loops",type:"Sample",bpm:110,license:"Commercial License",art:"art-mint",plays:"510"}
];

let activeSearchController=null;
let searchSequence=0;

const state={
points:0,
favorites:[],
submissions:[],
beats:[],category:"Alle",syllables:"Alle",beatFilter:"Alle",currentQuery:"",
aiResults:[],queryAnalysis:null,searchSignature:"",engineOnline:null,searchLoading:false,resultSource:"ai"
};

const $=(s,root=document)=>root.querySelector(s);
const $$=(s,root=document)=>[...root.querySelectorAll(s)];
const normalize=s=>String(s||"").toLowerCase().trim().replace(/[.,!?;:()[\]{}"'´]/g,"").replace(/\s+/g," ");
const save=()=>{localStorage.setItem("reimflow_points",String(state.points));localStorage.setItem("reimflow_favorites",JSON.stringify(state.favorites));localStorage.setItem("reimflow_submissions",JSON.stringify(state.submissions));};
const toast=msg=>{const el=$("#toast");el.textContent=msg;el.classList.add("show");clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>el.classList.remove("show"),3000)};
const updatePoints=()=>$$("[data-points]").forEach(el=>el.textContent=state.points);
const syllableBucket=n=>Number(n)>=4?"4+":String(n);

const rhymeKindLabel=kind=>({
  "Perfect Rhyme":"Perfekter Reim",
  "Near Rhyme":"Ähnlicher Reim",
  "Slant Rhyme":"Unreiner Reim",
  "Multi-Syllabic":"Mehrsilbiger Reim",
  "Multisyllabic":"Mehrsilbiger Reim",
  "Multi-Silben":"Mehrsilbig",
  "Internal Rhyme":"Binnenreim",
  "Assonance":"Assonanz",
  "Phrase":"Wortgruppe"
})[kind]||kind;
const licenseLabel=license=>({
  "Free Use":"Kostenlose Nutzung",
  "Non Commercial":"Nicht kommerziell",
  "Commercial License":"Kommerzielle Lizenz"
})[license]||license;

function go(page){
  window.ReimflowFlowChallenge?.onPageChange(page);
  window.ReimflowRapFlow?.onPageChange(page);
  $$(".page").forEach(p=>p.classList.toggle("active",p.dataset.page===page));
  $$("[data-go]").forEach(b=>b.classList.toggle("active",b.dataset.go===page));
  window.scrollTo({top:0,behavior:"smooth"});
  if(page==="community")renderCommunity();
  if(page==="beats")renderBeats();
  if(page==="profile")renderProfile();
  if(page==="rhymes"&&!state.currentQuery)renderRhymes();
}
$$("[data-go]").forEach(btn=>btn.addEventListener("click",e=>{e.preventDefault();go(btn.dataset.go)}));

async function checkEngine(){
  try{
    const r=await fetch("/api/health",{headers:{"Accept":"application/json"}});
    const data=await r.json();
    state.engineOnline=Boolean(r.ok&&data.ai);updateEngineState();
  }catch{state.engineOnline=false;updateEngineState()}
}
function updateEngineState(extra=""){
  const el=$("#engineState");if(!el)return;
  if(state.searchLoading){el.className="engine-state loading";el.innerHTML="<span></span> Klang wird analysiert…";return}
  if(state.engineOnline===true){el.className="engine-state online";el.innerHTML="<span></span> KI Reimsuche"+(extra?" · "+escapeHtml(extra):"");return}
  if(state.engineOnline===false){el.className="engine-state offline";el.innerHTML="<span></span> KI gerade nicht erreichbar";return}
  el.className="engine-state";el.innerHTML="<span></span> Verbindung wird geprüft";
}

$$("[data-example]").forEach(btn=>btn.addEventListener("click",()=>{$("#heroQuery").value=btn.dataset.example;runSearch(btn.dataset.example)}));
$("#heroSearch").addEventListener("submit",e=>{e.preventDefault();runSearch($("#heroQuery").value)});
$("#rhymeSearchForm").addEventListener("submit",e=>{e.preventDefault();runSearch($("#rhymeQuery").value,{stay:true,force:true})});

async function runSearch(query,{stay=false,force=false}={}){
  const cleaned=String(query||"").trim();
  if(!cleaned){toast("Bitte zuerst ein Wort oder eine Phrase eingeben.");return}
  state.currentQuery=cleaned.slice(0,120);$("#rhymeQuery").value=state.currentQuery;
  if(!stay)go("rhymes");
  await searchRhymes(force);
}

$("#categoryFilters").addEventListener("click",e=>{
  const b=e.target.closest("button");if(!b)return;
  state.category=b.dataset.category;
  $$("#categoryFilters button").forEach(x=>x.classList.toggle("active",x===b));
  // Both filters are local; do not restart a live AI request or call the AI twice.
  if(state.searchLoading)renderLoading();else renderRhymes();
});
$("#syllableFilter").addEventListener("change",e=>{
  state.syllables=e.target.value;
  // Both filters are local; do not restart a live AI request or call the AI twice.
  if(state.searchLoading)renderLoading();else renderRhymes();
});

function requestSignature(){return normalize(state.currentQuery)}

function setSearchBusy(busy){
  const buttons=[
    document.querySelector("#heroSearch button[type='submit']"),
    document.querySelector("#rhymeSearchForm button[type='submit']")
  ].filter(Boolean);
  buttons.forEach(button=>{
    button.disabled=busy;
    button.setAttribute("aria-busy",String(busy));
    if(!button.dataset.originalLabel)button.dataset.originalLabel=button.innerHTML;
    button.innerHTML=busy?'Analysiere… <span>···</span>':button.dataset.originalLabel;
  });
}

async function searchRhymes(force=false){
  if(!state.currentQuery)return;
  const signature=requestSignature();
  if(!force&&signature===state.searchSignature&&state.engineOnline===true){renderRhymes();return}

  if(activeSearchController) activeSearchController.abort();
  activeSearchController=new AbortController();
  const controller=activeSearchController;
  const seq=++searchSequence;

  state.searchLoading=true;setSearchBusy(true);updateEngineState();renderLoading();renderQueryInsight(null);
  const timer=setTimeout(()=>controller.abort(),255000);
  try{
    const response=await fetch("/api/rhymes",{method:"POST",headers:{"Content-Type":"application/json","Accept":"application/json"},body:JSON.stringify({query:state.currentQuery,category:state.category,syllables:state.syllables}),signal:controller.signal});
    let data=await response.json().catch(()=>({}));
    if(seq!==searchSequence)return;
    if(!response.ok)throw new Error(data.message||"KI Suche nicht verfügbar");
    // Long-running, independently reviewed model requests stay on the server.
    // Each poll is a short HTTP request, avoiding mobile/proxy timeouts.
    let polling=0;
    while(data.pending===true){
      if(!data.job_id || !/^[a-zA-Z0-9_-]{20,80}$/.test(data.job_id))throw new Error("Ungültige KI Suchanfrage.");
      if(++polling>135)throw new Error("Die KI braucht ungewöhnlich lange. Bitte später erneut versuchen.");
      const stage=data.stage;
      const progress=$("#searchProgressText");
      if(progress)progress.textContent=stage==="review"
        ?"Die zweite KI prüft jetzt Aussprache und Reimqualität…"
        :"Wir suchen echte Wortreime und passende mehrteilige Rap Phrasen…";
      await new Promise(resolve=>setTimeout(resolve,Math.min(4000,Math.max(1200,data.poll_after_ms||2200))));
      if(seq!==searchSequence || controller.signal.aborted)return;
      const poll=await fetch("/api/rhymes/jobs/"+encodeURIComponent(data.job_id),{
        headers:{"Accept":"application/json"},signal:controller.signal,cache:"no-store"});
      data=await poll.json().catch(()=>({}));
      if(!poll.ok)throw new Error(data.message||"KI Suche nicht verfügbar");
      if(poll.status!==202&&data.pending!==true)break;
    }
    if(data.ok!==true || data.quality_reviewed!==true)throw new Error("Die unabhängige Klangprüfung konnte nicht abgeschlossen werden.");
    state.aiResults=Array.isArray(data.rhymes)?data.rhymes:[];
    state.queryAnalysis=data.analysis||null;state.searchSignature=signature;state.engineOnline=true;state.searchLoading=false;state.resultSource=data.engine==="offline_suffix"?"offline_suffix":"ai";
    renderRhymes();renderQueryInsight(state.queryAnalysis);updateEngineState(data.cached?"Zwischenspeicher":"Aktuell");
  }catch(err){
    if(seq!==searchSequence)return;
    if(err.name==="AbortError" && controller!==activeSearchController)return;
    // No automatic suffix-based stand-ins: accuracy is more important than results.
    const fallback=null;
    state.searchLoading=false;
    if(fallback){
      state.engineOnline=false;state.resultSource=fallback.source||"curated";
      state.aiResults=fallback.rhymes;state.queryAnalysis=fallback.analysis;state.searchSignature=signature;
      renderRhymes();renderQueryInsight(fallback.analysis,true);updateEngineState();toast("KI derzeit nicht erreichbar. Ungeprüfte Wortideen werden angezeigt.");
    }else{
      state.aiResults=[];state.queryAnalysis=null;state.resultSource="ai";
      if(err.name==="AbortError"){
        state.engineOnline=true;
        renderRhymes("Die Analyse wurde nach längerer Wartezeit abgebrochen. Bitte erneut versuchen.");
        updateEngineState("Zeitüberschreitung");
      }else{
        state.engineOnline=false;
        renderRhymes(err.message);
        updateEngineState();
      }
    }
  }finally{
    clearTimeout(timer);
    if(seq===searchSequence){
      state.searchLoading=false;
      setSearchBusy(false);
      if(activeSearchController===controller)activeSearchController=null;
    }
  }
}

function filteredRhymes(){
  return state.aiResults.filter(r=>{
    if(r.german_valid!==true || r.register==="Englisch/Code-Switch")return false;
    const categoryOk=state.category==="Alle"||r.category===state.category;
    const syllablesOk=state.syllables==="Alle"||syllableBucket(r.syllables)===state.syllables;
    return categoryOk&&syllablesOk;
  });
}

function renderLoading(){
  $("#resultsCount").textContent="Analysiere…";$("#resultsFor").textContent=" „"+state.currentQuery+"“";
  const preview=window.ReimflowRhymePreviews?.find(state.currentQuery);
  const phraseWords=state.currentQuery.trim().split(/\s+/);
  const anchorWord=phraseWords.at(-1)||"";
  const phraseHint=phraseWords.length>1?'<div class="rhyme-anchor-chooser">Ganze Phrase: <strong>'+escapeHtml(state.currentQuery)+'</strong> · Endwort: <strong>'+escapeHtml(anchorWord)+'</strong><button type="button" class="secondary-btn compact" id="onlyRhymeAnchor">Nur „'+escapeHtml(anchorWord)+'“ suchen</button></div>':"";
  const first=(preview?'<div class="rhyme-preview"><strong>Sofort-Ideen fürs Endwort „'+escapeHtml(preview.anchor)+'“</strong><span class="rhyme-preview-note">Wörterbuchbeispiele, noch nicht durch die KI geprüft</span><div class="rhyme-preview-tags">'+preview.words.map(x=>'<span>'+escapeHtml(x)+'</span>').join('')+'</div>'+(preview.phrases.length?'<p>Mehrteilige Rap-Ideen: <b>'+preview.phrases.map(escapeHtml).join(' · ')+'</b></p>':'')+'<small>'+escapeHtml(preview.note)+'</small></div>':'');
  $("#rhymeResults").innerHTML=phraseHint+first+'<div class="search-progress-copy"><strong>KI prüft gerade Aussprache und Reimqualität</strong><span id="searchProgressText">Endwort und ganze Phrase werden getrennt analysiert. Du kannst die Seite weiter nutzen.</span><button class="secondary-btn compact" type="button" id="cancelRhymeSearch">Abbrechen</button></div>'+Array.from({length:3},(_,i)=>'<div class="rhyme-skeleton" style="--i:'+i+'"><span></span><div><b></b><small></small></div><i></i></div>').join("");
  $("#onlyRhymeAnchor")?.addEventListener("click",()=>runSearch(anchorWord,{stay:true,force:true}));
  $("#cancelRhymeSearch")?.addEventListener("click",()=>{
    if(activeSearchController)activeSearchController.abort();
    searchSequence++;state.searchLoading=false;setSearchBusy(false);
    renderRhymes("Suche abgebrochen. Du kannst eine neue Suche starten.");
  });
  const seqNow=searchSequence;
  setTimeout(()=>{if(seqNow===searchSequence&&state.searchLoading){const el=$("#searchProgressText");if(el)el.textContent="Die KI sucht Wortreime und sinnvolle mehrteilige Formulierungen…"}},7000);
  setTimeout(()=>{if(seqNow===searchSequence&&state.searchLoading){const el=$("#searchProgressText");if(el)el.textContent="Die zweite KI prüft den Klang. Solange sind die ersten Ideen oben sichtbar."}},16000);
}

function renderQueryInsight(analysis,fallback=false){
  const el=$("#queryInsight");if(!el)return;
  if(!analysis){el.hidden=true;el.innerHTML="";return}
  const correction=analysis.correction&&normalize(analysis.correction)!==normalize(state.currentQuery)?'<button class="correction-chip" data-correction="'+escapeAttr(analysis.correction)+'">Meintest du „'+escapeHtml(analysis.correction)+'“?</button>':"";
  el.hidden=false;
  el.innerHTML='<div class="insight-main"><span class="insight-label">'+(fallback?"Ungeprüfte Wortideen":"Klanganalyse")+'</span><strong>'+escapeHtml(analysis.interpreted_as||state.currentQuery)+'</strong><span class="ipa">'+escapeHtml(analysis.ipa||"")+'</span></div>'+
  '<div class="insight-meta"><span>'+escapeHtml(analysis.pronunciation||"")+'</span><span>'+(analysis.syllables||"?")+' Silben</span><span>'+escapeHtml(analysis.language||"")+'</span></div>'+correction+(analysis.note?'<p>'+escapeHtml(analysis.note)+'</p>':"");
}
$("#queryInsight")?.addEventListener("click",e=>{const b=e.target.closest("[data-correction]");if(!b)return;$("#rhymeQuery").value=b.dataset.correction;runSearch(b.dataset.correction,{stay:true,force:true})});

function renderRhymes(errorMessage=""){
  const list=$("#rhymeResults");
  if(!state.currentQuery){
    $("#resultsCount").textContent="Bereit";$("#resultsFor").textContent="";
    list.innerHTML='<div class="search-empty"><div class="empty-glyph">R</div><strong>Schreib ein Wort. Wir hören auf den Klang.</strong><p>Die Suche berücksichtigt Aussprache, Silben, Betonung, Umgangssprache und Multi Silben Reime.</p></div>';return;
  }
  const rows=filteredRhymes();$("#resultsCount").textContent=errorMessage?"Suche fehlgeschlagen":rows.length+" "+(rows.length===1?"Treffer":"Treffer");$("#resultsFor").textContent=' für „'+state.currentQuery+'“';
  if(errorMessage){
    list.innerHTML='<div class="search-empty error"><div class="empty-glyph">!</div><strong>Die Reimsuche konnte nicht geladen werden.</strong><p>'+escapeHtml(errorMessage)+'</p><button class="secondary-btn compact" id="retrySearch">Erneut versuchen</button></div>';
    $("#retrySearch")?.addEventListener("click",()=>searchRhymes(true));return;
  }
  if(!rows.length){
    list.innerHTML='<div class="search-empty"><div class="empty-glyph">∿</div><strong>Keine bestätigten Reime für diesen Suchversuch.</strong><p>Das bedeutet nicht, dass es keine Reime gibt. Versuche die Suche erneut oder gib das letzte Wort alleine ein. Bei mehrteiligen Eingaben werden Endwort und Gesamtphrase getrennt geprüft.</p><button class="secondary-btn compact" id="refineSearch">Neu analysieren</button><button class="secondary-btn compact" id="findAnchorOnly" hidden>Nur letztes Wort suchen</button></div>';
    $("#refineSearch")?.addEventListener("click",()=>searchRhymes(true));
    const words=state.currentQuery.trim().split(/\s+/);
    if(words.length>1){
      const anchor=words.at(-1),b=$("#findAnchorOnly");
      b.hidden=false;b.textContent="Nur „"+anchor+"“ suchen";
      b.addEventListener("click",()=>runSearch(anchor,{stay:true,force:true}));
    }
    return;
  }
  const offline=state.resultSource!=="ai";
  const hasPhrase=state.currentQuery.trim().split(/\s+/).length>1;
  const scopeTitle={full_phrase:"Ganzer Ausdruck",phrase_variation:"Kreative mehrteilige Reime",end_word:"Reime auf das letzte Wort"};
  const grouped=hasPhrase?[
    ...rows.filter(r=>r.scope==="full_phrase"),
    ...rows.filter(r=>r.scope==="phrase_variation"),
    ...rows.filter(r=>!r.scope||r.scope==="end_word")
  ]:rows;
  const caveat=offline?'<div class="rhyme-offline-note"><strong>Vorschläge ohne KI-Prüfung</strong><p>Diese Wörter haben ähnliche Endungen. Aussprache, Betonung und Reimqualität sind nicht geprüft. Bitte selbst anhören oder die KI Suche später erneut versuchen.</p><button class="secondary-btn compact" id="retryOnlineSearch">KI Suche erneut versuchen</button></div>':"";
  let lastScope="";
  list.innerHTML=caveat+grouped.map(r=>{
    const scope=hasPhrase?(r.scope||"end_word"):"end_word";
    const heading=scope!==lastScope?(lastScope=scope,'<div class="rhyme-group-title">'+escapeHtml(scopeTitle[scope]||"Reime aufs Endwort")+'</div>'):"";
    const fav=state.favorites.includes(r.word);
    const strength=r.strength==="stark"?"stark":"brauchbar";
    const label=offline?"IDEE":strength==="stark"?"STARK":"NAH";
    const tone=strength==="stark"?"elite":"good";
    return heading+'<article class="rhyme-card ai-rhyme '+tone+'"><div class="match-score" title="Einschätzung einer zweiten KI Prüfung">'+label+'</div>'+
    '<div class="rhyme-word"><div class="word-line"><strong>'+escapeHtml(r.word)+'</strong><span class="ai-chip"+(offline?" source-offline":"")+"">"+(offline?"IDEE":"KI")+"</span></div><small>'+escapeHtml(r.pronunciation||"")+(r.ipa?' · <span class="ipa-inline">'+escapeHtml(r.ipa)+'</span>':"")+'</small></div>'+
    '<div class="tag-row"><span class="micro-tag">'+escapeHtml(r.category||"Sonstiges")+'</span><span class="micro-tag">'+escapeHtml(String(r.syllables||"?"))+' Silben</span><span class="micro-tag">'+escapeHtml(rhymeKindLabel(r.kind||"Klangreim"))+'</span><span class="micro-tag">'+escapeHtml(r.register||"Standard")+'</span></div>'+
    '<div class="result-actions"><button class="icon-btn speak-result" data-word="'+escapeAttr(r.word)+'" aria-label="Aussprache anhören">♫</button><button class="favorite-btn '+(fav?"active":"")+'" data-fav="'+escapeAttr(r.word)+'" aria-label="Favorit">♥</button></div>'+
    '<div class="rhyme-explanation"><span class="review-explanation-label">'+(offline?"Nicht geprüft":"Zweite KI Klangprüfung · keine Wahrscheinlichkeitsangabe")+'</span><p>'+escapeHtml(r.explanation||"")+'</p></div></article>';
  }).join("");
  if(offline)$("#retryOnlineSearch")?.addEventListener("click",()=>searchRhymes(true));
}

$("#rhymeResults").addEventListener("click",e=>{
  const speak=e.target.closest(".speak-result");if(speak)speakWord(speak.dataset.word);
  const fav=e.target.closest("[data-fav]");if(fav)window.ReimflowPlatform?.toggleFavorite(fav.dataset.fav);
});
$("#speakQuery").addEventListener("click",()=>state.currentQuery&&speakWord(state.currentQuery));
$$(".speak-btn").forEach(b=>b.addEventListener("click",()=>speakWord(b.dataset.speak)));
function speakWord(text){if(!("speechSynthesis" in window)){toast("Aussprache wird von diesem Browser nicht unterstützt.");return}speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.lang="de-DE";u.rate=.86;speechSynthesis.speak(u)}

function escapeHtml(value){return String(value??"").replace(/[&<>"\x27]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","\x27":"&#39;"}[c]));}
function escapeAttr(value){return escapeHtml(value).replace(/"/g,"&quot;");}
// Real user content is rendered and persisted by platform.js.
function renderCommunity(){window.ReimflowPlatform?.renderCommunity();}
function renderBeats(){window.ReimflowPlatform?.renderBeats();}
function renderProfile(){window.ReimflowPlatform?.renderProfile();}
updatePoints();renderRhymes();checkEngine();
