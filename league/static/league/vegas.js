/* Server-owned outcomes and balances; this file only presents them. */
(() => {
  "use strict";
  const node=document.getElementById("vegas-config"); if(!node)return;
  const cfg=JSON.parse(node.textContent), $=id=>document.getElementById(`vegas-${id}`);
  const page=$("page"), machine=$("machine"), reels=$("reels"), svg=$("lines");
  const reduced=matchMedia("(prefers-reduced-motion: reduce)"), symbols=new Map(cfg.symbols.map(s=>[s.key,s]));
  const labels={banana:"БАНАНА",berry:"КЛУБНИЧНЫЙ МАКС",russell:"SPACE RUSSELL",toto:"NO, NO, NO!",bath:"БАН БАН БАН",tyre:"ПРОКОЛ",duck:"QUACK GP",wild:"WILD",scatter:"VEGAS"};
  const money=v=>new Intl.NumberFormat("ru-RU",{style:"currency",currency:"USD",maximumFractionDigits:v%100?2:0}).format(v/100);
  const pause=ms=>new Promise(r=>setTimeout(r,reduced.matches?Math.min(ms,35):ms));
  let state=cfg.state, betIndex=1, busy=false, pending=null, audio=null, sound=false;
  let current=cfg.last?.rounds?.at(-1)?.grid||Array.from({length:5},(_,c)=>Array.from({length:4},(_,r)=>cfg.symbols[(c*3+r)%cfg.symbols.length].key));
  const columns=Array.from({length:5},()=>{const column=document.createElement("div"),track=document.createElement("div");column.className="vegas-reel is-stopped";track.className="vegas-reel-track";column.append(track);reels.append(column);return{column,track};});
  function cell(key){
    const el=document.createElement("div"),art=document.createElement("span"),label=document.createElement("small");
    el.className="vegas-cell";el.dataset.symbol=key;el.setAttribute("aria-label",symbols.get(key).name);
    art.className=`vegas-symbol-art vegas-art-${key}`;art.setAttribute("aria-hidden","true");
    if(key==="wild"||key==="scatter"){const s=document.createElementNS("http://www.w3.org/2000/svg","svg"),use=document.createElementNS(s.namespaceURI,"use");use.setAttribute("href",key==="wild"?"#vegas-car":"#vegas-chip");s.append(use);art.append(s);}
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
  function clear(){svg.replaceChildren();$("particles").replaceChildren();reels.querySelectorAll(".is-winning,.is-exploding,.is-scatter").forEach(e=>e.classList.remove("is-winning","is-exploding","is-scatter"));}
  function line(win){
    svg.replaceChildren();const poly=document.createElementNS("http://www.w3.org/2000/svg","polyline");
    poly.setAttribute("points",win.rows.map((r,c)=>`${c*100+50},${r*100+50}`).join(" "));svg.append(poly);
    for(const[c,r]of win.cells){columns[c].track.children[r]?.classList.add("is-winning");const dot=document.createElementNS(poly.namespaceURI,"circle");dot.setAttribute("cx",c*100+50);dot.setAttribute("cy",r*100+50);dot.setAttribute("r",3);svg.append(dot);}
  }
  function sparks(cells){
    if(reduced.matches||document.hidden)return;const nodes=[];
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
  function log(result){
    let details=$("result-log");if(!details){details=document.createElement("details");details.id="vegas-result-log";details.className="vegas-rules";machine.after(details);}details.replaceChildren();
    const summary=document.createElement("summary"),content=document.createElement("div"),note=document.createElement("p");
    summary.textContent=`Последний спин · ${result.free?"бесплатный":money(result.bet)} · выигрыш ${money(result.payout)}`;
    note.textContent=`${result.scenario!=="random"?"ПРИНУДИТЕЛЬНЫЙ ТЕСТ · ":""}Каскадов: ${result.rounds.length}. Scatter: ${result.scatters}. Новых free spins: ${result.awarded}.`;content.append(note);
    result.rounds.forEach((round,i)=>{if(!round.wins.length)return;const p=document.createElement("p");p.textContent=`Каскад ${i+1} · ×${round.multiplier}: `+round.wins.map(w=>`линия ${w.line}, ${symbols.get(w.symbol).name} ×${w.count}: ${money(w.amount)}`).join("; ");content.append(p);});
    if(result.cascade_limit){const p=document.createElement("p");p.textContent="Достигнут лимит шести каскадов. Все показанные выигрыши оплачены.";content.append(p);}details.append(summary,content);
  }
  async function present(data){
    const result=data.result,first=result.rounds[0];await pause(700);
    for(let c=0;c<5;c++){columns[c].column.classList.add("is-stopped");column(c,first.grid[c]);tone(240+c*70,0,.055);await pause(130);}
    machine.classList.remove("is-spinning");current=first.grid;let total=0;
    for(const[i,round]of result.rounds.entries()){
      if(i)await cascade(result.rounds[i-1].grid,round.grid,result.rounds[i-1].wins);
      $("multiplier").textContent=`×${round.multiplier}`;if(!round.wins.length)break;
      total+=round.amount;$("win").textContent=money(total);
      for(const win of round.wins.slice(0,5)){clear();line(win);message(`Линия ${win.line} · ${symbols.get(win.symbol).name} ×${win.count} · +${money(win.amount)}`);tone(440,0,.15);tone(660,.08,.15);await pause(300);}
      clear();round.wins.flatMap(w=>w.cells).forEach(([c,r])=>columns[c].track.children[r]?.classList.add("is-winning"));message(`${round.wins.length} выигрышных линий · каскад +${money(round.amount)}`);await pause(400);
    }
    state=data.state;controls();$("win").textContent=money(result.payout);log(result);
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
      else{state=data.state;message("Тестовый баланс сброшен до $5 000");$("multiplier").textContent="×1";$("result-log")?.remove();}
      $("scenario").value="random";
    }catch(error){message(error.name==="AbortError"?"Нет подтверждения сервера. Повтори запрос — без повторного списания.":error.message);}
    finally{machine.classList.remove("is-spinning");columns.forEach(({column:el,track},c)=>{el.classList.add("is-stopped");if(track.children.length!==4)column(c,current[c]);});busy=false;controls();$("spin").focus({preventScroll:true});}
  }
  $("spin").addEventListener("click",()=>request());$("reset").addEventListener("click",()=>request("reset"));
  $("minus").addEventListener("click",()=>{betIndex=Math.max(0,betIndex-1);controls();});$("plus").addEventListener("click",()=>{betIndex=Math.min(cfg.bets.length-1,betIndex+1);controls();});
  $("sound").addEventListener("click",async()=>{try{const Audio=window.AudioContext||window.webkitAudioContext;if(!Audio)throw new Error();audio=audio||new Audio();await audio.resume();sound=!sound;$("sound").setAttribute("aria-pressed",String(sound));$("sound").textContent=sound?"Звук вкл.":"Звук выкл.";tone(660);}catch{message("Звук недоступен в этом браузере.");}});
  let oldOverflow="";
  function fullscreen(on){if(on){oldOverflow=document.body.style.overflow;document.body.style.overflow="hidden";}else document.body.style.overflow=oldOverflow;page.classList.toggle("is-fullscreen",on);$("fullscreen").textContent=on?"Выйти из экрана":"На весь экран";$("fullscreen").setAttribute("aria-pressed",String(on));}
  $("fullscreen").addEventListener("click",()=>fullscreen(!page.classList.contains("is-fullscreen")));
  document.addEventListener("keydown",e=>{if(e.key==="Escape"&&page.classList.contains("is-fullscreen")&&$("celebration").hidden)fullscreen(false);if(e.code==="Space"&&!e.repeat&&page.contains(e.target)&&!e.target.closest("input,textarea,select,button,summary,a")&&$("celebration").hidden){e.preventDefault();request();}});
  cfg.symbols.filter(s=>s.pays.length).forEach(s=>{const card=document.createElement("div"),title=document.createElement("b"),values=document.createElement("span");title.textContent=s.name;values.textContent=s.pays.map((v,i)=>`${i+3}: ×${v}`).join(" · ")+" от ставки на линию";card.append(title,values);$("paytable").append(card);});
  cfg.lines.forEach((rows,i)=>{const b=document.createElement("button");b.type="button";b.textContent=i+1;b.setAttribute("aria-label",`Показать линию ${i+1}`);b.addEventListener("click",()=>{if(busy)return;clear();line({rows,cells:rows.map((r,c)=>[c,r])});message(`Маршрут линии ${i+1}`);machine.scrollIntoView({behavior:reduced.matches?"instant":"smooth",block:"center"});});$("line-picker").append(b);});
  grid(current);controls();if(cfg.last){$("win").textContent=money(cfg.last.payout);log(cfg.last);}
})();
