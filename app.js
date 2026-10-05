const rhymeData = [
  {word:"blue Talisman", pronunciation:"bluː ta lis man", syllables:"4+", category:"Umgangssprache", score:91, source:["jude bellingham","bellingham"], kind:"Multi Silben"},
  {word:"Telegramm", pronunciation:"te le gram", syllables:"3", category:"Nomen", score:86, source:["jude bellingham","bellingham"], kind:"Klang Reim"},
  {word:"elegant", pronunciation:"e le gant", syllables:"3", category:"Adjektiv", score:79, source:["jude bellingham","bellingham"], kind:"Near Rhyme"},
  {word:"Maybach Turbo", pronunciation:"mai bach tur bo", syllables:"4+", category:"Nomen", score:88, source:["taycan turbo"], kind:"Phrase"},
  {word:"Nightclub Turbo", pronunciation:"nait klab tur bo", syllables:"4+", category:"Umgangssprache", score:82, source:["taycan turbo"], kind:"Near Rhyme"},
  {word:"mittendrin", pronunciation:"mit ten drin", syllables:"3", category:"Adjektiv", score:94, source:["berlin"], kind:"Endreim"},
  {word:"Gewinn", pronunciation:"ge vinn", syllables:"2", category:"Nomen", score:91, source:["berlin"], kind:"Endreim"},
  {word:"beginn", pronunciation:"be ginn", syllables:"2", category:"Verb", score:89, source:["berlin"], kind:"Endreim"},
  {word:"Kinn", pronunciation:"kinn", syllables:"1", category:"Nomen", score:85, source:["berlin"], kind:"Endreim"},
  {word:"Vision", pronunciation:"vi zi on", syllables:"3", category:"Nomen", score:80, source:["mission"], kind:"Klang Reim"},
  {word:"Position", pronunciation:"po zi tsi on", syllables:"4+", category:"Nomen", score:92, source:["mission"], kind:"Multi Silben"},
  {word:"Million", pronunciation:"mil li on", syllables:"3", category:"Nomen", score:84, source:["mission"], kind:"Klang Reim"}
];

const starterSubmissions = [
  {id:"s1",source:"Bellingham",target:"Telegramm",category:"Nomen",syllables:"3",pronunciation:"te le gram",status:"pending",user:"@linefactory",age:"vor 4 Min."},
  {id:"s2",source:"Berlin",target:"mittendrin",category:"Adjektiv",syllables:"3",pronunciation:"mit ten drin",status:"accepted",user:"@nachtstudio",age:"vor 12 Min."},
  {id:"s3",source:"Mission",target:"Position",category:"Nomen",syllables:"4+",pronunciation:"po zi tsi on",status:"accepted",user:"@mickönig",age:"vor 18 Min."}
];

const starterBeats = [
  {id:"b1",title:"Purple Steps",producer:"Nachtstudio",type:"Beat",bpm:92,license:"Free Use",art:"art-violet",plays:"1.2k"},
  {id:"b2",title:"Golden Loop",producer:"Milo Keys",type:"Sample",bpm:76,license:"Non Commercial",art:"art-yellow",plays:"860"},
  {id:"b3",title:"City Bounce",producer:"Westblock",type:"Beat",bpm:104,license:"Commercial License",art:"art-mint",plays:"2.4k"},
  {id:"b4",title:"Velvet Vox",producer:"Lina.wav",type:"Sample",bpm:88,license:"Free Use",art:"art-violet",plays:"640"},
  {id:"b5",title:"Late Train",producer:"92BPM",type:"Beat",bpm:92,license:"Non Commercial",art:"art-yellow",plays:"1.7k"},
  {id:"b6",title:"Glass Keys",producer:"Ari Loops",type:"Sample",bpm:110,license:"Commercial License",art:"art-mint",plays:"510"}
];

