/* Hand-curated, transparently labeled short-list for common rhyme anchors.
 * These previews appear immediately while full phonetic AI validation runs.
 * Not auto-promoted as checked matches.
 */
(function(root){
  "use strict";
  const BANK={
    ferrari:{
      anchor:"Ferrari",language:"Name / Italienisch",
      words:["Safari","Kalamari"],
      phrases:[],
      note:"Nur deutsche Endwort-Ideen, nicht automatisch ein Reim auf die ganze Phrase."
    }
  };
  const lastWord=q=>(String(q||"").match(/[a-zA-ZäöüÄÖÜß]+/g)||[]).at(-1)?.toLocaleLowerCase("de-DE")||"";
  root.ReimflowRhymePreviews=Object.freeze({
    find(query){return BANK[lastWord(query)]||null},
    lastWord
  });
})(typeof window!=="undefined"?window:globalThis);
