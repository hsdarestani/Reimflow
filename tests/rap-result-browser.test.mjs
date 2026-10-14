import {chromium} from "playwright";
import {spawn} from "node:child_process";
import assert from "node:assert/strict";
const server=spawn("python3",["-m","http.server","8187","--bind","127.0.0.1"],{stdio:"ignore"});
let browser;
const delay=ms=>new Promise(r=>setTimeout(r,ms));
try{
  await delay(550);
  browser=await chromium.launch({headless:true,args:[
    "--no-sandbox","--use-fake-ui-for-media-stream","--use-fake-device-for-media-stream"
  ]});
  const context=await browser.newContext({viewport:{width:390,height:844},
    permissions:["microphone"],baseURL:"http://127.0.0.1:8187"});
  const page=await context.newPage(),errors=[];
  page.on("pageerror",e=>errors.push(e.message));
  await page.goto("/",{waitUntil:"domcontentloaded"});
  await page.locator(".mobile-nav [data-go='flow']").click();
  await page.locator("#flowShowRap").click();
  await page.locator("#rapConsent").check();
  await page.locator("#rapBpm").selectOption("140");
  await page.locator("#rapBars").selectOption("4");
  await page.locator("#rapStart").click();
  await page.locator("#rapPreview").waitFor({state:"visible",timeout:17000});
  const state=page.locator("#rapAnalysisState"),results=page.locator("#rapResults");
  assert.match(await state.textContent(),/Aufnahme gespeichert/);
  assert.equal(await results.isVisible(),false);
  assert.ok(await page.locator("#rapAudioPreview").getAttribute("src"));
  assert.match(await page.locator("#rapRecordingDuration").textContent(),/Tatsächliche Aufnahmelänge:/);
  const metadata=await page.evaluate(async()=>{
    const audio=document.querySelector("#rapAudioPreview");
    audio.preload="metadata";
    audio.load();
    if(audio.readyState<1){
      await new Promise((resolve,reject)=>{
        audio.addEventListener("loadedmetadata",resolve,{once:true});
        audio.addEventListener("error",()=>reject(Error("Playback metadata rejected")),{once:true});
        setTimeout(()=>reject(Error("Audio metadata timeout")),5000);
      });
    }
    return {duration:audio.duration,url:audio.src,blobType:audio.currentSrc};
  });
  assert.ok(Number.isFinite(metadata.duration)&&metadata.duration>7&&metadata.duration<18,
    "Expected a real short WAV duration, got "+JSON.stringify(metadata));

  let attempts=0;
  await page.route("**/api/flow/analyze",async route=>{
    attempts++;
    if(attempts===1)await route.fulfill({status:502,contentType:"text/html",body:"<html><body>Bad Gateway</body></html>"});
    else await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({
      ok:true,status:"analyzed",metrics:{
        bpm:140,bars:4,word_onset_grid_percent:68,longest_pause_sec:0.63,
        syllables_est:15,density_change_per_sec_est:0.74},
      bars:[{bar:1,syllables_est:2},{bar:2,syllables_est:4},{bar:3,syllables_est:6},{bar:4,syllables_est:3}],
      words:[{word:"Hallo",start:0.2,end:0.5},{word:"Reimflow",start:0.65,end:1.1}],
      feedback:["68 % im Zeitraster."],transcript:"Hallo Reimflow",
      limits:"Näherungen, keine musikalische Talentnote."
    })});
  });
  await page.locator("#rapAnalyze").click();
  await page.locator("#rapAnalyze").getByText("Analyse erneut versuchen").waitFor({timeout:7000});
  assert.match(await state.textContent(),/Analyse fehlgeschlagen: Der Analyseserver ist vorübergehend nicht erreichbar.*HTTP 502/);
  assert.equal(await results.isVisible(),false);
  await page.locator("#rapAnalyze").click();
  await page.locator("#rapResultTitle").getByText("Dein Flow im Zeitraster").waitFor({timeout:7000});
  assert.equal(await page.locator("#rapGrid").textContent(),"68 %");
  assert.equal(await results.isVisible(),true);
  assert.match(await state.textContent(),/Analyse abgeschlossen/);
  assert.match(await page.locator("#rapAnalyze").textContent(),/Erneut auswerten/);
  const ordering=await page.evaluate(()=>{
    const record=document.querySelector(".rap-record-card");
    const results=document.querySelector("#rapResults");
    const tips=document.querySelector(".rap-info-card");
    return {underRecording:record.contains(results),tipsAfter:!!(results.compareDocumentPosition(tips)&Node.DOCUMENT_POSITION_FOLLOWING)};
  });
  assert.ok(ordering.underRecording && ordering.tipsAfter,"Results must appear before explanatory sidebar on mobile");
  assert.equal(attempts,2);
  assert.deepEqual(errors,[],"No browser JS runtime error should occur");
  console.log("Mobile Rap analysis error + retry + success UX: PASSED");
}finally{
  await browser?.close();
  server.kill("SIGTERM");
}
