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

const state={
points:Number(localStorage.getItem("reimflow_points")||120),
favorites:JSON.parse(localStorage.getItem("reimflow_favorites")||"[]"),
submissions:JSON.parse(localStorage.getItem("reimflow_submissions")||"null")||starterSubmissions,
beats:[...starterBeats],category:"Alle",syllables:"Alle",beatFilter:"Alle",currentQuery:"",
aiResults:[],queryAnalysis:null,searchSignature:"",engineOnline:null,searchLoading:false
};

const $=(s,root=document)=>root.querySelector(s);
const $$=(s,root=document)=>[...root.querySelectorAll(s)];
const normalize=s=>String(s||"").toLowerCase().trim().replace(/[.,!?;:()[\]{}"'´]/g,"").replace(/\s+/g," ");
const save=()=>{localStorage.setItem("reimflow_points",String(state.points));localStorage.setItem("reimflow_favorites",JSON.stringify(state.favorites));localStorage.setItem("reimflow_submissions",JSON.stringify(state.submissions));};
const toast=msg=>{const el=$("#toast");el.textContent=msg;el.classList.add("show");clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>el.classList.remove("show"),3000)};
const updatePoints=()=>$$("[data-points]").forEach(el=>el.textContent=state.points);
const syllableBucket=n=>Number(n)>=4?"4+":String(n);

function go(page){
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
  if(state.engineOnline===true){el.className="engine-state online";el.innerHTML="<span></span> AI Phonetic Engine"+(extra?" · "+escapeHtml(extra):"");return}
  if(state.engineOnline===false){el.className="engine-state offline";el.innerHTML="<span></span> Offline Fallback";return}
  el.className="engine-state";el.innerHTML="<span></span> Engine Check";
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
  const local=filteredRhymes();renderRhymes();
  if(state.currentQuery&&!local.length)searchRhymes(false);
});
$("#syllableFilter").addEventListener("change",e=>{
  state.syllables=e.target.value;
  const local=filteredRhymes();renderRhymes();
  if(state.currentQuery&&!local.length)searchRhymes(false);
});

function requestSignature(){return[normalize(state.currentQuery),state.category,state.syllables].join("|")}

async function searchRhymes(force=false){
  if(!state.currentQuery)return;
  const signature=requestSignature();
  if(!force&&signature===state.searchSignature&&state.aiResults.length){renderRhymes();return}
  state.searchLoading=true;updateEngineState();renderLoading();renderQueryInsight(null);
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),45000);
  try{
    const response=await fetch("/api/rhymes",{method:"POST",headers:{"Content-Type":"application/json","Accept":"application/json"},body:JSON.stringify({query:state.currentQuery,category:state.category,syllables:state.syllables}),signal:controller.signal});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(data.message||"AI Suche nicht verfügbar");
    state.aiResults=Array.isArray(data.rhymes)?data.rhymes:[];
    state.queryAnalysis=data.analysis||null;state.searchSignature=signature;state.engineOnline=true;state.searchLoading=false;
    renderRhymes();renderQueryInsight(state.queryAnalysis);updateEngineState(data.cached?"Cache":"Live");
  }catch(err){
    const fallback=curatedFallback[normalize(state.currentQuery)];
    state.searchLoading=false;state.engineOnline=false;
    if(fallback){
      state.aiResults=fallback.rhymes;state.queryAnalysis=fallback.analysis;state.searchSignature=signature;
      renderRhymes();renderQueryInsight(fallback.analysis,true);updateEngineState("Fallback");toast("AI gerade nicht erreichbar. Kuratierte Ersatztreffer werden gezeigt.");
    }else{
      state.aiResults=[];state.queryAnalysis=null;
      renderRhymes(err.name==="AbortError"?"Die Analyse hat zu lange gedauert. Bitte erneut versuchen.":err.message);updateEngineState();
    }
  }finally{clearTimeout(timer)}
}

function filteredRhymes(){
  return state.aiResults.filter(r=>{
    const categoryOk=state.category==="Alle"||r.category===state.category;
    const syllablesOk=state.syllables==="Alle"||syllableBucket(r.syllables)===state.syllables;
    return categoryOk&&syllablesOk;
  });
}

function renderLoading(){
  $("#resultsCount").textContent="Analysiere…";$("#resultsFor").textContent=" „"+state.currentQuery+"“";
  $("#rhymeResults").innerHTML=Array.from({length:5},(_,i)=>'<div class="rhyme-skeleton" style="--i:'+i+'"><span></span><div><b></b><small></small></div><i></i></div>').join("");
}

