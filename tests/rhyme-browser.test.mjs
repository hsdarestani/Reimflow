import {chromium} from "playwright";
import {spawn} from "node:child_process";
import assert from "node:assert/strict";
const server=spawn("python3",["-m","http.server","8195","--bind","127.0.0.1"],{stdio:"ignore"});
const delay=ms=>new Promise(r=>setTimeout(r,ms));
let browser;
try{
  await delay(500);
  browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
  for(const viewport of [{width:1280,height:850},{width:390,height:844}]){
    const context=await browser.newContext({viewport,baseURL:"http://127.0.0.1:8195"});
    const page=await context.newPage(),errors=[];
    page.on("pageerror",e=>errors.push(e.message));
    let tries=0;
    await page.route("**/api/rhymes",async route=>{
      tries++;
      if(tries===1){
        return route.fulfill({status:502,contentType:"application/json",
          body:JSON.stringify({error:"AI_TIMEOUT",message:"Die KI-Reimsuche ist vorübergehend nicht erreichbar."})});
      }
      return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({
        ok:true,engine:"ai_phonetic",cached:false,
        analysis:{input:"Blue Talisman",interpreted_as:"Blue Talisman",pronunciation:"",ipa:"",syllables:4,language:"Englisch",correction:null,note:""},
        rhymes:[{word:"sample",category:"Nomen",syllables:2,pronunciation:"",ipa:"",score:66,confidence:60,register:"Englisch/Code-Switch",kind:"Near Rhyme",explanation:"Test response, not real rhyme"}]
      })});
    });
    await page.goto("/",{waitUntil:"domcontentloaded"});
    const nav=viewport.width<600?".mobile-nav [data-go='rhymes']":".desktop-nav [data-go='rhymes']";
    await page.locator(nav).click();
    await page.locator("#rhymeQuery").fill("Blue Talisman");
    await page.locator("#rhymeSearchForm button[type='submit']").click();
    const note=page.locator(".rhyme-offline-note");
    await note.waitFor({state:"visible",timeout:8500});
    assert.match(await note.innerText(),/ohne KI-Prüfung/);
    assert.ok(await page.locator(".rhyme-card").count()>=3,
      "A phrase with the suffix Talisman should have real dictionary-word suggestions");
    assert.match(await page.locator(".rhyme-card .ai-chip").first().innerText(),/IDEE/);
    assert.ok(!(await page.locator("#rhymeResults").innerText()).includes("Die Reimsuche konnte nicht geladen werden."));
    await page.locator("#retryOnlineSearch").click();
    await page.locator(".rhyme-card .ai-chip").getByText("KI").first().waitFor({timeout:8500});
    assert.equal(await note.count(),0,"Offline caveat must disappear for live AI success");
    assert.equal(await page.locator(".rhyme-card").count(),1);
    assert.equal(tries,2);
    assert.deepEqual(errors,[],JSON.stringify({viewport:viewport.width,errors}));
    console.log(viewport.width+"px Blue Talisman failed API -> honest offline words -> retry AI: PASSED");
    await context.close();
  }
}finally{
  await browser?.close();
  server.kill("SIGTERM");
}
