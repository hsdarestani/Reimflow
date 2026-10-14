/* Reimflow Flow Challenge scoring. Pure, deterministic helpers shared by the game and CI. */
(function(root){
  "use strict";
  const BEATS=16;
  const COUNT_IN=4;
  const WINDOW_MS=190;
  function judgeOffset(offsetMs){
    const abs=Math.abs(Number(offsetMs));
    if(!Number.isFinite(abs)||abs>WINDOW_MS)return{kind:"miss",points:0,label:"MISS"};
    if(abs<=55)return{kind:"perfect",points:100,label:"PERFECT!"};
    if(abs<=115)return{kind:"good",points:Math.round(95-(abs-55)*.35),label:"GOOD!"};
    return{kind:"okay",points:Math.round(74-(abs-115)*.56),label:"OKAY"};
  }
  function rating(score){
    if(score>=93)return{title:"BEAT MONSTER",subtitle:"Du sitzt direkt auf dem Beat. 🔥"};
    if(score>=78)return{title:"FLOW RIDER",subtitle:"Stabiles Timing. Jetzt die nächsten Bars!"};
    if(score>=60)return{title:"RHYTHM ROOKIE",subtitle:"Du hast den Groove. Noch eine Runde!"};
    return{title:"KEEP THE FLOW",subtitle:"Übung macht den Flow. Versuch's erneut!"};
  }
  function scoreRound(hits){
    const events=Array.from({length:BEATS},(_,i)=>hits[i]||{kind:"miss",points:0});
    const total=events.reduce((a,e)=>a+(Number(e.points)||0),0);
    const score=Math.max(0,Math.min(100,Math.round(total/BEATS)));
    let combo=0,maxCombo=0;
    for(const e of events){
      combo=e.kind!=="miss"?combo+1:0;
      maxCombo=Math.max(maxCombo,combo);
    }
    return {score,perfect:events.filter(x=>x.kind==="perfect").length,good:events.filter(x=>x.kind==="good").length,
      okay:events.filter(x=>x.kind==="okay").length,miss:events.filter(x=>x.kind==="miss").length,maxCombo,...rating(score)};
  }
  root.ReimflowTiming=Object.freeze({BEATS,COUNT_IN,WINDOW_MS,judgeOffset,scoreRound,rating});
})(typeof window==="undefined"?globalThis:window);