const state = {
  points:Number(localStorage.getItem("reimflow_points")||120),
  favorites:JSON.parse(localStorage.getItem("reimflow_favorites")||"[]"),
  submissions:JSON.parse(localStorage.getItem("reimflow_submissions")||"null") || starterSubmissions,
  beats:[...starterBeats],
  category:"Alle",
  syllables:"Alle",
  beatFilter:"Alle",
  currentQuery:"Jude Bellingham"
};

const $ = (s,root=document)=>root.querySelector(s);
const $$ = (s,root=document)=>[...root.querySelectorAll(s)];
const normalize=s=>s.toLowerCase().trim().replace(/[.,!?]/g,"");
const save=()=>{localStorage.setItem("reimflow_points",String(state.points));localStorage.setItem("reimflow_favorites",JSON.stringify(state.favorites));localStorage.setItem("reimflow_submissions",JSON.stringify(state.submissions));};
const toast=msg=>{const el=$("#toast");el.textContent=msg;el.classList.add("show");clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>el.classList.remove("show"),2600)};
const updatePoints=()=>$$("[data-points]").forEach(el=>el.textContent=state.points);

function go(page){
  $$(".page").forEach(p=>p.classList.toggle("active",p.dataset.page===page));
  $$("[data-go]").forEach(b=>b.classList.toggle("active",b.dataset.go===page));
  window.scrollTo({top:0,behavior:"smooth"});
  if(page==="community") renderCommunity();
  if(page==="beats") renderBeats();
  if(page==="profile") renderProfile();
}
$$("[data-go]").forEach(btn=>btn.addEventListener("click",e=>{e.preventDefault();go(btn.dataset.go)}));

$$("[data-example]").forEach(btn=>btn.addEventListener("click",()=>{
  $("#heroQuery").value=btn.dataset.example;
  runSearch(btn.dataset.example);
}));

$("#heroSearch").addEventListener("submit",e=>{e.preventDefault();runSearch($("#heroQuery").value)});
function runSearch(query){
  state.currentQuery=query.trim()||"Jude Bellingham";
  $("#rhymeQuery").value=state.currentQuery;
  renderRhymes();
  go("rhymes");
}
$("#rhymeSearchForm").addEventListener("submit",e=>{e.preventDefault();state.currentQuery=$("#rhymeQuery").value.trim();renderRhymes()});

$("#categoryFilters").addEventListener("click",e=>{
  const b=e.target.closest("button");if(!b)return;
  state.category=b.dataset.category;
  $$("#categoryFilters button").forEach(x=>x.classList.toggle("active",x===b));
  renderRhymes();
});
$("#syllableFilter").addEventListener("change",e=>{state.syllables=e.target.value;renderRhymes()});

