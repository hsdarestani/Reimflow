import {chromium} from "playwright";
import {spawn} from "node:child_process";
import assert from "node:assert/strict";
const server=spawn("python3",["-m","http.server","8184","--bind","127.0.0.1"],{stdio:"ignore"});
const delay=ms=>new Promise(r=>setTimeout(r,ms));
let browser;
try{
  await delay(500);
  browser=await chromium.launch({headless:true,args:[
    "--no-sandbox","--use-fake-ui-for-media-stream","--use-fake-device-for-media-stream"
  ]});
  for(const viewport of [{width:1280,height:820},{width:390,height:844}]){
    const context=await browser.newContext({viewport,permissions:["microphone"],baseURL:"http://127.0.0.1:8184"});
    const page=await context.newPage();
    const errors=[];
    page.on("pageerror",e=>errors.push(e.message));
    await page.goto("/",{waitUntil:"domcontentloaded"});
    await page.waitForTimeout(600);
    const nav=viewport.width<500?".mobile-nav [data-go='flow']":".desktop-nav [data-go='flow']";
    await page.locator(nav).click();
    assert.equal(await page.locator(".page.active").getAttribute("data-page"),"flow");
    await page.locator("#flowShowRap").click();
    assert.equal(await page.locator("#rapPanel").isVisible(),true);
    assert.equal(await page.locator("#tapGamePanel").isVisible(),false);
    await page.locator("#rapStart").click();
    assert.match(await page.locator("#rapStatus").innerText(),/Einwilligung erforderlich/);
    await page.locator("#rapConsent").check();
    await page.locator("#rapBars").selectOption("4");
    await page.locator("#rapStart").click();
    await page.waitForTimeout(1500);
    const status=await page.locator("#rapStatus").innerText();
    console.log(viewport.width+"px microphone status:",status);
    assert.ok(/Einzählen|Jetzt rappen|Aufnahme/.test(status));
    if(await page.locator("#rapStop").isEnabled()){
      await page.locator("#rapStop").click();
      await page.waitForTimeout(450);
    }
    // Tab switching back must not keep the recording active.
    await page.locator("#flowShowTap").click();
    assert.equal(await page.locator("#tapGamePanel").isVisible(),true);
    assert.equal(await page.locator("#rapPanel").isVisible(),false);
    assert.deepEqual(errors,[],"Runtime JS errors at "+viewport.width+": "+errors);
    console.log(viewport.width+"px Rap recording controls, consent and mode switch: PASSED");
    await context.close();
  }
}finally{
  await browser?.close();
  server.kill("SIGTERM");
}