function renderQueryInsight(analysis,fallback=false){
  const el=$("#queryInsight");if(!el)return;
  if(!analysis){el.hidden=true;el.innerHTML="";return}
  const correction=analysis.correction&&normalize(analysis.correction)!==normalize(state.currentQuery)?'<button class="correction-chip" data-correction="'+escapeAttr(analysis.correction)+'">Meintest du „'+escapeHtml(analysis.correction)+'“?</button>':"";
  el.hidden=false;
  el.innerHTML='<div class="insight-main"><span class="insight-label">'+(fallback?"Fallback Analyse":"Klanganalyse")+'</span><strong>'+escapeHtml(analysis.interpreted_as||state.currentQuery)+'</strong><span class="ipa">'+escapeHtml(analysis.ipa||"")+'</span></div>'+
  '<div class="insight-meta"><span>'+escapeHtml(analysis.pronunciation||"")+'</span><span>'+(analysis.syllables||"?")+' Silben</span><span>'+escapeHtml(analysis.language||"")+'</span></div>'+correction+(analysis.note?'<p>'+escapeHtml(analysis.note)+'</p>':"");
}
$("#queryInsight")?.addEventListener("click",e=>{const b=e.target.closest("[data-correction]");if(!b)return;$("#rhymeQuery").value=b.dataset.correction;runSearch(b.dataset.correction,{stay:true,force:true})});

function renderRhymes(errorMessage=""){
  const list=$("#rhymeResults");
  if(!state.currentQuery){
    $("#resultsCount").textContent="Bereit";$("#resultsFor").textContent="";
    list.innerHTML='<div class="search-empty"><div class="empty-glyph">R</div><strong>Schreib ein Wort. Wir hören auf den Klang.</strong><p>Die Suche berücksichtigt Aussprache, Silben, Betonung, Umgangssprache und Multi Silben Reime.</p></div>';return;
  }
  const rows=filteredRhymes();$("#resultsCount").textContent=rows.length+" "+(rows.length===1?"Treffer":"Treffer");$("#resultsFor").textContent=' für „'+state.currentQuery+'“';
  if(errorMessage){
    list.innerHTML='<div class="search-empty error"><div class="empty-glyph">!</div><strong>Die Reimsuche konnte nicht geladen werden.</strong><p>'+escapeHtml(errorMessage)+'</p><button class="secondary-btn compact" id="retrySearch">Erneut versuchen</button></div>';
    $("#retrySearch")?.addEventListener("click",()=>searchRhymes(true));return;
  }
  if(!rows.length){
    list.innerHTML='<div class="search-empty"><div class="empty-glyph">∿</div><strong>Mit diesen Filtern gibt es gerade keine starken Treffer.</strong><p>Setze Wortart oder Silben auf „Alle“, oder starte eine neue AI Suche.</p><button class="secondary-btn compact" id="refineSearch">Neu analysieren</button></div>';
    $("#refineSearch")?.addEventListener("click",()=>searchRhymes(true));return;
  }
  list.innerHTML=rows.map(r=>{
    const fav=state.favorites.includes(r.word),score=Math.max(0,Math.min(100,Number(r.score)||0)),confidence=Math.max(0,Math.min(100,Number(r.confidence)||0));
    const tone=score>=90?"elite":score>=80?"strong":score>=70?"good":"loose";
    return '<article class="rhyme-card ai-rhyme '+tone+'"><div class="match-score" title="Klang Match">'+score+'</div>'+
    '<div class="rhyme-word"><div class="word-line"><strong>'+escapeHtml(r.word)+'</strong><span class="ai-chip">AI</span></div><small>'+escapeHtml(r.pronunciation||"")+(r.ipa?' · <span class="ipa-inline">'+escapeHtml(r.ipa)+'</span>':"")+'</small></div>'+
    '<div class="tag-row"><span class="micro-tag">'+escapeHtml(r.category||"Sonstiges")+'</span><span class="micro-tag">'+escapeHtml(String(r.syllables||"?"))+' Silben</span><span class="micro-tag">'+escapeHtml(r.kind||"Klang Reim")+'</span><span class="micro-tag">'+escapeHtml(r.register||"Standard")+'</span></div>'+
    '<div class="result-actions"><button class="icon-btn speak-result" data-word="'+escapeAttr(r.word)+'" aria-label="Aussprache anhören">♫</button><button class="favorite-btn '+(fav?"active":"")+'" data-fav="'+escapeAttr(r.word)+'" aria-label="Favorit">♥</button></div>'+
    '<div class="rhyme-explanation"><span class="confidence-meter"><i style="width:'+confidence+'%"></i></span><span>'+confidence+'% Sicherheit</span><p>'+escapeHtml(r.explanation||"")+'</p></div></article>';
  }).join("");
}