function genericScore(query,word){
  const a=normalize(query),b=normalize(word);
  let common=0;for(let i=1;i<=Math.min(5,a.length,b.length);i++)if(a.slice(-i)===b.slice(-i))common=i;
  return 55+common*8;
}
function filteredRhymes(){
  const q=normalize(state.currentQuery);
  let results=rhymeData.filter(r=>r.source.some(s=>q.includes(s)||s.includes(q)));
  if(!results.length){
    results=rhymeData.map(r=>({...r,score:Math.min(88,genericScore(q,r.word))})).sort((a,b)=>b.score-a.score).slice(0,5);
  }
  return results.filter(r=>(state.category==="Alle"||r.category===state.category)&&(state.syllables==="Alle"||r.syllables===state.syllables));
}
function renderRhymes(){
  const rows=filteredRhymes();
  $("#resultsCount").textContent=rows.length+" "+(rows.length===1?"Reim":"Reime");
  $("#resultsFor").textContent=" für „"+state.currentQuery+"“";
  const list=$("#rhymeResults");
  if(!rows.length){list.innerHTML='<div class="empty-state"><strong>Keine Treffer mit diesen Filtern.</strong><br>Ändere Wortart oder Silben und versuche es erneut.</div>';return}
  list.innerHTML=rows.map(r=>{
    const fav=state.favorites.includes(r.word);
    return '<article class="rhyme-card">'+
      '<div class="match-score">'+r.score+'</div>'+
      '<div class="rhyme-word"><strong>'+escapeHtml(r.word)+'</strong><small>'+escapeHtml(r.pronunciation)+'</small></div>'+
      '<div class="tag-row"><span class="micro-tag">'+r.category+'</span><span class="micro-tag">'+r.syllables+' Silben</span><span class="micro-tag">'+r.kind+'</span></div>'+
      '<div><button class="icon-btn speak-result" data-word="'+escapeAttr(r.word)+'" aria-label="Aussprache">♫</button> <button class="favorite-btn '+(fav?"active":"")+'" data-fav="'+escapeAttr(r.word)+'" aria-label="Favorit">♥</button></div>'+
      '</article>';
  }).join("");
}
$("#rhymeResults").addEventListener("click",e=>{
  const speak=e.target.closest(".speak-result");if(speak)speakWord(speak.dataset.word);
  const fav=e.target.closest("[data-fav]");if(fav){
    const w=fav.dataset.fav;state.favorites=state.favorites.includes(w)?state.favorites.filter(x=>x!==w):[...state.favorites,w];save();renderRhymes();toast(state.favorites.includes(w)?"Zu Favoriten hinzugefügt":"Aus Favoriten entfernt");
  }
});
$("#speakQuery").addEventListener("click",()=>speakWord(state.currentQuery));
$$(".speak-btn").forEach(b=>b.addEventListener("click",()=>speakWord(b.dataset.speak)));
function speakWord(text){
  if(!("speechSynthesis" in window)){toast("Aussprache wird von diesem Browser nicht unterstützt.");return}
  speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.lang="de-DE";u.rate=.88;speechSynthesis.speak(u);
}

const submitDialog=$("#submitDialog");
$("#openSubmit").addEventListener("click",()=>submitDialog.showModal());
$("#submitRhymeForm").addEventListener("submit",e=>{
  e.preventDefault();
  const source=$("#submitSource").value.trim(),target=$("#submitTarget").value.trim();
  if(!source||!target)return;
  state.submissions.unshift({id:"u"+Date.now(),source,target,category:$("#submitCategory").value,syllables:$("#submitSyllables").value,pronunciation:$("#submitPronunciation").value.trim()||"Noch nicht angegeben",status:"pending",user:"@hosseinflow",age:"gerade eben",mine:true});
  state.points+=3;save();updatePoints();submitDialog.close();e.target.reset();renderCommunity();toast("+3 Punkte. Dein Reim wartet auf einen Test.");
});

$$("[data-community-tab]").forEach(b=>b.addEventListener("click",()=>{
  const tab=b.dataset.communityTab;
  $$("[data-community-tab]").forEach(x=>x.classList.toggle("active",x===b));
  $$(".community-tab").forEach(x=>x.classList.toggle("active",x.id===(tab==="feed"?"communityFeed":"testerQueue")));
}));
function submissionMarkup(s,tester=false){
  return '<article class="sticker-card submission-card">'+
    '<div><div class="submission-pair"><span>'+escapeHtml(s.source)+'</span><span class="arrow-pill">→</span><span>'+escapeHtml(s.target)+'</span></div>'+
    '<div class="submission-meta"><span class="micro-tag">'+s.category+'</span><span class="micro-tag">'+s.syllables+' Silben</span><span class="micro-tag">'+escapeHtml(s.pronunciation)+'</span><span class="micro-tag">'+s.user+' · '+s.age+'</span></div></div>'+
    (tester?'<div class="review-actions"><button class="approve-btn" data-review="accept" data-id="'+s.id+'">✓ Passt</button><button class="reject-btn" data-review="reject" data-id="'+s.id+'">× Nein</button></div>':'<span class="status-pill '+(s.status==="accepted"?"mint-bg":"")+'">'+(s.status==="accepted"?"BESTÄTIGT":"IM TEST")+'</span>')+
    '</article>';
}
function renderCommunity(){
  $("#communityFeed").innerHTML=state.submissions.slice(0,8).map(s=>submissionMarkup(s,false)).join("");
  const pending=state.submissions.filter(s=>s.status==="pending");
  $("#testerQueue").innerHTML=pending.length?pending.map(s=>submissionMarkup(s,true)).join(""):'<div class="empty-state">Aktuell gibt es keine offenen Reime zum Testen.</div>';
}
$("#testerQueue").addEventListener("click",e=>{
  const b=e.target.closest("[data-review]");if(!b)return;
  const s=state.submissions.find(x=>x.id===b.dataset.id);if(!s)return;
  s.status=b.dataset.review==="accept"?"accepted":"rejected";
  state.points+=b.dataset.review==="accept"?5:2;save();updatePoints();renderCommunity();toast(b.dataset.review==="accept"?"+5 Punkte für den Test":"+2 Punkte für den Test");
});

