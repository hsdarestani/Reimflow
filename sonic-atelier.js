
(() => {
  const root=document.documentElement;
  const isArt=()=>root.dataset.theme==="sonic-art";

  // Persistent visual chrome
  const progress=document.createElement("div");
  progress.className="sonic-progress";progress.innerHTML="<i></i>";
  document.body.appendChild(progress);

  const cursor=document.createElement("div");
  cursor.className="sonic-cursor";
  document.body.appendChild(cursor);

  window.addEventListener("pointermove",e=>{
    if(!isArt()) return;
    cursor.style.left=e.clientX+"px";cursor.style.top=e.clientY+"px";
  },{passive:true});
  document.addEventListener("pointerover",e=>{
    if(!isArt())return;
    cursor.classList.toggle("hot",Boolean(e.target.closest("button,a,input,select,.art-panel")));
  });

  function updateProgress(){
    const max=Math.max(1,document.documentElement.scrollHeight-innerHeight);
    const p=Math.min(100,(scrollY/max)*100);
    progress.style.setProperty("--progress",p+"%");
  }
  addEventListener("scroll",updateProgress,{passive:true});updateProgress();

  // Populate phoneme constellation with deterministic positions.
  const phonemes=["aɪ","ɔʏ","ʃ","ŋ","ɪ","oː","ə","ts","ç","ʁ","aː","ɛ","BAR","/r/","/k/","/f/","ˈ","ˌ","∞","REIM","SILBE","KLANG"];
  const field=document.querySelector(".phoneme-field");
  if(field){
    for(let i=0;i<18;i++){
      const s=document.createElement("span");
      s.textContent=phonemes[i%phonemes.length];
      const x=(i*37)%97,y=(i*61)%91;
      s.style.left=x+"%";s.style.top=y+"%";
      s.style.setProperty("--fs",(0.52+(i%5)*.11)+"rem");
      s.style.setProperty("--o",String(.25+(i%7)*.08));
      s.style.setProperty("--r",((i*19)%70-35)+"deg");
      s.style.setProperty("--d",(5+(i%6)*1.35)+"s");
      s.style.setProperty("--x",((i%3)-1)*10+"px");
      s.style.setProperty("--y",(-8-(i%5)*3)+"px");
      s.style.setProperty("--c",i%5===0?"#ff4d2e":i%7===0?"#c8ff45":i%9===0?"#6d63ff":"#f0ece2");
      field.appendChild(s);
    }
  }

  // Create responsive waveform bars.
  const wave=document.querySelector(".wave-stack");
  if(wave){
    for(let i=0;i<27;i++){
      const bar=document.createElement("i");
      const d=Math.abs(i-23);
      const h=22+Math.max(0,74-d*2.4)+(i%4)*5;
      bar.style.setProperty("--h",h+"px");
      bar.style.setProperty("--t",(1.1+(i%7)*.17)+"s");
      wave.appendChild(bar);
    }
  }

  // Word sculpture changes like a kinetic poster.
  const core=document.querySelector(".core-word");
  const words=["KLANG","SILBE","REIM"];
  let wi=0;
  setInterval(()=>{
    if(!core||!isArt()||matchMedia("(prefers-reduced-motion: reduce)").matches)return;
    wi=(wi+1)%words.length;
    core.classList.remove("swap");
    void core.offsetWidth;
    core.textContent=words[wi];
    core.classList.add("swap");
  },2800);

  // Sculpture tilt, kept subtle and reset on leave.
  const sculpture=document.querySelector(".sonic-sculpture");
  if(sculpture){
    sculpture.addEventListener("pointermove",e=>{
      if(!isArt()||innerWidth<900)return;
      const r=sculpture.getBoundingClientRect();
      const x=(e.clientX-r.left)/r.width-.5;
      const y=(e.clientY-r.top)/r.height-.5;
      sculpture.style.transform="rotateX("+(-y*5)+"deg) rotateY("+(x*6)+"deg) translateZ(0)";
    });
    sculpture.addEventListener("pointerleave",()=>sculpture.style.transform="");
  }

  // Reveal chapters as the scroll passes them.
  const io=new IntersectionObserver(entries=>{
    for(const entry of entries){
      if(entry.isIntersecting)entry.target.classList.add("in-view");
    }
  },{threshold:.12});
  document.querySelectorAll(".art-chapter,.art-panel,.community-installation").forEach(el=>io.observe(el));

  // Page transitions are handled by CSS on .page.active.
  // Do not observe and mutate page classes here: that creates a self-triggering loop.

  // Audio-reactive-ish illusion: search typing nudges the sculpture.
  const heroInput=document.getElementById("heroQuery");
  heroInput?.addEventListener("input",e=>{
    if(!isArt()||!sculpture)return;
    const n=Math.min(1,e.target.value.length/16);
    sculpture.style.setProperty("--typing",n);
    const bars=sculpture.querySelectorAll(".wave-stack i");
    bars.forEach((bar,i)=>{
      if(i%3===e.target.value.length%3)bar.style.opacity=String(.5+n*.5);
    });
  });

  // Pause decorative motion when the tab is hidden to keep the artwork light on GPU/CPU.
  const syncPause=()=>document.documentElement.classList.toggle("art-paused",document.hidden);
  document.addEventListener("visibilitychange",syncPause);syncPause();

  // Keep custom chrome hidden when another theme is chosen.
  function sync(){
    const show=isArt();
    progress.style.display=show?"block":"none";
    cursor.style.display=show&&innerWidth>980?"block":"none";
  }
  addEventListener("reimflow:themechange",sync);
  addEventListener("resize",sync);
  sync();
})();
