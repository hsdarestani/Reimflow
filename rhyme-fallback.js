/* Genuine dictionary-word prompts when online rhyme AI is temporarily offline.
   These are UNVERIFIED suffix suggestions, NOT phonetic AI matches. */
(function(root){
  "use strict";
  const entry=(word,category,syllables,register="Standard")=>({word,category,syllables,register});
  const bank={
    an:[
      entry("Mann","Nomen",1),entry("Bann","Nomen",1),
      entry("kann","Verb",1),entry("dann","Sonstiges",1),
      entry("dran","Umgangssprache",1),entry("ran","Umgangssprache",1),
      entry("wann","Sonstiges",1),entry("Kran","Nomen",1),
      entry("Plan","Nomen",1),entry("Wahn","Nomen",1)
    ],
    in:[
      entry("Sinn","Nomen",1),entry("drin","Umgangssprache",1),
      entry("hin","Sonstiges",1),entry("Gewinn","Nomen",2),
      entry("Beginn","Nomen",2),entry("dahin","Sonstiges",2),
      entry("mittendrin","Umgangssprache",3),entry("Kinn","Nomen",1)
    ],
    ein:[
      entry("mein","Sonstiges",1),entry("dein","Sonstiges",1),entry("sein","Verb",1),
      entry("klein","Adjektiv",1),entry("rein","Sonstiges",1),entry("allein","Adjektiv",2)
    ],
    on:[
      entry("Ton","Nomen",1),entry("Sohn","Nomen",1),entry("Thron","Nomen",1),
      entry("Vision","Nomen",2),entry("Mission","Nomen",2),entry("Position","Nomen",3)
    ],
    aus:[
      entry("Haus","Nomen",1),entry("Maus","Nomen",1),
      entry("raus","Umgangssprache",1),entry("Applaus","Nomen",2),
      entry("daraus","Sonstiges",2),entry("hinaus","Sonstiges",2)
    ],
    acht:[
      entry("Nacht","Nomen",1),entry("Macht","Nomen",1),
      entry("Pracht","Nomen",1),entry("gebracht","Verb",2),
      entry("erwacht","Verb",2),entry("gedacht","Verb",2)
    ],
    icht:[
      entry("Licht","Nomen",1),entry("Sicht","Nomen",1),entry("nicht","Sonstiges",1),
      entry("Pflicht","Nomen",1),entry("Gesicht","Nomen",2),entry("Gewicht","Nomen",2)
    ],
    eit:[
      entry("Zeit","Nomen",1),entry("weit","Adjektiv",1),entry("bereit","Adjektiv",2),
      entry("zu zweit","Sonstiges",2),entry("Freiheit","Nomen",2),entry("Kleinigkeit","Nomen",4)
    ],
    ung:[
      entry("Schwung","Nomen",1),entry("Sprung","Nomen",1),
      entry("jung","Adjektiv",1),entry("Dschungel","Nomen",2)
    ],
    ing:[
      entry("Ring","Nomen",1),entry("Ding","Nomen",1),
      entry("King","Nomen",1,"Englisch/Code-Switch"),
      entry("Swing","Nomen",1,"Englisch/Code-Switch")
    ],
    ame:[
      entry("game","Nomen",1,"Englisch/Code-Switch"),entry("name","Nomen",1,"Englisch/Code-Switch"),
      entry("same","Adjektiv",1,"Englisch/Code-Switch"),
      entry("flame","Nomen",1,"Englisch/Code-Switch")
    ],
    ight:[
      entry("night","Nomen",1,"Englisch/Code-Switch"),
      entry("light","Nomen",1,"Englisch/Code-Switch"),
      entry("fight","Nomen",1,"Englisch/Code-Switch"),
      entry("right","Adjektiv",1,"Englisch/Code-Switch"),
      entry("bright","Adjektiv",1,"Englisch/Code-Switch")
    ]
  };
  const safeLast=query=>{
    const tokens=String(query||"").trim().match(/[a-zA-ZäöüÄÖÜß]+/g)||[];
    return tokens.length?tokens[tokens.length-1].toLocaleLowerCase("de-DE"):"";
  };
  function groupFor(token){
    if(/(?:talisman|mann|man|ann|an)$/.test(token))return "an";
    if(/ein$/.test(token))return "ein";
    if(/(?:inn|in)$/.test(token))return "in";
    if(/(?:aus|auss)$/.test(token))return "aus";
    if(/acht$/.test(token))return "acht";
    if(/icht$/.test(token))return "icht";
    if(/eit$/.test(token))return "eit";
    if(/ung$/.test(token))return "ung";
    if(/ing$/.test(token))return "ing";
    if(/ame$/.test(token))return "ame";
    if(/ight$/.test(token))return "ight";
    if(/on$/.test(token))return "on";
    return null;
  }
  function find(query,{category="Alle",syllables="Alle"}={}){
    const anchor=safeLast(query),group=groupFor(anchor);
    if(!group)return null;
    const items=(bank[group]||[]).filter(row=>{
      if(row.word.toLocaleLowerCase("de-DE")===anchor)return false;
      if(category!=="Alle"&&category!==row.category)return false;
      if(syllables!=="Alle"&&(syllables==="4+" ? row.syllables<4 : row.syllables!==Number(syllables)))return false;
      return true;
    });
    if(!items.length)return null;
    return {
      source:"offline_suffix",engine:"offline_suffix",
      analysis:{
        input:String(query).trim(),interpreted_as:String(query).trim(),
        pronunciation:"",ipa:"",syllables:0,language:"Ungeprüft",
        correction:null,
        note:"Nur ungeprüfte Wortideen mit ähnlicher Endung für „"+anchor+"“. Die tatsächliche Aussprache, Betonung und Reimqualität wurden nicht durch KI geprüft."
      },
      rhymes:items.slice(0,10).map((row,index)=>({
        ...row,pronunciation:"",ipa:"",
        score:Math.max(40,65-index*2),confidence:0,
        kind:"Near Rhyme",source:"offline_suffix",
        explanation:"Idee aufgrund ähnlicher Schreibendung zu „"+anchor+"“. Klang und Betonung bitte selbst prüfen."
      }))
    };
  }
  root.ReimflowOfflineRhymes=Object.freeze({find,safeLast,groupFor});
})(typeof window!=="undefined"?window:globalThis);
