import {chromium} from "playwright";
import {spawn} from "node:child_process";
import assert from "node:assert/strict";

const server=spawn("python3",["-m","http.server","8195","--bind","127.0.0.1"],{stdio:"ignore"});
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let browser;
try{
  await delay(500);
  browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
  for(const viewport of [{width:1280,height:850},{width:390,height:844}]){
    const context=await browser.newContext({viewport,baseURL:"http://127.0.0.1:8195"});
    const page=await context.newPage(),errors=[];
    page.on("pageerror",error=>errors.push(error.message));
    let tries=0;
    await page.route("**/api/rhymes",async route=>{
      tries++;
      const {query}=route.request().postDataJSON();
      if(query==="Blue Ferrari"){
        await delay(1100);
        return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({
          ok:true,engine:"ai_phonetic",quality_reviewed:true,
          analysis:{input:query,interpreted_as:query,pronunciation:"",ipa:"",syllables:4,language:"Englisch",correction:null,note:""},
          rhymes:[
            {word:"Auf Safari",category:"Sonstiges",syllables:4,pronunciation:"",ipa:"",score:0,confidence:0,strength:"brauchbar",scope:"phrase_variation",register:"Standard",german_valid:true,kind:"Phrase",explanation:"Deutsche Reimphrase"},
            {word:"Safari",category:"Nomen",syllables:3,pronunciation:"",ipa:"",score:0,confidence:0,strength:"stark",scope:"end_word",register:"Standard",german_valid:true,kind:"Near Rhyme",explanation:"Deutsches Lehnwort"},
            {word:"caper",category:"Nomen",syllables:2,pronunciation:"",ipa:"",score:0,confidence:0,strength:"stark",scope:"end_word",register:"Englisch/Code-Switch",german_valid:false,kind:"Near Rhyme",explanation:"Must be hidden"}
          ]
        })});
      }
      if(query==="Blue paper"){
        return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({
          ok:true,engine:"ai_phonetic",quality_reviewed:true,
          analysis:{input:query,interpreted_as:query,pronunciation:"",ipa:"",syllables:3,language:"Englisch",correction:null,note:""},
          rhymes:[{word:"shaper",category:"Nomen",syllables:2,pronunciation:"",ipa:"",score:0,confidence:0,strength:"stark",scope:"end_word",register:"Standard",kind:"Near Rhyme",explanation:"Unverified English"}]
        })});
      }
      if(tries===1){
        return route.fulfill({status:502,contentType:"application/json",
          body:JSON.stringify({error:"AI_TIMEOUT",message:"Die KI-Reimsuche ist vorübergehend nicht erreichbar."})});
      }
      return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({
        ok:true,engine:"ai_phonetic",cached:false,
        analysis:{input:query,interpreted_as:query,pronunciation:"",ipa:"",syllables:4,language:"Englisch",correction:null,note:""},
        quality_reviewed:true,rhymes:[{word:"Bann",category:"Nomen",syllables:1,pronunciation:"",ipa:"",score:0,confidence:0,strength:"brauchbar",scope:"end_word",register:"Standard",german_valid:true,kind:"Near Rhyme",explanation:"Geprüfter deutscher Reimanker"}]
      })});
    });
    await page.goto("/",{waitUntil:"domcontentloaded"});
    const nav=viewport.width<600?".mobile-nav [data-go='rhymes']":".desktop-nav [data-go='rhymes']";
    await page.locator(nav).click();
    await page.locator("#rhymeQuery").fill("Blue Talisman");
    await page.locator("#rhymeSearchForm button[type='submit']").click();
    const message=page.locator(".search-empty.error");
    await message.waitFor({state:"visible",timeout:8500});
    assert.match(await message.innerText(),/nicht geladen werden/i);
    assert.equal(await page.locator(".rhyme-card").count(),0);
    assert.equal(await page.locator(".rhyme-offline-note").count(),0);
    await page.locator("#retrySearch").click();
    await page.locator(".rhyme-card .ai-chip").getByText("KI").first().waitFor({timeout:8500});
    assert.equal(await message.count(),0);
    assert.equal(await page.locator(".rhyme-card").count(),1);
    assert.equal(tries,2);

    // German-only hand-curated preview is displayed while review runs.
    await page.locator("#rhymeQuery").fill("Blue Ferrari");
    await page.locator("#rhymeSearchForm button[type='submit']").click();
    const preview=page.locator(".rhyme-preview");
    await preview.waitFor({state:"visible",timeout:1000});
    assert.equal(await page.locator("#onlyRhymeAnchor").isVisible(),true);
    assert.match(await page.locator("#onlyRhymeAnchor").innerText(),/Ferrari/);
    assert.match(await preview.innerText(),/Safari|Kalamari/);
    assert.doesNotMatch(await preview.innerText(),/caper|scraper|vapor/);
    await page.locator(".rhyme-group-title").first().waitFor({state:"visible",timeout:6500});
    assert.deepEqual(await page.locator(".rhyme-group-title").allTextContents(),["Kreative mehrteilige Reime","Reime auf das letzte Wort"]);
    assert.equal(await page.locator(".rhyme-card").count(),2,"English result must not render even with a forged API payload");
    assert.equal(await preview.count(),0);

    // Legacy responses without verified German language labels must fail closed.
    await page.locator("#rhymeQuery").fill("Blue paper");
    await page.locator("#rhymeSearchForm button[type='submit']").click();
    await page.locator(".search-empty:not(.error)").waitFor({state:"visible",timeout:6500});
    assert.equal(await page.locator(".rhyme-card").count(),0);
    assert.equal(await page.locator(".rhyme-preview").count(),0);
    assert.deepEqual(errors,[],JSON.stringify({viewport:viewport.width,errors}));
    console.log(viewport.width+"px German-only rhyme preview, reviewed rhymes and fallback protection: PASSED");
    await context.close();
  }
}finally{
  await browser?.close();
  server.kill("SIGTERM");
}