const beatDialog=$("#beatDialog");
$("#openBeatUpload").addEventListener("click",()=>beatDialog.showModal());
$("#beatUploadForm").addEventListener("submit",e=>{
  e.preventDefault();const file=$("#beatFile").files[0];
  state.beats.unshift({id:"u"+Date.now(),title:$("#beatTitle").value.trim(),producer:"Hossein Flow",type:$("#beatType").value,bpm:Number($("#beatBpm").value),license:$("#beatLicense").value,art:"art-violet",plays:"neu",audio:file?URL.createObjectURL(file):null});
  beatDialog.close();e.target.reset();renderBeats();toast("Upload zur Testansicht hinzugefügt.");
});
$("#beatFilters").addEventListener("click",e=>{const b=e.target.closest("button");if(!b)return;state.beatFilter=b.dataset.beatFilter;$$("#beatFilters button").forEach(x=>x.classList.toggle("active",x===b));renderBeats()});
$("#beatSearch").addEventListener("input",renderBeats);
function renderBeats(){
  const term=normalize($("#beatSearch")?.value||"");
  const rows=state.beats.filter(b=>(state.beatFilter==="Alle"||b.type===state.beatFilter)&&(!term||normalize(b.title+" "+b.producer).includes(term)));
  $("#beatGrid").innerHTML=rows.map(b=>'<article class="sticker-card beat-card"><div class="beat-art '+b.art+'"><button class="play-btn" data-play="'+b.id+'" aria-label="Abspielen">▶</button></div><div class="beat-info"><h3>'+escapeHtml(b.title)+'</h3><div class="beat-meta"><span class="micro-tag">'+b.type+'</span><span class="micro-tag">'+b.bpm+' BPM</span></div><div class="beat-footer"><span>von '+escapeHtml(b.producer)+'</span><span class="license-chip">'+escapeHtml(b.license)+'</span></div></div></article>').join("");
}
$("#beatGrid").addEventListener("click",e=>{
  const b=e.target.closest("[data-play]");if(!b)return;const beat=state.beats.find(x=>x.id===b.dataset.play);
  if(beat?.audio){if(window.activeAudio)window.activeAudio.pause();window.activeAudio=new Audio(beat.audio);window.activeAudio.play();b.textContent="❚❚";window.activeAudio.onended=()=>b.textContent="▶";}else toast("Audio Vorschau wird in der nächsten Backend Phase angebunden.");
});

function renderProfile(){
  const accepted=state.submissions.filter(s=>s.status==="accepted").length+6;$("#acceptedCount").textContent=accepted;
  const mine=state.submissions.filter(s=>s.mine).slice(0,5);
  $("#profileActivity").innerHTML=mine.length?mine.map(s=>'<div class="activity-row"><strong>'+escapeHtml(s.source)+' → '+escapeHtml(s.target)+'</strong><span>'+(s.status==="accepted"?"bestätigt":"im Test")+'</span></div>').join(""):'<div class="empty-state">Noch keine eigenen Beiträge in diesem Browser.</div>';
}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function escapeAttr(s){return escapeHtml(s).replace(/"/g,"&quot;")}

updatePoints();renderRhymes();renderCommunity();renderBeats();renderProfile();