$("#rhymeResults").addEventListener("click",e=>{
  const speak=e.target.closest(".speak-result");if(speak)speakWord(speak.dataset.word);
  const fav=e.target.closest("[data-fav]");if(fav){const w=fav.dataset.fav;state.favorites=state.favorites.includes(w)?state.favorites.filter(x=>x!==w):[...state.favorites,w];save();renderRhymes();toast(state.favorites.includes(w)?"Zu Favoriten hinzugefügt":"Aus Favoriten entfernt")}
});
$("#speakQuery").addEventListener("click",()=>state.currentQuery&&speakWord(state.currentQuery));
$$(".speak-btn").forEach(b=>b.addEventListener("click",()=>speakWord(b.dataset.speak)));
function speakWord(text){if(!("speechSynthesis" in window)){toast("Aussprache wird von diesem Browser nicht unterstützt.");return}speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.lang="de-DE";u.rate=.86;speechSynthesis.speak(u)}

const submitDialog=$("#submitDialog");
$("#openSubmit").addEventListener("click",()=>submitDialog.showModal());
$("#submitRhymeForm").addEventListener("submit",e=>{e.preventDefault();const source=$("#submitSource").value.trim(),target=$("#submitTarget").value.trim();if(!source||!target)return;state.submissions.unshift({id:"u"+Date.now(),source,target,category:$("#submitCategory").value,syllables:$("#submitSyllables").value,pronunciation:$("#submitPronunciation").value.trim()||"Noch nicht angegeben",status:"pending",user:"@hosseinflow",age:"gerade eben",mine:true});state.points+=3;save();updatePoints();submitDialog.close();e.target.reset();renderCommunity();toast("+3 Punkte. Dein Reim wartet auf einen Test.")});

$$("[data-community-tab]").forEach(b=>b.addEventListener("click",()=>{const tab=b.dataset.communityTab;$$("[data-community-tab]").forEach(x=>x.classList.toggle("active",x===b));$$(".community-tab").forEach(x=>x.classList.toggle("active",x.id===(tab==="feed"?"communityFeed":"testerQueue")))}));

