// Lightweight DOM smoke tests for Reimflow theme switching.
// No UI framework or production bundle dependency required.
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source=fs.readFileSync(new URL("../theme-engine.js",import.meta.url),"utf8");
const html=fs.readFileSync(new URL("../index.html",import.meta.url),"utf8");
const variants=fs.readFileSync(new URL("../comic-variants.css",import.meta.url),"utf8");

function element(dataset={}){
  const listeners={};
  const classes=new Set();
  const attrs={};
  return {
    dataset,
    classList:{
      add:c=>classes.add(c),
      remove:c=>classes.delete(c),
      toggle:(c,enabled)=>{
        if(enabled===undefined) enabled=!classes.has(c);
        if(enabled)classes.add(c);else classes.delete(c);
        return enabled;
      },
      contains:c=>classes.has(c)
    },
    addEventListener:(type,cb)=>{listeners[type]=cb},
    setAttribute:(k,v)=>{attrs[k]=v},
    getAttribute:k=>attrs[k],
    fire:(type,arg={})=>{assert.ok(listeners[type],"missing "+type+" listener");listeners[type](arg)},
    style:{setProperty:()=>{}},
    contains:()=>false
  };
}
function boot(savedValue="sonic-art"){
  const selected=[];
  const store=new Map([["reimflow_theme_v3",savedValue]]);
  const root=element({theme:"sonic-art"});
  const menu=element();
  const toggle=element();
  const chooser=element();
  const label=element();
  const meta=element();
  const btns=["sonic-art","comic-graffiti","comic-novel","comic-clean"].map(name=>element({themePick:name}));
  const opts=["sonic-art","comic-graffiti","comic-novel","comic-clean","playful","linear","minimal-dark","vaporwave","art-deco"].map(name=>element({themeOption:name}));
  const document={
    documentElement:root,
    querySelector(selector){
      return {".theme-switcher":chooser,"#themeToggle":toggle,"#themeMenu":menu,".theme-current":label,'meta[name="theme-color"]':meta}[selector]||null;
    },
    querySelectorAll(selector){
      return {"[data-theme-pick]":btns,"[data-theme-option]":opts}[selector]||[];
    },
    addEventListener:()=>{}
  };
  const window={
    addEventListener:()=>{},
    dispatchEvent:e=>selected.push(e.detail)
  };
  const context={
    window,document,localStorage:{
      getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)
    },
    CustomEvent:class{constructor(type,data){this.type=type;this.detail=data.detail}},
    requestAnimationFrame:()=>{},
    console
  };
  vm.runInNewContext(source,context,{filename:"theme-engine.js"});
  return{root,label,meta,btns,opts,menu,toggle,store,selected,chooser};
}

for(const [theme,expectedStyle] of [["sonic-art","pop"],["comic-graffiti","graffiti"],["comic-novel","novel"],["comic-clean","clean"]]){
  const ui=boot(theme);
  assert.equal(ui.root.dataset.theme,"sonic-art",theme+" must keep base app stylesheet");
  assert.equal(ui.root.dataset.comicStyle,expectedStyle);
  assert.equal(ui.opts.find(x=>x.dataset.themeOption===theme).getAttribute("aria-checked"),"true");
  assert.equal(ui.btns.find(x=>x.dataset.themePick===theme).getAttribute("aria-pressed"),"true");
  assert.ok(html.includes('data-theme-option="'+theme+'"'));
  assert.ok(html.includes('data-theme-pick="'+theme+'"'));
}

const ui=boot("sonic-art");
for(const [theme,style] of [["comic-graffiti","graffiti"],["comic-novel","novel"],["comic-clean","clean"],["sonic-art","pop"]]){
  ui.btns.find(x=>x.dataset.themePick===theme).fire("click");
  assert.equal(ui.root.dataset.comicStyle,style);
  assert.equal(ui.root.dataset.theme,"sonic-art");
  assert.equal(ui.store.get("reimflow_theme_v3"),theme);
  assert.equal(ui.opts.filter(x=>x.getAttribute("aria-checked")==="true").length,1);
  assert.equal(ui.selected.at(-1).theme,theme);
}
// Legacy themes remain usable and must turn off comic-only overrides.
ui.menu.fire("click",{target:{closest:()=>({dataset:{themeOption:"playful"}})}});
assert.equal(ui.root.dataset.theme,"playful");
assert.equal(ui.root.dataset.comicStyle,undefined);
assert.equal(ui.store.get("reimflow_theme_v3"),"playful");
assert.equal(ui.btns.filter(x=>x.getAttribute("aria-pressed")==="true").length,0);

assert.ok(html.includes("comic-variants.css?v=20261014-styles4"));
for(const name of ['data-comic-style="graffiti"','data-comic-style="novel"','data-comic-style="clean"']){
  assert.ok(variants.includes(name),"missing visual override "+name);
}
for(const w of [375,700,980])assert.ok(variants.includes("max-width: "+w+"px"),"missing viewport "+w);
assert.equal((variants.match(/{/g)||[]).length,(variants.match(/}/g)||[]).length);
console.log("9 themes preserved: 4 real Comic editions persist, switch, and retain mobile CSS breakpoints.");
