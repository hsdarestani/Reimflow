/* Hand-curated, transparently labeled short-list for common rhyme anchors.
 * These previews appear immediately while full phonetic AI validation runs.
 * Not auto-promoted as checked matches.
 */
(function(root){
  "use strict";
  const BANK={
    paper:{
      anchor:"paper",language:"Englisch",
      words:["caper","taper","scraper","shaper","vapor"],
      phrases:["blue vapor","true caper","clue shaper"],
      note:"Bei englischer Aussprache: paper /ˈpeɪpə(r)/. Einzelwörter reimen auf das Endwort; mehrteilige Ideen sind poetische Beispiele, keine festen Redewendungen."
    },
    ferrari:{
      anchor:"Ferrari",language:"Name / Italienisch",
      words:["Safari","Calamari","Atari"],
      phrases:[],
      note:"Nur Endwort-Ideen, nicht automatisch ein Reim auf die ganze Phrase."
    }
  };
  const lastWord=q=>(String(q||"").match(/[a-zA-ZäöüÄÖÜß]+/g)||[]).at(-1)?.toLocaleLowerCase("de-DE")||"";
  root.ReimflowRhymePreviews=Object.freeze({
    find(query){return BANK[lastWord(query)]||null},
    lastWord
  });
})(typeof window!=="undefined"?window:globalThis);
