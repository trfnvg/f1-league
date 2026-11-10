/* Server-owned outcomes and balances; this file only presents them. */
(() => {
  "use strict";
  const node=document.getElementById("vegas-config"); if(!node)return;
  const cfg=JSON.parse(node.textContent), $=id=>document.getElementById(`vegas-${id}`);
  const page=$("page"), machine=$("machine"), reels=$("reels"), svg=$("lines");
  const reduced=matchMedia("(prefers-reduced-motion: reduce)"), symbols=new Map(cfg.symbols.map(s=>[s.key,s]));
  const labels={banana:"SBINALLA",berry:"SMOOTH OPERATOR",russell:"T-POSE",toto:"NO, MICHAEL!",bath:"EL PLAN",tyre:"BONO, MY TYRES!",duck:"GP2 ENGINE",wild:"WILD",scatter:"SCATTER"};
  const money=v=>new Intl.NumberFormat("ru-RU",{style:"currency",currency:"USD",maximumFractionDigits:v%100?2:0}).format(v/100);
  const pause=ms=>new Promise(r=>setTimeout(r,reduced.matches?Math.min(ms,35):ms));
  let state=cfg.state, betIndex=Math.max(0,cfg.bets.indexOf(cfg.default_bet)), busy=false, pending=null, audio=null, sound=false;
  let current=cfg.last?.rounds?.at(-1)?.grid||Array.from({length:5},(_,c)=>Array.from({length:4},(_,r)=>cfg.symbols[(c*3+r)%cfg.symbols.length].key));
  const columns=Array.from({length:5},()=>{const column=document.createElement("div"),track=document.createElement("div");column.className="vegas-reel is-stopped";track.className="vegas-reel-track";column.append(track);reels.append(column);return{column,track};});
  function cell(key){
    const el=document.createElement("div"),art=document.createElement("span"),label=document.createElement("small");
    el.className="vegas-cell";el.dataset.symbol=key;el.setAttribute("aria-label",symbols.get(key).name);
    art.className=`vegas-symbol-art vegas-art-${key}`;art.setAttribute("aria-hidden","true");
    label.textContent=labels[key];el.append(art,label);return el;
  }
  function column(c,values,duplicate=false){columns[c].track.replaceChildren(...(duplicate?values.concat(values):values).map(cell));}
  function grid(values){values.forEach((v,c)=>column(c,v));current=values;}
  function message(text){$("message").textContent=text;}
  function tone(f,delay=0,length=.1){
    if(!sound||!audio||document.hidden)return;
    const o=audio.createOscillator(),g=audio.createGain(),t=audio.currentTime+delay;o.frequency.value=f;
    g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(.035,t+.008);g.gain.exponentialRampToValueAtTime(.0001,t+length);
    o.connect(g);g.connect(audio.destination);o.start(t);o.stop(t+length);
  }
  function controls(){
    $("balance").textContent=money(state.balance);$("free").textContent=state.free_spins;
    $("bet").textContent=money(state.free_spins?state.bonus_bet:cfg.bets[betIndex]);$("spin").disabled=busy;
    $("spin").querySelector("span").textContent=busy?"СПИН…":pending?"ПОВТОРИТЬ":state.free_spins?"FREE SPIN":"КРУТИТЬ";
    $("minus").disabled=busy||!!pending||state.free_spins>0||betIndex===0;
    $("plus").disabled=busy||!!pending||state.free_spins>0||betIndex===cfg.bets.length-1;
    $("reset").disabled=busy||!!pending;$("scenario").disabled=busy||!!pending;
    machine.classList.toggle("is-bonus",state.free_spins>0);machine.setAttribute("aria-busy",String(busy));
  }
  // Responsive stage: size the field against BOTH viewport axes. No scale()
  // transforms, distorted tiles, polling loop, or scroll-blocking touch handlers.
  function fitStage(){
    const full=page.classList.contains("is-fullscreen"),safe=full?getComputedStyle(page):null;
    const height=(window.visualViewport?.height||innerHeight)-(safe?(parseFloat(safe.paddingTop)||0)+(parseFloat(safe.paddingBottom)||0):0);
    const wide=machine.clientWidth>=700||(innerWidth>=650&&height<500);
    machine.classList.toggle("is-wide",wide);
    const h=selector=>machine.querySelector(selector)?.getBoundingClientRect().height||0;
    const outside=full?0:(document.querySelector(".site-header")?.offsetHeight||60)+page.querySelector(".vegas-page-heading").offsetHeight+32+(innerWidth<=700?68:0);
    const overhead=h(".vegas-toolbar")+h(".vegas-marquee")+h(".vegas-announcer")+h(".vegas-console")+24;
    const maxWidth=Math.max(180,machine.clientWidth-24);
    const board=Math.floor(Math.min(750,maxWidth,Math.max(wide?120:180,height-outside-overhead)*1.25));
    machine.style.setProperty("--board-size",`${board}px`);
    // The bottom control bar stays comfortably wide even in a short viewport.
    machine.style.setProperty("--cabinet-width",`${Math.min(maxWidth,Math.max(board,wide?580:0))}px`);
  }
  let fitFrame=0;
  function scheduleFit(){cancelAnimationFrame(fitFrame);fitFrame=requestAnimationFrame(fitStage);}
  window.addEventListener("resize",scheduleFit);window.visualViewport?.addEventListener("resize",scheduleFit);
  const resizeObserver=new ResizeObserver(entries=>{
    const width=Math.round(entries[0].contentRect.width);
    if(resizeObserver.lastWidth!==width){resizeObserver.lastWidth=width;scheduleFit();}
  });resizeObserver.observe(machine);

  // Transient canvas FX only. <=3 bursts, <=54 sparks, DPR capped at 1.5,
  // no animation frame remains scheduled after the last burst expires.
  const fxCanvas=$("fx"), fxContext=fxCanvas.getContext("2d");
  fxCanvas.dataset.active="false";
  let fxEnabled=true, fxFrame=0, fxBursts=[], fxWidth=0, fxHeight=0, fxRatio=1, edgeTimer=0;
  function stopFX(){
    cancelAnimationFrame(fxFrame);fxFrame=0;fxBursts=[];clearTimeout(edgeTimer);
    machine.classList.remove("is-fire","is-electric");
    fxContext?.clearRect(0,0,fxWidth,fxHeight);fxCanvas.dataset.active="false";
  }
  function paintFX(now){
    fxBursts=fxBursts.filter(b=>now-b.born<950);
    if(!fxEnabled||reduced.matches||document.hidden||!fxBursts.length){stopFX();return;}
    const ctx=fxContext;ctx.clearRect(0,0,fxWidth,fxHeight);
    for(const burst of fxBursts){
      const t=Math.max(0,(now-burst.born)/950),fade=Math.sin(Math.PI*Math.min(1,t*1.7))*(1-t);
      ctx.save();ctx.globalAlpha=Math.max(0,fade);ctx.globalCompositeOperation="lighter";
      const electric=burst.mode==="electric";
      ctx.strokeStyle=electric?"#a1f4ff":"#ffbb65";ctx.lineWidth=1.8;
      // Ribbons stay at cell borders, so faces and line labels remain legible.
      for(const [col,row]of burst.cells.slice(0,8)){
        const x=col*fxWidth/5+3,y=row*fxHeight/4+3,cw=fxWidth/5-6,ch=fxHeight/4-6;
        ctx.beginPath();
        for(let k=0;k<=12;k++){
          const dx=x+cw*k/12,dy=y+(k===0||k===12?0:Math.sin(k*8+burst.seed)*Math.min(5,fxWidth*.009));
          if(!k)ctx.moveTo(dx,dy);else ctx.lineTo(dx,dy);
        }ctx.stroke();
        if(electric){ctx.beginPath();ctx.moveTo(x+cw,y);ctx.lineTo(x+cw-3,y+ch*.35);ctx.lineTo(x+cw+1,y+ch*.65);ctx.lineTo(x+cw,y+ch);ctx.stroke();}
      }
      if(!electric){
        for(let n=0;n<12;n++){
          const x=(n+.5)*fxWidth/12,w=fxWidth/18,h=(14+12*Math.sin(n*1.7+burst.seed))*Math.sin(t*Math.PI)+8;
          const flame=ctx.createLinearGradient(0,fxHeight,0,fxHeight-h);flame.addColorStop(0,"#ee6225");flame.addColorStop(.5,"#ffc174");flame.addColorStop(1,"#ffe9a800");ctx.fillStyle=flame;
          ctx.beginPath();ctx.moveTo(x-w,fxHeight);ctx.bezierCurveTo(x-w,fxHeight-h*.5,x+w*.8,fxHeight-h*.5,x,fxHeight-h);ctx.bezierCurveTo(x+w*1.5,fxHeight-h*.4,x+w,fxHeight,x+w,fxHeight);ctx.fill();
        }
      }
      for(let n=0;n<18;n++){
        const [c,r]=burst.cells[n%burst.cells.length],angle=n*2.4+burst.seed,travel=t*(18+n*2);
        const x=(c+.5)*fxWidth/5+Math.cos(angle)*travel,y=(r+.5)*fxHeight/4+Math.sin(angle)*travel-t*22;
        ctx.fillStyle=electric?"#bceef5":"#ffcf82";ctx.fillRect(x,y,2,Math.max(2,4*(1-t)));
      }
      ctx.restore();
    }
    fxFrame=requestAnimationFrame(paintFX);
  }
  function burstFX(mode,cells){
    if(!fxContext||!fxEnabled||reduced.matches||document.hidden||!cells.length)return;
    const box=$("board").getBoundingClientRect();fxWidth=box.width;fxHeight=box.height;fxRatio=Math.min(devicePixelRatio||1,1.5);
    const w=Math.round(fxWidth*fxRatio),h=Math.round(fxHeight*fxRatio);
    if(fxCanvas.width!==w||fxCanvas.height!==h){fxCanvas.width=w;fxCanvas.height=h;fxContext.setTransform(fxRatio,0,0,fxRatio,0,0);}
    fxBursts.push({mode,cells,born:performance.now(),seed:Math.random()*20});fxBursts=fxBursts.slice(-3);
    machine.classList.remove("is-fire","is-electric");machine.classList.add(mode==="electric"?"is-electric":"is-fire");
    clearTimeout(edgeTimer);edgeTimer=setTimeout(()=>machine.classList.remove("is-fire","is-electric"),950);
    fxCanvas.dataset.active="true";fxCanvas.dataset.effect=mode;
    if(!fxFrame)fxFrame=requestAnimationFrame(paintFX);
  }
  $("effects").addEventListener("click",()=>{
    fxEnabled=!fxEnabled;page.classList.toggle("effects-off",!fxEnabled);$("effects").setAttribute("aria-pressed",String(fxEnabled));$("effects").textContent=fxEnabled?"Эффекты вкл.":"Эффекты выкл.";if(!fxEnabled)stopFX();
  });
  reduced.addEventListener("change",()=>{if(reduced.matches)stopFX();});document.addEventListener("visibilitychange",()=>{if(document.hidden)stopFX();});
  function clear(){svg.replaceChildren();$("particles").replaceChildren();reels.querySelectorAll(".is-winning,.is-exploding,.is-scatter").forEach(e=>e.classList.remove("is-winning","is-exploding","is-scatter"));}
  function line(win){
    svg.replaceChildren();const poly=document.createElementNS("http://www.w3.org/2000/svg","polyline");
    poly.setAttribute("points",win.rows.map((r,c)=>`${c*100+50},${r*100+50}`).join(" "));svg.append(poly);
    for(const[c,r]of win.cells){columns[c].track.children[r]?.classList.add("is-winning");const dot=document.createElementNS(poly.namespaceURI,"circle");dot.setAttribute("cx",c*100+50);dot.setAttribute("cy",r*100+50);dot.setAttribute("r",3);svg.append(dot);}
  }
  function sparks(cells){
    if(!fxEnabled||reduced.matches||document.hidden)return;const nodes=[];
    for(const[c,r]of cells.slice(0,12))for(let i=0;i<4;i++){const n=document.createElement("i");n.style.cssText=`--x:${(c+.5)*20}%;--y:${(r+.5)*25}%;--dx:${(i%2?1:-1)*(20+i*8)}px;--dy:${-30-i*12}px`;nodes.push(n);}
    $("particles").replaceChildren(...nodes);
  }
  async function cascade(previous,next,wins){
    const removed=new Set(wins.flatMap(w=>w.cells.map(([c,r])=>`${c},${r}`)));
    for(const key of removed){const[c,r]=key.split(",").map(Number);columns[c].track.children[r]?.classList.add("is-exploding");}
    sparks([...removed].map(k=>k.split(",").map(Number)));await pause(350);clear();const animations=[];
    for(let c=0;c<5;c++){
      const kept=previous[c].map((_,r)=>r).filter(r=>!removed.has(`${c},${r}`)),added=4-kept.length;column(c,next[c]);
      if(!reduced.matches&&!document.hidden){const height=columns[c].track.clientHeight/4;
        [...columns[c].track.children].forEach((el,r)=>{const d=r<added?-(added+1)*height:(kept[r-added]-r)*height;
          if(d)animations.push(el.animate([{transform:`translateY(${d}px)`,opacity:r<added?.25:1},{transform:"translateY(0)",opacity:1}],{duration:360,delay:c*35,easing:"cubic-bezier(.2,.7,.2,1)"}).finished.catch(()=>{}));});}
    }
    current=next;await Promise.all(animations);
  }
  function celebration(title,value,copy,kicker="VEGAS PIT"){
    $("celebration-kicker").textContent=kicker;$("celebration-title").textContent=title;$("celebration-value").textContent=value;$("celebration-copy").textContent=copy;
    const overlay=$("celebration"),button=$("celebration-close");overlay.hidden=false;overlay.setAttribute("aria-labelledby","vegas-celebration-title");overlay.showModal();
    const inert=[...page.children].filter(el=>el!==machine).concat([...machine.children].filter(el=>el!==overlay));inert.forEach(el=>el.inert=true);button.focus();
    return new Promise(resolve=>{
      function finish(){overlay.close();overlay.hidden=true;inert.forEach(el=>el.inert=false);button.removeEventListener("click",finish);overlay.removeEventListener("keydown",keys);overlay.removeEventListener("cancel",cancel);resolve();}
      function cancel(e){e.preventDefault();finish();}
      function keys(e){if(e.key==="Escape"){e.preventDefault();e.stopPropagation();finish();}if(e.key==="Tab"){e.preventDefault();button.focus();}}
      button.addEventListener("click",finish);overlay.addEventListener("keydown",keys);overlay.addEventListener("cancel",cancel);
    });
  }
  async function present(data){
    const result=data.result,first=result.rounds[0];await pause(700);
    for(let c=0;c<5;c++){columns[c].column.classList.add("is-stopped");column(c,first.grid[c]);tone(240+c*70,0,.055);await pause(130);}
    machine.classList.remove("is-spinning");current=first.grid;let total=0;
    for(const[i,round]of result.rounds.entries()){
      if(i)await cascade(result.rounds[i-1].grid,round.grid,result.rounds[i-1].wins);
      $("multiplier").textContent=`×${round.multiplier}`;if(!round.wins.length)break;
      total+=round.amount;$("win").textContent=money(total);
      burstFX(round.multiplier>=3||round.amount>=result.bet*8?"fire":"electric",round.wins.flatMap(w=>w.cells));
      for(const win of round.wins.slice(0,5)){clear();line(win);message(`Линия ${win.line} · ${symbols.get(win.symbol).name} ×${win.count} · +${money(win.amount)}`);tone(440,0,.15);tone(660,.08,.15);await pause(300);}
      clear();round.wins.flatMap(w=>w.cells).forEach(([c,r])=>columns[c].track.children[r]?.classList.add("is-winning"));message(`${round.wins.length} выигрышных линий · каскад +${money(round.amount)}`);await pause(400);
    }
    state=data.state;controls();$("win").textContent=money(result.payout);
    if(result.awarded){reels.querySelectorAll('[data-symbol="scatter"]').forEach(el=>el.classList.add("is-scatter"));[392,494,587,784].forEach((f,i)=>tone(f,i*.1,.35));await celebration(result.free?"ЕЩЁ КРУГИ!":"БОНУСНЫЙ СТИНТ",`+${result.awarded} FREE SPINS`,`Осталось ${state.free_spins}. Ставка ${money(state.bonus_bet)} зафиксирована. Множители ×2 → ×12.`,"SCATTER · VEGAS");}
    else if(result.payout>=result.bet*8){[440,554,659,880].forEach((f,i)=>tone(f,i*.08,.3));await celebration(result.payout>=result.bet*25?"MEGA WIN":"BIG WIN",money(result.payout),"Все выигрышные линии зачислены на тестовый баланс.");}
    message(result.free&&!state.free_spins?"Бонусный стинт завершён":state.free_spins?`Бесплатных вращений: ${state.free_spins} · ставка не списывается`:result.payout?`На баланс зачислено ${money(result.payout)}`:"Нет выигрышных комбинаций");
  }
  async function request(action="spin"){
    if(busy||!$("celebration").hidden)return;
    if(action==="reset"&&!confirm("Сбросить только свой тестовый баланс и бесплатные вращения?"))return;
    if(!pending)pending={request_id:crypto.randomUUID(),revision:state.revision,bet:cfg.bets[betIndex],scenario:$("scenario").value,action};
    busy=true;clear();controls();$("win").textContent=money(0);message(pending.action==="reset"?"Сбрасываем тестовый баланс…":"Барабаны вращаются…");
    if(pending.action==="spin"){columns.forEach(({column:el},c)=>{column(c,current[c],true);el.classList.remove("is-stopped");});machine.classList.add("is-spinning");}
    try{
      if(audio?.state==="suspended")await audio.resume();
      const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000);let response;
      try{response=await fetch(cfg.spin_url,{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json","X-CSRFToken":page.querySelector('[name="csrfmiddlewaretoken"]').value},body:JSON.stringify(pending),signal:controller.signal});}finally{clearTimeout(timer);}
      let data;try{data=await response.json();}catch{throw new Error("Сервер не подтвердил результат. Повтори запрос — новая ставка не спишется.");}
      if(!response.ok){if(data.state){state=data.state;pending=null;}if(response.status===400||response.status===403)pending=null;throw new Error(data.error||"Не удалось выполнить прокрутку.");}
      pending=null;
      if(data.result){state=data.state;await present(data);}
      else{state=data.state;message("Тестовый баланс сброшен до $5 000");$("multiplier").textContent="×1";}
      $("scenario").value="random";
    }catch(error){message(error.name==="AbortError"?"Нет подтверждения сервера. Повтори запрос — без повторного списания.":error.message);}
    finally{machine.classList.remove("is-spinning");columns.forEach(({column:el,track},c)=>{el.classList.add("is-stopped");if(track.children.length!==4)column(c,current[c]);});busy=false;controls();$("spin").focus({preventScroll:true});}
  }
  $("spin").addEventListener("click",()=>request());$("reset").addEventListener("click",()=>request("reset"));
  $("minus").addEventListener("click",()=>{betIndex=Math.max(0,betIndex-1);controls();});$("plus").addEventListener("click",()=>{betIndex=Math.min(cfg.bets.length-1,betIndex+1);controls();});
  $("sound").addEventListener("click",async()=>{try{const Audio=window.AudioContext||window.webkitAudioContext;if(!Audio)throw new Error();audio=audio||new Audio();await audio.resume();sound=!sound;$("sound").setAttribute("aria-pressed",String(sound));$("sound").textContent=sound?"Звук вкл.":"Звук выкл.";tone(660);}catch{message("Звук недоступен в этом браузере.");}});
  let oldOverflow="";
  function fullscreen(on){if(on){oldOverflow=document.body.style.overflow;document.body.style.overflow="hidden";}else document.body.style.overflow=oldOverflow;page.classList.toggle("is-fullscreen",on);$("fullscreen").textContent=on?"Выйти из экрана":"На весь экран";$("fullscreen").setAttribute("aria-pressed",String(on));scheduleFit();}
  $("fullscreen").addEventListener("click",()=>fullscreen(!page.classList.contains("is-fullscreen")));
  document.addEventListener("keydown",e=>{
    if(e.key==="Escape"&&page.classList.contains("is-fullscreen")&&$("celebration").hidden)fullscreen(false);
    if(e.code!=="Space"&&e.key!==" ")return;
    if(e.isComposing||e.ctrlKey||e.altKey||e.metaKey||e.defaultPrevented)return;
    if(!$("celebration").hidden||e.target.closest('input,textarea,select,[contenteditable]:not([contenteditable="false"])'))return;
    // Works from the initial body focus and every game button. Suppress native
    // button activation/scrolling, including held-key repeats, to send one spin.
    e.preventDefault();if(!e.repeat)request();
  });
  grid(current);controls();fitStage();if(cfg.last)$("win").textContent=money(cfg.last.payout);
})();