function submissionMarkup(s,tester=false){
  return '<article class="sticker-card submission-card" data-submission-card="'+s.id+'"><div><div class="submission-pair"><span>'+escapeHtml(s.source)+'</span><span class="arrow-pill">→</span><span>'+escapeHtml(s.target)+'</span></div>'+
  '<div class="submission-meta"><span class="micro-tag">'+escapeHtml(s.category)+'</span><span class="micro-tag">'+escapeHtml(String(s.syllables))+' Silben</span><span class="micro-tag">'+escapeHtml(s.pronunciation)+'</span><span class="micro-tag">'+escapeHtml(s.user)+' · '+escapeHtml(s.age)+'</span></div><div class="ai-review-slot"></div></div>'+
  (tester?'<div class="review-actions"><button class="ai-check-btn" data-ai-review="'+s.id+'">✦ AI Check</button><button class="approve-btn" data-review="accept" data-id="'+s.id+'">✓ Passt</button><button class="reject-btn" data-review="reject" data-id="'+s.id+'">× Nein</button></div>':'<span class="status-pill '+(s.status==="accepted"?"mint-bg":"")+'">'+(s.status==="accepted"?"BESTÄTIGT":"IM TEST")+'</span>')+'</article>';
}
function renderCommunity(){$("#communityFeed").innerHTML=state.submissions.filter(s=>s.status!=="rejected").slice(0,10).map(s=>submissionMarkup(s,false)).join("");const pending=state.submissions.filter(s=>s.status==="pending");$("#testerQueue").innerHTML=pending.length?pending.map(s=>submissionMarkup(s,true)).join(""):'<div class="empty-state">Aktuell gibt es keine offenen Reime zum Testen.</div>'}
$("#testerQueue").addEventListener("click",async e=>{
  const ai=e.target.closest("[data-ai-review]");
  if(ai){
    const s=state.submissions.find(x=>x.id===ai.dataset.aiReview);if(!s)return;ai.disabled=true;ai.textContent="AI prüft…";
    try{
      const r=await fetch("/api/validate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({source:s.source,target:s.target})});const data=await r.json();if(!r.ok)throw new Error(data.message||"AI Check nicht verfügbar");
      const card=document.querySelector('[data-submission-card="'+s.id+'"]'),slot=$(".ai-review-slot",card),verdict=data.verdict==="passt"?"Passt":data.verdict==="grenzwertig"?"Grenzwertig":"Passt nicht";
      slot.innerHTML='<div class="ai-review '+data.verdict+'"><strong>✦ AI: '+verdict+' · '+data.score+'/100</strong><span>'+escapeHtml(data.explanation||"")+'</span></div>';ai.textContent="✦ AI geprüft";
    }catch(err){ai.disabled=false;ai.textContent="✦ AI Check";toast(err.message)}return;
  }
  const b=e.target.closest("[data-review]");if(!b)return;const s=state.submissions.find(x=>x.id===b.dataset.id);if(!s)return;s.status=b.dataset.review==="accept"?"accepted":"rejected";state.points+=b.dataset.review==="accept"?5:2;save();updatePoints();renderCommunity();toast(b.dataset.review==="accept"?"+5 Punkte für den Test":"+2 Punkte für den Test");
});

const beatDialog=$("#beatDialog");
$("#openBeatUpload").addEventListener("click",()=>beatDialog.showModal());
$("#beatUploadForm").addEventListener("submit",e=>{e.preventDefault();const file=$("#beatFile").files[0];state.beats.unshift({id:"u"+Date.now(),title:$("#beatTitle").value.trim(),producer:"Hossein Flow",type:$("#beatType").value,bpm:Number($("#beatBpm").value),license:$("#beatLicense").value,art:"art-violet",plays:"neu",audio:file?URL.createObjectURL(file):null});beatDialog.close();e.target.reset();renderBeats();toast("Upload zur Testansicht hinzugefügt.")});
$("#beatFilters").addEventListener("click",e=>{const b=e.target.closest("button");if(!b)return;state.beatFilter=b.dataset.beatFilter;$$("#beatFilters button").forEach(x=>x.classList.toggle("active",x===b));renderBeats()});
$("#beatSearch").addEventListener("input",renderBeats);
function renderBeats(){const term=normalize($("#beatSearch")?.value||"");const rows=state.beats.filter(b=>(state.beatFilter==="Alle"||b.type===state.beatFilter)&&(!term||normalize(b.title+" "+b.producer).includes(term)));$("#beatGrid").innerHTML=rows.map(b=>'<article class="sticker-card beat-card"><div class="beat-art '+b.art+'"><button class="play-btn" data-play="'+b.id+'" aria-label="Abspielen">▶</button></div><div class="beat-info"><h3>'+escapeHtml(b.title)+'</h3><div class="beat-meta"><span class="micro-tag">'+b.type+'</span><span class="micro-tag">'+b.bpm+' BPM</span></div><div class="beat-footer"><span>von '+escapeHtml(b.producer)+'</span><span class="license-chip">'+escapeHtml(b.license)+'</span></div></div></article>').join("")}
$("#beatGrid").addEventListener("click",e=>{const b=e.target.closest("[data-play]");if(!b)return;const beat=state.beats.find(x=>x.id===b.dataset.play);if(beat?.audio){if(window.activeAudio)window.activeAudio.pause();window.activeAudio=new Audio(beat.audio);window.activeAudio.play();b.textContent="❚❚";window.activeAudio.onended=()=>b.textContent="▶"}else toast("Für diesen Demo Beat ist noch keine Audiodatei hinterlegt.")});

function renderProfile(){const accepted=state.submissions.filter(s=>s.status==="accepted").length+6;$("#acceptedCount").textContent=accepted;const mine=state.submissions.filter(s=>s.mine).slice(0,5);$("#profileActivity").innerHTML=mine.length?mine.map(s=>'<div class="activity-row"><strong>'+escapeHtml(s.source)+' → '+escapeHtml(s.target)+'</strong><span>'+(s.status==="accepted"?"bestätigt":"im Test")+'</span></div>').join(""):'<div class="empty-state">Noch keine eigenen Beiträge in diesem Browser.</div>'}
function escapeHtml(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function escapeAttr(s){return escapeHtml(s).replace(/"/g,"&quot;")}

updatePoints();renderCommunity();renderBeats();renderProfile();renderRhymes();checkEngine();
