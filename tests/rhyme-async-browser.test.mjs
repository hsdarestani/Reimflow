import {chromium} from "playwright";
import {spawn} from "node:child_process";
import assert from "node:assert/strict";
const server=spawn("python3",["-m","http.server","8196","--bind","127.0.0.1"],{stdio:"ignore"});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let browser;
try{
 await sleep(500);
 browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
 for(const width of [390,1280]){
  const page=await browser.newPage({viewport:{width,height:844},baseURL:"http://127.0.0.1:8196"});
  const errors=[];page.on("pageerror",e=>errors.push(e.message));
  let poll=0,failNext=false;
  const jobId="jude-bellingham-test-abcdefghijklmnop";
  await page.route("**/api/rhymes",async route=>{
   const req=route.request().postDataJSON();
   assert.equal(req.query,failNext?"Bad Retry QA":"Jude Bellingham");
   await route.fulfill({status:202,contentType:"application/json",
    body:JSON.stringify({ok:true,pending:true,stage:"queued",job_id:jobId,poll_after_ms:80})});
  });
  await page.route("**/api/rhymes/jobs/**",async route=>{
   poll++;
   if(failNext)return route.fulfill({status:504,contentType:"application/json",
     body:JSON.stringify({error:"AI_TIMEOUT",message:"KI benötigt länger. Bitte erneut versuchen."})});
   if(poll<3)return route.fulfill({status:202,contentType:"application/json",
     body:JSON.stringify({ok:true,pending:true,stage:poll===1?"generation":"review",job_id:jobId,poll_after_ms:80})});
   return route.fulfill({status:200,contentType:"application/json",
     body:JSON.stringify({ok:true,quality_reviewed:true,engine:"ai_phonetic",
       analysis:{input:"Jude Bellingham",interpreted_as:"Jude Bellingham",syllables:5,language:"Englisch"},
       rhymes:[{word:"Telegramm",pronunciation:"",ipa:"",syllables:3,
        category:"Nomen",strength:"brauchbar",register:"Standard",kind:"Near Rhyme",
        score:0,confidence:0,scope:"end_word",explanation:"Test reviewed response"}]})});
  });
  await page.goto("/",{waitUntil:"domcontentloaded"});
  await page.locator(width<600?".mobile-nav [data-go='rhymes']":".desktop-nav [data-go='rhymes']").click();
  await page.locator("#rhymeQuery").fill("Jude Bellingham");
  await page.locator("#rhymeSearchForm button[type=submit]").click();
  await page.locator(".rhyme-card .rhyme-word").getByText("Telegramm").waitFor({timeout:12000});
  assert.equal(await page.locator("#resultsCount").innerText(),"1 Treffer");
  assert(poll>=3);
  assert.deepEqual(errors,[]);
  failNext=true;poll=0;
  await page.locator("#rhymeQuery").fill("Bad Retry QA");
  await page.locator("#rhymeSearchForm button[type=submit]").click();
  await page.locator(".search-empty.error").waitFor({timeout:10000});
  assert.match(await page.locator("#resultsCount").innerText(),/fehlgeschlagen/i);
  assert.equal(await page.getByText("Ersatzsuche aktiv").count(),0);
  assert.deepEqual(errors,[]);
  console.log("Async reviewed search + truthful timeout errors: "+width+"px PASSED");
  await page.close();
 }
}finally{await browser?.close();server.kill("SIGTERM")}
