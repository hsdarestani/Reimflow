import {readFileSync} from "node:fs";
import {runInNewContext} from "node:vm";
import assert from "node:assert/strict";

const code=readFileSync(new URL("../rhyme-fallback.js",import.meta.url),"utf8");
const ctx={};
runInNewContext(code,ctx,{filename:"rhyme-fallback.js"});
const finder=ctx.ReimflowOfflineRhymes;
assert.ok(finder);
const blue=finder.find("Blue Talisman");
assert.ok(blue&&blue.rhymes.length>=5);
assert.equal(blue.engine,"offline_suffix");
assert.equal(blue.analysis.interpreted_as,"Blue Talisman");
assert.equal(blue.analysis.ipa,"");
assert.match(blue.analysis.note,/ungeprüfte/);
for(const w of blue.rhymes) {
  assert.ok(w.word&&w.score<80);
  assert.equal(w.source,"offline_suffix");
  assert.equal(w.confidence,0);
  assert.notEqual(w.word.toLowerCase(),"talisman");
}
assert.equal(finder.find("xyqrspl"),null);
const nouns=finder.find("Blue Talisman",{category:"Nomen"});
assert.ok(nouns.rhymes.length>0&&nouns.rhymes.every(w=>w.category==="Nomen"));
assert.ok(finder.find("Blue Talisman",{category:"Verb",syllables:"4+"})===null);
assert.ok(finder.find("Sommernacht").rhymes.some(x=>x.word==="Macht"));
console.log("Offline suffix vocabulary respects filters, labels approximations and serves Blue Talisman.");
