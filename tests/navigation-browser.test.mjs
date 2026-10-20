import {chromium} from "playwright";
import {spawn} from "node:child_process";
import assert from "node:assert/strict";
const server=spawn("python3",["-m","http.server","8179","--bind","127.0.0.1"],{stdio:"ignore"});
let browser;
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const errors=[];
try{
  await delay(600);
  browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
  for(const size of [{width:1366,height:850},{width:390,height:844}]){
    const context=await browser.newContext({viewport:size,isMobile:size.width<500,deviceScaleFactor:1});
    const page=await context.newPage();
    page.on("pageerror",e=>{errors.push({viewport:size.width,message:e.message});console.log("PAGEERROR",size.width,e.message,e.stack)});
    page.on("console",m=>{if(m.type()==="error")console.log("CONSOLE ERROR",size.width,m.text())});
    page.on("requestfailed",request=>console.log("REQUEST FAILED",size.width,request.url(),request.failure()?.errorText));
    const response=await page.goto("http://127.0.0.1:8179/",{waitUntil:"domcontentloaded"});
    assert.equal(response.status(),200);
    await page.waitForTimeout(1000);
    console.log("BOOT",size.width,await page.evaluate(()=>({scripts:[...document.scripts].map(s=>s.src.split("/").at(-1)),active:document.querySelector(".page.active")?.dataset.page,appState:typeof state, errors:window.__reimflow_errors||[]})));
    const selector=size.width<500?".mobile-nav [data-go]":".desktop-nav [data-go]";
    // Four clear primary destinations, with Beats/Community/Profile under Entdecken.
    for(const name of ["home","rhymes","flow","more"]){
      const button=page.locator(selector+'[data-go="'+name+'"]');
      assert.equal(await button.count(),1,"Missing primary tab "+name+" on "+size.width+"px");
      await button.click({timeout:5000});
      await page.waitForTimeout(190);
      const active=await page.locator(".page.active").getAttribute("data-page");
      assert.equal(active,name,"navigation failed on "+size.width+"px for "+name);
    }
    for(const name of ["beats","community","profile","premium"]){
      await page.locator(selector+'[data-go="more"]').click({timeout:5000});
      await page.locator('.page[data-page="more"] .more-tile[data-go="'+name+'"]').click({timeout:5000});
      const active=await page.locator(".page.active").getAttribute("data-page");
      assert.equal(active,name,"secondary navigation failed on "+size.width+"px for "+name);
      assert.equal(await page.locator(selector+'[data-go="more"].active').count(),1,"Entdecken should remain selected for "+name);
    }
    await page.locator(selector+'[data-go="rhymes"]').click({timeout:5000});
    assert.equal(await page.locator(".advanced-filters:not([open])").count(),1);
    await page.locator(".advanced-filters summary").click({timeout:5000});
    assert.equal(await page.locator(".advanced-filters[open] #categoryFilters").count(),1);
    console.log(size.width+"px primary and secondary navigation passed");
    if(size.width<500){
      const geometry=await page.evaluate(()=>{
        const nav=document.querySelector(".mobile-nav"),r=nav.getBoundingClientRect();
        return{left:r.left,right:r.right,viewport:innerWidth,width:r.width};
      });
      assert.ok(geometry.left>=0 && geometry.right<=size.width+1,"navigation exceeds phone width: "+JSON.stringify(geometry));
    }
    await context.close();
  }
  if(errors.length)console.log("Runtime page errors:",JSON.stringify(errors));
  assert.equal(errors.length,0,"runtime JS errors");
  console.log("Navigation browser smoke passed on desktop and mobile.");
}finally{
  await browser?.close();
  server.kill("SIGTERM");
}
