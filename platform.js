/* Real Reimflow community client. No fake activity or paid entitlements. */
(function(){
"use strict";
const $=(s,root=document)=>root.querySelector(s);
const $$=(s,root=document)=>[...root.querySelectorAll(s)];
const esc=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const app={user:null,feed:[],queue:[],beats:[],leaders:[],scores:[],mine:[],favorites:[],ready:false,filter:"Alle"};
const msg=x=>{const el=$("#toast");if(!el)return;el.textContent=x;el.classList.add("show");clearTimeout(window.platformToast);window.platformToast=setTimeout(()=>el.classList.remove("show"),4000)};
async function request(path,payload){
 const multipart=payload instanceof FormData;
 const opt={method:"POST",credentials:"same-origin",headers:{"X-Reimflow-Client":"1"}};
 if(multipart)opt.body=payload;else {opt.headers["Content-Type"]="application/json";opt.body=JSON.stringify(payload||{})}
 let response;try{response=await fetch("/api/platform/"+path,opt)}catch{throw Error("Verbindung fehlgeschlagen.")}
 let data;try{data=await response.json()}catch{throw Error("Ungültige Serverantwort.")}
 if(!response.ok)throw Error(data.message||({AUTH_REQUIRED:"Bitte anmelden.",SELF_REVIEW_FORBIDDEN:"Eigene Beiträge können nicht geprüft werden.",TESTER_REQUIRED:"Nur für bestätigte Tester.",BAD_CREDENTIALS:"Anmeldedaten nicht korrekt.",ACCOUNT_EXISTS:"Nutzername oder E-Mail schon vergeben.",ALREADY_REVIEWED:"Dieser Beitrag wurde bereits geprüft.",RATE_LIMIT:"Zu viele Anfragen. Bitte später erneut versuchen."}[data.error])||"Aktion fehlgeschlagen: "+data.error);
 return data;
}
async function refresh(){
 const response=await fetch("/api/platform/bootstrap",{credentials:"same-origin",cache:"no-store"});
 if(!response.ok)throw Error("Community Daten nicht verfügbar.");
 const data=await response.json();if(!data.ok)throw Error("Serverantwort ungültig.");
 Object.assign(app,data,{ready:true});
 if(typeof state!=="undefined"){state.favorites=app.favorites.slice();state.points=app.user?.points||0;if(typeof updatePoints==="function")updatePoints();if(typeof renderRhymes==="function")renderRhymes();}
 renderCommunity();renderBeats();renderProfile();renderLoginState();
}
function authNeeded(){if(app.user)return false;openAuth();msg("Bitte zuerst anmelden.");return true}
function openAuth(register=false){const el=$("#authDialog");if(el&&!el.open)el.showModal();selectTab(register?"register":"login")}
function selectTab(tab){$$("#authDialog [data-auth-tab]").forEach(el=>el.classList.toggle("active",el.dataset.authTab===tab));$("#loginForm").hidden=tab!=="login";$("#registerForm").hidden=tab!=="register";$("#authMessage").textContent=""}
function renderLoginState(){
 const status=$("#accountStatus");if(status)status.textContent=app.user?"@"+app.user.username:"Anmelden";
 const button=$("#profileEditButton");if(button)button.textContent=app.user?"Profil bearbeiten":"Anmelden";
 const tester=$('[data-community-tab="tester"]');if(tester)tester.hidden=!["tester","admin"].includes(app.user?.role);
 if(tester?.hidden && $("#testerQueue")?.classList.contains("active"))$('[data-community-tab="feed"]')?.click();
}
function renderCommunity(){
 const container=$("#communityFeed");if(!container)return;
 if(!app.ready){container.textContent="Community wird geladen ...";return}
 container.innerHTML=app.feed.length?app.feed.map(x=>'<article class="sticker-card submission-card"><div><div class="submission-pair"><span>'+esc(x.source)+'</span><span class="arrow-pill">→</span><span>'+esc(x.target)+'</span></div><div class="submission-meta"><span class="micro-tag">'+esc(x.category)+'</span><span class="micro-tag">'+esc(x.syllables)+' Silben</span><span class="micro-tag">'+esc(x.pronunciation)+'</span><span class="micro-tag">@'+esc(x.username)+'</span></div></div><div><span class="status-pill '+(x.status==="accepted"?"mint-bg":"")+'">'+(x.status==="accepted"?"BESTÄTIGT":"IN PRÜFUNG")+'</span><button class="text-link" data-report-kind="submission" data-report-id="'+x.id+'">Melden</button>'+(app.user&&app.user.id!==x.author_id?'<button class="text-link" data-block-user="'+x.author_id+'">Blockieren</button>':"")+'</div></article>').join(""):'<div class="empty-state">Noch keine Community Beiträge. Sei der Erste!</div>';
 const queue=$("#testerQueue");
 if(queue)queue.innerHTML=["tester","admin"].includes(app.user?.role)?app.queue.map(x=>'<article class="sticker-card submission-card"><div><div class="submission-pair"><span>'+esc(x.source)+'</span> → <span>'+esc(x.target)+'</span></div><div class="submission-meta"><span class="micro-tag">@'+esc(x.username)+'</span></div></div>'+(x.author_id===app.user.id?'<small>Eigener Beitrag</small>':'<div class="review-actions"><button class="ai-check-btn" data-ai-review="'+x.id+'">✦ KI Prüfung</button><button class="approve-btn" data-decision="accepted" data-id="'+x.id+'">✓ Passt</button><button class="reject-btn" data-decision="rejected" data-id="'+x.id+'">× Nein</button></div>')+'<div class="ai-review-slot" data-ai-result="'+x.id+'"></div></article>').join("")||'<div class="empty-state">Keine offenen Reime.</div>':'<div class="empty-state">Nur für bestätigte Tester.</div>';
 const leaders=$(".leaderboard ol");
 if(leaders)leaders.innerHTML=app.leaders.length?app.leaders.map(x=>'<li><span class="avatar violet-bg">'+esc(x.display_name.slice(0,2).toUpperCase())+'</span><div><strong>'+esc(x.display_name)+'</strong><small>@'+esc(x.username)+'</small></div><b>'+Number(x.points)+'</b></li>').join(""):'<li>Hier erscheinen echte Punkte der Mitglieder.</li>';
}
function renderBeats(){
 const grid=$("#beatGrid");if(!grid)return;
 const text=($("#beatSearch")?.value||"").toLowerCase().trim();
 const items=app.beats.filter(b=>(app.filter==="Alle"||b.kind===app.filter)&&(!text||(b.title+" "+b.display_name).toLowerCase().includes(text)));
 grid.innerHTML=items.length?items.map(b=>'<article class="sticker-card beat-card"><div class="beat-art art-violet"><button class="play-btn" data-play="'+b.id+'" type="button" aria-label="Audio abspielen">▶</button></div><div class="beat-info"><h3>'+esc(b.title)+'</h3><div class="beat-meta"><span class="micro-tag">'+esc(b.kind)+'</span><span class="micro-tag">'+b.bpm+' BPM</span></div><div class="beat-footer"><span>von '+esc(b.display_name)+'</span><span class="license-chip">'+esc(b.license)+'</span></div>'+(b.hidden?'<small>Wartet auf Freigabe</small>':"")+'<div class="platform-actions"><button class="text-link" data-report-kind="beat" data-report-id="'+b.id+'">Melden</button>'+(app.user&&app.user.id!==b.author_id?'<button class="text-link" data-block-user="'+b.author_id+'">Blockieren</button>':"")+(app.user&&(app.user.id===b.author_id||app.user.role==="admin")?'<button class="text-link" data-delete-beat="'+b.id+'">Löschen</button>':"")+'</div></div></article>').join(""):'<div class="empty-state">Noch keine Audiodateien. Lade den ersten Beat hoch.</div>';
}
function renderProfile(){
 if(!app.ready)return;const u=app.user,profile=$(".profile-copy");if(!profile)return;
 profile.querySelector("h1").textContent=u?.display_name||"Dein Reimflow Profil";
 profile.querySelector("p").textContent=u?"@"+u.username+(u.bio?" · "+u.bio:""):"Melde dich an und gestalte dein Profil.";
 profile.querySelector(".status-pill").textContent=u?.persona==="producer"?"Producer":u?"Rapper":"Gast";
 $(".profile-avatar").textContent=u?.display_name.slice(0,2).toUpperCase()||"RF";
 $("#acceptedCount").textContent=app.total_accepted||0;
 const stats=$$(".stats-grid .stat-card strong");
 if(stats[2])stats[2].textContent=app.total_beats||0;
 if(stats[3])stats[3].textContent="–";
 $("#profileActivity").innerHTML=app.mine.length?app.mine.map(s=>'<div class="activity-row"><strong>'+esc(s.source)+' → '+esc(s.target)+'</strong><span>'+esc(s.status)+'</span></div>').join(""):'<div class="empty-state">Noch keine eigenen Beiträge.</div>';
 $("#myFavoriteList").textContent=app.favorites.join(" · ")||"Noch keine Favoriten.";
 $("#myScoreList").textContent=app.scores.map(s=>s.bpm+" BPM ("+s.mode+"): "+s.best+"/100").join(" · ")||"Noch kein gespeichertes Spiel.";
 $("#profileLogout").hidden=!u;$("#profileDelete").hidden=!u;
 $("#accountExport").hidden=!u;
 $("#blockedMembers").innerHTML=(app.blocked||[]).map(m=>'<div class="activity-row"><strong>@'+esc(m.username)+'</strong><button class="secondary-btn compact" data-unblock="'+m.id+'">Freigeben</button></div>').join("")||'<p class="tiny-note">Keine blockierten Mitglieder.</p>';
 renderAdmin();
}

function renderAdmin(){
 const panel=$("#moderationPanel");if(!panel)return;
 panel.hidden=app.user?.role!=="admin";
 if(panel.hidden)return;
 $("#adminPendingAudio").innerHTML="<h4>Audio Freigaben</h4>"+((app.pending_beats||[]).map(b=>
  '<div class="activity-row"><strong>'+esc(b.title)+' · @'+esc(b.username)+'</strong><audio controls preload="none" src="/api/platform/media/'+b.id+'"></audio><button class="secondary-btn compact" data-admin-kind="beat" data-admin-id="'+b.id+'" data-admin-decision="approve">Freigeben</button><button class="secondary-btn compact" data-admin-kind="beat" data-admin-id="'+b.id+'" data-admin-decision="hide">Ablehnen</button></div>').join("")||"<p>Keine offenen Uploads.</p>");
 $("#adminReports").innerHTML="<h4>Offene Meldungen</h4>"+((app.reports||[]).map(r=>
  '<div class="activity-row"><span>'+esc(r.kind)+" #"+r.content_id+": "+esc(r.reason)+'</span><button class="secondary-btn compact" data-admin-kind="'+esc(r.kind)+'" data-admin-id="'+r.content_id+'" data-admin-decision="hide">Ausblenden & schließen</button></div>').join("")||"<p>Keine offenen Meldungen.</p>");
 $("#adminMembers").innerHTML="<h4>Tester verwalten</h4>"+((app.members||[]).map(m=>
  '<div class="activity-row"><span>@'+esc(m.username)+" ("+esc(m.role)+')</span>'+(m.role==="admin"?"":'<button class="secondary-btn compact" data-role-user="'+m.id+'" data-role="'+(m.role==="tester"?"member":"tester")+'">'+(m.role==="tester"?"Tester entfernen":"Als Tester freigeben")+'</button>')+'</div>').join("")||"<p>Keine Mitglieder.</p>");
}

async function toggleFavorite(word){if(authNeeded())return;try{await request("favorites",{word,remove:app.favorites.includes(word)});await refresh()}catch(e){msg(e.message)}}
async function saveScore(result){if(!app.user||!result)return;try{await request("scores",{score:result.score,bpm:result.bpm,mode:result.mode});await refresh()}catch(e){msg("Ergebnis nur lokal gespeichert: "+e.message)}}
$$("#authDialog [data-auth-tab]").forEach(b=>b.addEventListener("click",()=>selectTab(b.dataset.authTab)));
$("#loginForm")?.addEventListener("submit",async e=>{e.preventDefault();const f=e.currentTarget,b=f.querySelector('button[type="submit"]');b.disabled=true;try{await request("login",{identity:f.elements.identity.value,password:f.elements.password.value});await refresh();$("#authDialog").close();f.reset();msg("Willkommen zurück!")}catch(err){$("#authMessage").textContent=err.message}finally{b.disabled=false}});
$("#registerForm")?.addEventListener("submit",async e=>{e.preventDefault();const f=e.currentTarget,b=f.querySelector('button[type="submit"]');b.disabled=true;try{await request("register",{username:f.elements.username.value,email:f.elements.email.value,password:f.elements.password.value,persona:f.elements.persona.value});await refresh();$("#authDialog").close();f.reset();msg("Konto erstellt!")}catch(err){$("#authMessage").textContent=err.message}finally{b.disabled=false}});
$("#profileEditButton")?.addEventListener("click",()=>{if(authNeeded())return;$("#editDisplayName").value=app.user.display_name;$("#editBio").value=app.user.bio;$("#editPersona").value=app.user.persona;$("#profileDialog").showModal()});
$("#profileForm")?.addEventListener("submit",async e=>{e.preventDefault();try{await request("profile",{display_name:$("#editDisplayName").value,bio:$("#editBio").value,persona:$("#editPersona").value});$("#profileDialog").close();await refresh();msg("Profil gespeichert.")}catch(err){msg(err.message)}});
$("#changePasswordForm")?.addEventListener("submit",async e=>{e.preventDefault();const f=e.currentTarget;try{await request("password",{current_password:f.elements.current_password.value,new_password:f.elements.new_password.value});f.reset();$("#profileDialog").close();await refresh();msg("Passwort geändert. Bitte erneut anmelden.")}catch(err){msg(err.message)}});
$("#profileLogout")?.addEventListener("click",async()=>{try{await request("logout",{});await refresh();msg("Abgemeldet.")}catch(err){msg(err.message)}});
$("#profileDelete")?.addEventListener("click",async()=>{if(!app.user||!confirm("Konto und alle Beiträge und Uploads endgültig löschen?"))return;const password=prompt("Passwort zur Bestätigung eingeben:");if(password===null)return;try{await request("delete-account",{password});await refresh();msg("Konto gelöscht.")}catch(e){msg(e.message)}});
$("#openSubmit")?.addEventListener("click",()=>{if(!authNeeded())$("#submitDialog").showModal()});
$("#submitRhymeForm")?.addEventListener("submit",async e=>{e.preventDefault();if(authNeeded())return;const f=e.currentTarget,b=f.querySelector('button[type="submit"]');b.disabled=true;try{await request("submissions",{source:$("#submitSource").value,target:$("#submitTarget").value,category:$("#submitCategory").value,syllables:$("#submitSyllables").value,pronunciation:$("#submitPronunciation").value});$("#submitDialog").close();f.reset();await refresh();msg("Dein Beitrag wartet auf eine Prüfung.")}catch(err){msg(err.message)}finally{b.disabled=false}});
$("#testerQueue")?.addEventListener("click",async e=>{const b=e.target.closest("[data-decision],[data-ai-review]");if(!b||!["tester","admin"].includes(app.user?.role))return;b.disabled=true;const id=Number(b.dataset.id||b.dataset.aiReview);try{if(b.dataset.aiReview){const item=app.queue.find(row=>row.id===id);if(!item)return;const res=await fetch("/api/validate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({source:item.source,target:item.target})});const data=await res.json();if(!res.ok)throw Error(data.message||"KI Prüfung fehlgeschlagen.");$('[data-ai-result="'+id+'"]').textContent="KI: "+data.verdict+" · "+data.explanation}else{await request("review",{id,decision:b.dataset.decision});await refresh();msg("Prüfung gespeichert.")}}catch(err){msg(err.message)}finally{b.disabled=false}});
$("#openBeatUpload")?.addEventListener("click",()=>{if(!authNeeded())$("#beatDialog").showModal()});
$("#beatUploadForm")?.addEventListener("submit",async e=>{e.preventDefault();if(authNeeded())return;const f=e.currentTarget,file=$("#beatFile").files[0];if(!file||file.size>12*1024*1024){msg("Audio Datei bis 12 MB auswählen.");return}const b=f.querySelector('button[type="submit"]'),d=new FormData();b.disabled=true;d.set("audio",file);d.set("title",$("#beatTitle").value);d.set("kind",$("#beatType").value);d.set("bpm",$("#beatBpm").value);d.set("license",$("#beatLicense").value);d.set("rights",$("#beatRights").checked?"yes":"no");try{await request("beats",d);$("#beatDialog").close();f.reset();await refresh();msg("Audio dauerhaft hochgeladen.")}catch(err){msg(err.message)}finally{b.disabled=false}});
$("#beatFilters")?.addEventListener("click",e=>{const b=e.target.closest("[data-beat-filter]");if(!b)return;app.filter=b.dataset.beatFilter;$$("#beatFilters button").forEach(x=>x.classList.toggle("active",x===b));renderBeats()});
$("#beatSearch")?.addEventListener("input",renderBeats);
let audio=null,playButton=null;
$("#beatGrid")?.addEventListener("click",async e=>{const b=e.target.closest("[data-play]");if(b){if(audio)audio.pause();if(playButton)playButton.textContent="▶";audio=new Audio("/api/platform/media/"+Number(b.dataset.play));playButton=b;audio.onended=()=>{b.textContent="▶";audio=null};audio.onerror=()=>msg("Audio nicht verfügbar.");try{await audio.play();b.textContent="❚❚"}catch{msg("Audio kann nicht abgespielt werden.")}return}const del=e.target.closest("[data-delete-beat]");if(del&&confirm("Diesen Upload endgültig löschen?"))try{await request("delete-beat",{id:Number(del.dataset.deleteBeat)});await refresh();msg("Upload gelöscht.")}catch(err){msg(err.message)}});
$("#blockedMembers")?.addEventListener("click",async e=>{const b=e.target.closest("[data-unblock]");if(!b)return;try{await request("block-user",{user_id:Number(b.dataset.unblock),remove:true});await refresh();msg("Mitglied freigegeben.")}catch(err){msg(err.message)}});
$("#moderationPanel")?.addEventListener("click",async e=>{const role=e.target.closest("[data-role-user]");const action=e.target.closest("[data-admin-kind]");if(!role&&!action)return;try{if(role)await request("set-tester",{user_id:Number(role.dataset.roleUser),role:role.dataset.role});else await request("moderate",{kind:action.dataset.adminKind,id:Number(action.dataset.adminId),decision:action.dataset.adminDecision});await refresh();msg("Moderation gespeichert.")}catch(err){msg(err.message)}});
function report(kind,id){if(authNeeded())return;$("#reportKind").value=kind;$("#reportId").value=id;$("#reportDialog").showModal()}
["#communityFeed","#beatGrid"].forEach(s=>$(s)?.addEventListener("click",async e=>{const block=e.target.closest("[data-block-user]");if(block){if(authNeeded())return;if(!confirm("Inhalte dieses Mitglieds für dich ausblenden?"))return;try{await request("block-user",{user_id:Number(block.dataset.blockUser)});await refresh();msg("Mitglied blockiert.")}catch(err){msg(err.message)}return;}const el=e.target.closest("[data-report-kind]");if(el)report(el.dataset.reportKind,el.dataset.reportId)}));
$("#reportForm")?.addEventListener("submit",async e=>{e.preventDefault();try{await request("report",{kind:$("#reportKind").value,id:Number($("#reportId").value),reason:$("#reportReason").value});$("#reportDialog").close();e.currentTarget.reset();msg("Meldung gesendet.")}catch(err){msg(err.message)}});
const premium=$("#premiumTestButton");if(premium){premium.disabled=true;premium.textContent="Bald verfügbar";}
$$("#communityFeed [data-community-tab]").forEach(b=>b.addEventListener("click",()=>{}));
$$("[data-community-tab]").forEach(b=>b.addEventListener("click",()=>{$$("[data-community-tab]").forEach(x=>x.classList.toggle("active",x===b));$$(".community-tab").forEach(x=>x.classList.toggle("active",x.id===(b.dataset.communityTab==="feed"?"communityFeed":"testerQueue")))}));
window.ReimflowPlatform={renderCommunity,renderBeats,renderProfile,toggleFavorite,saveScore,openAuth,refresh};
refresh().catch(err=>msg(err.message));
})();
