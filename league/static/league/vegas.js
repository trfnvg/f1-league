/* Server-owned outcomes and balances; this file only presents them. */
(() => {
  "use strict";
  const node=document.getElementById("vegas-config"); if(!node)return;
  const cfg=JSON.parse(node.textContent), $=id=>document.getElementById(`vegas-${id}`);
  const page=$("page"), machine=$("machine"), reels=$("reels"), svg=$("lines");
  const reduced=matchMedia("(prefers-reduced-motion: reduce)"), symbols=new Map(cfg.symbols.map(s=>[s.key,s]));
const labels={banana:"КУБОК НОРРИСА",berry:"БАНАНА ЛЕКЛЕР",russell:"КЛУБНИКА МАКС",toto:"ПЕРЧИК РАССЕЛЛ",bath:"АЛОНСО В ШЕЗЛОНГЕ",tyre:"BONO, MY TYRES!",duck:"ТРАКТОР FERRARI",wild:"WILD",scatter:"БОНУС"};
  const cashFormat=new Intl.NumberFormat("ru-RU",{style:"currency",currency:"USD",maximumFractionDigits:0});
  const centsFormat=new Intl.NumberFormat("ru-RU",{style:"currency",currency:"USD",maximumFractionDigits:2});
  const money=v=>(v%100?centsFormat:cashFormat).format(v/100);
  const unlimited=cfg.unlimited_balance===true;
  const canAfford=cost=>unlimited||state.balance>=cost;
  const pause=ms=>new Promise(resolve=>{
    let timer;
    const finish=()=>{clearTimeout(timer);document.removeEventListener("visibilitychange",hidden);resolve();};
    const hidden=()=>{if(document.hidden)finish();};
    timer=setTimeout(finish,reduced.matches||document.hidden?Math.min(ms,35):ms);
    document.addEventListener("visibilitychange",hidden);
  });
  let state=cfg.state, betIndex=Math.max(0,cfg.bets.indexOf(cfg.default_bet)), busy=false, pending=null, audio=null, sound=true;
  let autoPlay=false,autoCount=25,autoRemaining=0;
  let displayedBalance=null;
  let autoTimer=0, bonusPaused=false, autoBlocked=false, pageSuspended=false, lastRequestAt=0;
  let daily=null,dailySending=false,dailyTimer=0;
  function dailyControls(){
    if(!$("daily"))return;
    $("daily").disabled=dailySending||busy||!!pending||autoPlay||!daily||daily.claimed||cfg.closed||state.free_spins>0||state.balance>=10000;
    $("daily").textContent=dailySending?"Начисляем…":daily?.claimed?"Сегодня получено":"Забрать +3 000 $";
    $("daily-note").textContent=cfg.closed?"Зачёт завершён":daily?.claimed?"Снова в 00:00 МСК":state.free_spins?"Заверши бонусную серию":"Баланс ниже 100 $ · обновление в 00:00 МСК";
  }
  async function dailyRequest(claim=false){
    clearTimeout(dailyTimer);
    if(!cfg.daily_url||document.hidden||pageSuspended||(!claim&&dailySending))return;
    if(claim){if(busy||pending||autoPlay||dailySending)return;dailySending=true;controls();}
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
    try{
      const response=await fetch(cfg.daily_url,{method:claim?"POST":"GET",credentials:"same-origin",signal:controller.signal,
        ...(claim?{headers:{"Content-Type":"application/json","X-CSRFToken":page.querySelector('[name="csrfmiddlewaretoken"]').value},body:JSON.stringify({wallet_id:cfg.wallet_id})}:{})});
      const data=await response.json();if(!response.ok)throw new Error(data.error||"Не удалось проверить пополнение.");
      if(data.wallet_id!==cfg.wallet_id)return;
      if(data.closed)cfg.closed=true;
      if(data.state.revision<state.revision)return;
      daily=data;
      if(!busy&&!pending&&data.state.revision>=state.revision)state=data.state;
      if(claim)message("Ежедневные +3 000 $ зачислены. Можно продолжать играть.");
    }catch(error){if(claim)message(error.name==="AbortError"?"Нет подтверждения. Повтори — повторного начисления не будет.":error.message);}
    finally{clearTimeout(timer);if(claim)dailySending=false;controls();if(!document.hidden&&!pageSuspended)dailyTimer=setTimeout(()=>dailyRequest(),15000);}
  }
  $("daily")?.addEventListener("click",()=>dailyRequest(true));
  document.addEventListener("visibilitychange",()=>{clearTimeout(dailyTimer);if(!document.hidden)dailyRequest();});
  window.addEventListener("pagehide",()=>clearTimeout(dailyTimer));
  let master=null;const voices=new Set(),counters=new Map(),visualAnimations=new Set();
  let musicBuffer=null,musicSource=null,musicGain=null,musicOffset=0,musicStarted=0;
  const musicButton=document.createElement("button");
  musicButton.type="button";musicButton.id="vegas-music";musicButton.textContent="♫ Музыка";
  musicButton.setAttribute("aria-label","Выключить музыку");musicButton.setAttribute("aria-pressed","true");
  page.querySelector(".vegas-toolbar>div").prepend(musicButton);
  let musicEnabled=true;
  // Original eight-bar casino lounge loop. A single sample-accurate looping
  // buffer, independent from win effects, timers and reel/cascade animations.
  function buildMusic(){
    const rate=22050,beat=60/112,length=Math.round(32*beat*rate);
    const buffer=audio.createBuffer(1,length,rate),out=buffer.getChannelData(0);
    const note=(start,duration,midi,volume,bright=false)=>{
      const first=Math.round(start*rate),count=Math.round(duration*rate),f=440*2**((midi-69)/12);
      for(let i=0;i<count;i++){
        const t=i/rate,envelope=Math.min(1,t/.012)*Math.min(1,(count-i)/(rate*.07))*Math.exp(-t*(bright?5:2));
        const phase=2*Math.PI*f*t;
        out[(first+i)%length]+=volume*envelope*(Math.sin(phase)+(bright?.28*Math.sin(phase*3):0));
      }
    };
    const chords=[[57,60,64,67],[62,65,69,72],[55,59,62,65],[60,64,67,71]];
    let seed=7127;const noise=()=>{seed=(1664525*seed+1013904223)>>>0;return seed/2147483648-1;};
    for(let bar=0;bar<8;bar++){
      const chord=chords[bar%4],base=bar*4*beat;
      chord.forEach(n=>{note(base,beat*1.3,n,.055);note(base+beat*2.5,beat*.8,n,.04);});
      for(let b=0;b<4;b++)note(base+b*beat,beat*.7,chord[0]-24+(b===3?7:0),.16);
      for(let step=0;step<8;step++)note(base+(step*.5+(step%2?.08:0))*beat,beat*.34,chord[(step+bar)%4]+12,.045,true);
      for(let step=0;step<8;step++){
        const first=Math.round((base+step*.5*beat)*rate),count=Math.round(rate*.055);
        for(let i=0;i<count;i++)out[(first+i)%length]+=noise()*.035*Math.exp(-i/(rate*.009));
      }
      for(let b=0;b<4;b++){
        const first=Math.round((base+b*beat)*rate);
        for(let i=0;i<rate*.13;i++){const t=i/rate;out[(first+i)%length]+=.13*Math.sin(2*Math.PI*(55*t+5*(1-Math.exp(-t*30))))*Math.exp(-t*35);}
      }
    }
    return buffer;
  }
  function startMusic(){
    if(!musicEnabled||!audio||document.hidden||musicSource)return;
    musicBuffer ||= buildMusic();musicGain ||= audio.createGain();musicGain.gain.value=.5;musicGain.connect(master);
    musicSource=audio.createBufferSource();musicSource.buffer=musicBuffer;musicSource.loop=true;musicSource.connect(musicGain);
    musicStarted=audio.currentTime;musicSource.start(0,musicOffset%musicBuffer.duration);
    machine.dataset.music="playing";
  }
  function stopMusic(){
    if(!musicSource)return;
    musicOffset=(musicOffset+audio.currentTime-musicStarted)%musicBuffer.duration;
    musicSource.stop();musicSource.disconnect();musicSource=null;musicGain.disconnect();machine.dataset.music="paused";
  }
  musicButton.addEventListener("click",()=>{
    musicEnabled=!musicEnabled;musicButton.setAttribute("aria-pressed",String(musicEnabled));
    musicButton.textContent=musicEnabled?"♫ Музыка":"♫ Без музыки";
    musicButton.setAttribute("aria-label",musicEnabled?"Выключить музыку":"Включить музыку");
    if(musicEnabled)unlockAudio(true);else stopMusic();
  });
  page.addEventListener("pointerdown",()=>unlockAudio(true),{once:true});
  function animate(el,frames,options){
    const animation=el.animate(frames,options);visualAnimations.add(animation);
    animation.finished.then(()=>visualAnimations.delete(animation),()=>visualAnimations.delete(animation));return animation;
  }
  let current=cfg.last?.rounds?.at(-1)?.grid||cfg.last_purchase?.grid||Array.from({length:5},(_,c)=>Array.from({length:4},(_,r)=>cfg.symbols[(c*3+r)%cfg.symbols.length].key));
  const columns=Array.from({length:5},()=>{const column=document.createElement("div"),track=document.createElement("div");column.className="vegas-reel is-stopped";track.className="vegas-reel-track";column.append(track);reels.append(column);return{column,track,pool:[]};});
  function cell(key){
    const el=document.createElement("div"),art=document.createElement("span"),label=document.createElement("small");
    el.className="vegas-cell";art.setAttribute("aria-hidden","true");
    el.append(art,label);updateCell(el,key);return el;
  }
  function updateCell(el,key){
    if(el.dataset.symbol===key)return;
    el.dataset.symbol=key;el.setAttribute("aria-label",symbols.get(key).name);
    el.children[0].className=`vegas-symbol-art vegas-art-${key}`;el.children[1].textContent=labels[key];
  }
  function column(c,values,duplicate=false){
    const {track,pool}=columns[c],next=(duplicate?values.concat(values):values).map((key,index)=>{
      const el=pool[index]||(pool[index]=cell(key));updateCell(el,key);return el;
    });
    if(track.children.length!==next.length)track.replaceChildren(...next);
  }
  function grid(values){values.forEach((v,c)=>column(c,v));current=values;}
  function message(text){$("message").textContent=text;}
  function unlockAudio(gesture=false){
    if(!sound||document.hidden)return;
    try{
      if(!audio){
        if(!gesture&&!navigator.userActivation?.isActive)return;
        const Audio=window.AudioContext||window.webkitAudioContext;if(!Audio)return;
        audio=new Audio();master=audio.createGain();master.gain.value=.18;
        const limiter=audio.createDynamicsCompressor();limiter.threshold.value=-18;limiter.ratio.value=5;
        master.connect(limiter);limiter.connect(audio.destination);
      }
      if(audio.state!=="running")audio.resume().catch(()=>{});
      startMusic();
    }catch{/* Sound cannot block a server request. */}
  }
  function stopAudio(){stopMusic();for(const voice of voices){try{voice.stop();}catch{}}voices.clear();}
  function tone(f,delay=0,length=.1,type="sine",volume=.2){
    if(!sound||!audio||audio.state!=="running"||document.hidden||voices.size>=24)return;
    const o=audio.createOscillator(),g=audio.createGain(),t=audio.currentTime+delay;
    o.type=type;o.frequency.value=f;
    g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(volume,t+.008);g.gain.exponentialRampToValueAtTime(.0001,t+length);
    o.connect(g);g.connect(master);voices.add(o);machine.dataset.soundVoices=String(voices.size);
    o.onended=()=>{voices.delete(o);o.disconnect();g.disconnect();machine.dataset.soundVoices=String(voices.size);};
    o.start(t);o.stop(t+length);
  }
  function cue(kind,step=0){
    const melodies={line:[659.25,783.99,987.77],cascade:[523.25,659.25,783.99,1046.5],bonus:[392,493.88,587.33,783.99,987.77,1174.66],summary:[523.25,659.25,783.99,1046.5,1318.51]};
    const notes=melodies[kind]||melodies.line;machine.dataset.soundCue=kind;
    notes.forEach((f,i)=>{const pitch=f*(kind==="line"?2**(Math.min(step,3)/12):1);tone(pitch,i*.065,kind==="line"?.2:.36,"sine",.22);tone(pitch/2,i*.065,.2,"triangle",.09);});
  }
  function setAmount(el,value){cancelAnimationFrame(counters.get(el));counters.delete(el);el.dataset.value=String(value);el.textContent=money(value);}
  function countAmount(el,target){
    cancelAnimationFrame(counters.get(el));const from=Number(el.dataset.value)||0,born=performance.now();
    if(reduced.matches||!fxEnabled||document.hidden){setAmount(el,target);return;}
    function tick(now){const t=Math.min(1,(now-born)/440),v=Math.round(from+(target-from)*(1-(1-t)**3));el.dataset.value=String(v);el.textContent=money(v);if(t<1)counters.set(el,requestAnimationFrame(tick));else counters.delete(el);}
    counters.set(el,requestAnimationFrame(tick));
  }
  function queueBonus(){
    clearTimeout(autoTimer);autoTimer=0;
    if(autoPlay&&!state.free_spins&&!canAfford(cfg.bets[betIndex])){autoPlay=false;controls();message("Авто остановлено: недостаточно средств");}
    if((!state.free_spins&&!autoPlay)||busy||pending||(state.free_spins&&bonusPaused)||autoBlocked||document.hidden||pageSuspended||!$("celebration").hidden||$("purchase").open||$("auto-dialog").open||$("topup-dialog").open)return;
    const delay=Math.max(reduced.matches?160:550,(cfg.min_spin_interval_ms||0)+80-(performance.now()-lastRequestAt));
    autoTimer=setTimeout(()=>{autoTimer=0;request("spin",true);},delay);
  }
  $("bonus-pause").addEventListener("click",()=>{unlockAudio(true);if(autoBlocked){request();return;}bonusPaused=!bonusPaused;controls();queueBonus();});
  document.addEventListener("visibilitychange",()=>{if(document.hidden){autoPlay=false;controls();clearTimeout(autoTimer);stopAudio();}else{unlockAudio();queueBonus();}});
  window.addEventListener("pagehide",()=>{pageSuspended=true;autoPlay=false;controls();clearTimeout(autoTimer);stopAudio();});
  window.addEventListener("pageshow",()=>{pageSuspended=false;unlockAudio();queueBonus();});
  function controls(){
    dailyControls();
    $("topup").disabled=busy||!!pending;
    if(displayedBalance!==state.balance){displayedBalance=state.balance;document.dispatchEvent(new CustomEvent("vegas:balance",{detail:{balance:state.balance}}));}
    $("shop").setAttribute("aria-disabled",String(busy||!!pending));
    $("auto").setAttribute("aria-pressed",String(autoPlay));
    $("auto").querySelector("span").textContent=autoPlay?`СТОП${Number.isFinite(autoRemaining)?` · ${autoRemaining}`:""}`:"АВТО";
    $("auto").setAttribute("aria-label",autoPlay?`Остановить автопрокрутку${Number.isFinite(autoRemaining)?`, осталось ${autoRemaining}`:""}`:"Выбрать количество автопрокрутов");
    $("auto").dataset.remaining=autoPlay?String(autoRemaining):"0";
    $("auto").disabled=!autoPlay&&(busy||!!pending||state.free_spins>0||!canAfford(cfg.bets[betIndex]));
    $("balance").textContent=unlimited?"∞":money(state.balance);$("free").textContent=state.free_spins;
    if(unlimited)$("balance").setAttribute("aria-label","Неограниченный тестовый баланс");
    $("bet").textContent=money(state.free_spins?state.bonus_bet:cfg.bets[betIndex]);$("spin").disabled=busy||autoPlay||dailySending;
    $("spin").querySelector("span").textContent=busy?"СПИН…":pending?"ПОВТОРИТЬ":state.free_spins?"FREE SPIN":"КРУТИТЬ";
    $("minus").disabled=autoPlay||busy||!!pending||state.free_spins>0||betIndex===0;
    $("plus").disabled=autoPlay||busy||!!pending||state.free_spins>0||betIndex===cfg.bets.length-1;
    if($("reset"))$("reset").disabled=autoPlay||busy||!!pending;if($("scenario"))$("scenario").disabled=autoPlay||busy||!!pending;
    const hud=$("bonus-hud"),visible=state.bonus.granted>0,changed=hud.hidden===visible;
    hud.hidden=!visible;hud.classList.toggle("is-complete",visible&&!state.free_spins);machine.classList.toggle("has-bonus-hud",visible);
    setAmount($("bonus-total"),state.bonus.win);
    $("bonus-progress").textContent=`${state.bonus.played} / ${state.bonus.granted} вращений${autoBlocked?" · ошибка сети":bonusPaused?" · пауза":""}`;
    $("bonus-pause").hidden=!state.free_spins;$("bonus-pause").textContent=autoBlocked?"Повторить":bonusPaused?"Продолжить":"Пауза";$("bonus-pause").setAttribute("aria-pressed",String(bonusPaused));
    $("win-label").textContent=visible?"ЗА СПИН":"ВЫИГРЫШ";
    if(changed)scheduleFit();
    const retry=pending?.action==="buy_bonus",stake=retry?pending.bet:cfg.bets[betIndex],cost=stake*cfg.bonus_buy.multiplier;
    $("buy").disabled=autoPlay||busy||state.free_spins>0||(!retry&&(!!pending||!canAfford(cost)));
    $("buy-label").textContent=state.free_spins?"БОНУС АКТИВЕН":retry?"ПОВТОРИТЬ ПОКУПКУ":"КУПИТЬ БОНУС";
    $("buy-count").textContent=state.free_spins||cfg.bonus_buy.spins;
    $("buy-caption").textContent=state.free_spins?"ОСТАЛОСЬ":"FREE SPINS";
    $("buy-price").textContent=state.free_spins?money(state.bonus_bet):money(cost);
    $("buy-note").textContent=state.free_spins?"СТАВКА СЕРИИ":!canAfford(cost)&&!retry?"НЕДОСТАТОЧНО СРЕДСТВ":`${cfg.bonus_buy.multiplier}× ставка`;
    $("buy").setAttribute("aria-label",state.free_spins?`Бонус активен, осталось ${state.free_spins} вращений`:`${retry?"Повторить покупку":"Купить"} ${cfg.bonus_buy.spins} бесплатных вращений за ${money(cost)}`);
    machine.classList.toggle("is-bonus",state.free_spins>0);machine.setAttribute("aria-busy",String(busy));
    if(cfg.closed){for(const id of ["spin","auto","buy","topup","bonus-pause","minus","plus"])$(id).disabled=true;message("Зачёт завершён. Баланс зафиксирован на дедлайн.");}
  }
  // Responsive stage: size the field against BOTH viewport axes. No scale()
  // transforms, distorted tiles, polling loop, or scroll-blocking touch handlers.
  let inlineWidth=0,inlineHeight=0;
  function fitStage(){
    const full=page.classList.contains("is-fullscreen"),safe=full?getComputedStyle(page):null;
    const height=(window.visualViewport?.height||innerHeight)-(safe?(parseFloat(safe.paddingTop)||0)+(parseFloat(safe.paddingBottom)||0):0);
    const wide=machine.clientWidth>=700||(innerWidth>=650&&height<500);
    machine.classList.toggle("is-wide",wide);
    const dailyPanel=machine.querySelector(".vegas-daily");
    if(dailyPanel){
      const host=wide&&height<500?machine.querySelector(".vegas-toolbar>div"):machine.querySelector(".vegas-console");
      if(dailyPanel.parentElement!==host)host.append(dailyPanel);
    }
    // Measure the control rows at usable width, not at the previous small
    // board width (which otherwise feeds text wrapping back into the fitter).
    machine.style.setProperty("--cabinet-width",`${machine.clientWidth-24}px`);
    const h=selector=>machine.querySelector(selector)?.getBoundingClientRect().height||0;
    if(!full){
      if(inlineWidth!==innerWidth){inlineWidth=innerWidth;inlineHeight=height;}
      inlineHeight=Math.min(inlineHeight,height);
    }
    const outside=full?0:Math.max(0,machine.getBoundingClientRect().top+scrollY)+(document.querySelector(".nightshift-mobile-nav")?.getBoundingClientRect().height||0)+12;
    const side=innerWidth>700||(innerWidth>=650&&innerHeight<=500)?128:0;
    const overhead=h(".vegas-toolbar")+h(".vegas-marquee")+h(".vegas-announcer")+h(".vegas-console")+h(".vegas-balances")+(side?0:h(".vegas-bonus-panel")+8)+24;
    const maxWidth=Math.max(180,machine.clientWidth-24-side);
    const board=Math.floor(Math.min(full?750:560,maxWidth,Math.max(full?(wide?60:100):40,(full?height:inlineHeight)-outside-overhead)*1.25));
    machine.style.setProperty("--board-size",`${board}px`);
    // The bottom control bar stays comfortably wide even in a short viewport.
    machine.style.setProperty("--cabinet-width",`${wide?Math.min(machine.clientWidth-24,Math.max(board+side,580)):machine.clientWidth-24}px`);
  }
  let fitFrame=0;
  function scheduleFit(){cancelAnimationFrame(fitFrame);fitFrame=requestAnimationFrame(fitStage);}
  window.addEventListener("resize",scheduleFit);window.visualViewport?.addEventListener("resize",scheduleFit);
  const resizeObserver=new ResizeObserver(entries=>{
    const width=Math.round(entries[0].contentRect.width);
    if(resizeObserver.lastWidth!==width){resizeObserver.lastWidth=width;scheduleFit();}
  });resizeObserver.observe(machine);

  // Two bounded bursts. Flame textures are painted once, then composited as
  // small sprites; no gradients, blur filters or DOM particles per frame.
  const fxCanvas=$("fx"), fxContext=fxCanvas.getContext("2d");
  fxCanvas.dataset.active="false";
  let fxEnabled=true, fxFrame=0, fxBursts=[], fxWidth=0, fxHeight=0, fxRatio=1, edgeTimer=0;
  let flameSheet=null,lastFxPaint=0,fxInterval=16,fxDrawCount=0;
  function fireTexture(){
    if(flameSheet)return flameSheet;
    flameSheet=document.createElement("canvas");flameSheet.width=240;flameSheet.height=192;
    const ctx=flameSheet.getContext("2d");
    for(let variant=0;variant<3;variant++){
      ctx.save();ctx.translate(variant*80,0);
      const outer=ctx.createLinearGradient(0,192,0,0);
      outer.addColorStop(0,"#fff0a4");outer.addColorStop(.23,"#ffb62e");outer.addColorStop(.55,"#ff5217");outer.addColorStop(1,"#d92c1000");
      ctx.fillStyle=outer;ctx.beginPath();ctx.moveTo(11,192);
      ctx.bezierCurveTo(-6,142,53,106,25+variant*8,12);
      ctx.bezierCurveTo(80,55,50,116,69,140);ctx.bezierCurveTo(90,175,59,192,11,192);ctx.fill();
      const core=ctx.createLinearGradient(0,192,0,70);
      core.addColorStop(0,"#fffbe1");core.addColorStop(.45,"#ffdc5b");core.addColorStop(1,"#ffb12b00");
      ctx.fillStyle=core;ctx.beginPath();ctx.moveTo(25,192);ctx.bezierCurveTo(10,154,57,132,45,75);ctx.bezierCurveTo(73,127,49,143,60,168);ctx.bezierCurveTo(66,190,47,192,25,192);ctx.fill();ctx.restore();
    }
    return flameSheet;
  }
  function stopFX(){
    cancelAnimationFrame(fxFrame);fxFrame=0;fxBursts=[];clearTimeout(edgeTimer);
    machine.classList.remove("is-fire");
    fxContext?.clearRect(0,0,fxWidth,fxHeight);fxCanvas.dataset.active="false";fxCanvas.dataset.frames=String(fxDrawCount);
  }
  function stopTransient(){
    stopFX();for(const animation of visualAnimations)animation.cancel();visualAnimations.clear();
    for(const [el,frame] of counters){cancelAnimationFrame(frame);counters.delete(el);}
  }
  function paintFX(now){
    fxBursts=fxBursts.filter(b=>now-b.born<b.duration);
    if(!fxEnabled||reduced.matches||document.hidden||!fxBursts.length){stopFX();return;}
    if(now-lastFxPaint<fxInterval){fxFrame=requestAnimationFrame(paintFX);return;}
    lastFxPaint=now;fxDrawCount++;
    const ctx=fxContext;ctx.clearRect(0,0,fxWidth,fxHeight);
    for(const burst of fxBursts){
      const t=Math.max(0,(now-burst.born)/burst.duration),fade=Math.min(1,t*8)*Math.min(1,(1-t)*4);
      ctx.save();ctx.globalAlpha=Math.max(0,fade);ctx.globalCompositeOperation="lighter";
      // Flames stay at cell borders, so faces and line labels remain legible.
      for(const [col,row]of burst.cells){
        const x=col*fxWidth/5+3,y=row*fxHeight/4+3,cw=fxWidth/5-6,ch=fxHeight/4-6;
        for(let n=0;n<3;n++){
          const pulse=.8+.2*Math.sin(now*.015+n*2+col+burst.seed);
          const fh=ch*(n===1?.35:burst.pepper?1.15:.7)*pulse;
          const fw=cw*(n===1?.3:.48),px=x+cw*(.08+n*.42)-fw/2;
          ctx.drawImage(fireTexture(),((n+col)%3)*80,0,80,192,px,y+ch-fh,fw,fh);
        }
      }
      for(let n=0;n<12;n++){
        const x=(n+.5)*fxWidth/12,w=fxWidth/10,h=fxHeight*(.07+.06*(1+Math.sin(n*1.7+now*.012+burst.seed)))*(burst.pepper?1.2:1);
        ctx.drawImage(fireTexture(),(n%3)*80,0,80,192,x-w/2,fxHeight-h,w,h);
      }
      for(let n=0;n<24;n++){
        const [c,r]=burst.cells[n%burst.cells.length],angle=n*2.4+burst.seed,travel=t*(18+n*2);
        const x=(c+.5)*fxWidth/5+Math.cos(angle)*travel,y=(r+.7)*fxHeight/4+Math.sin(angle)*travel-t*(burst.pepper?100:35);
        ctx.fillStyle=n%3?"#ff9c36":"#fff4ad";ctx.fillRect(x,y,1.8,Math.max(2,6*(1-t)));
      }
      ctx.restore();
    }
    fxFrame=requestAnimationFrame(paintFX);
  }
  function fireFX(cells,pepper=false){
    if(!fxContext||!fxEnabled||reduced.matches||document.hidden||!cells.length)return;
    const box=$("board").getBoundingClientRect();fxWidth=box.width;fxHeight=box.height;
    const mobile=innerWidth<650||matchMedia("(pointer:coarse)").matches;
    fxRatio=Math.min(devicePixelRatio||1,mobile?1.25:1.5);fxInterval=mobile?30:15;
    const w=Math.round(fxWidth*fxRatio),h=Math.round(fxHeight*fxRatio);
    if(fxCanvas.width!==w||fxCanvas.height!==h){fxCanvas.width=w;fxCanvas.height=h;fxContext.setTransform(fxRatio,0,0,fxRatio,0,0);}
    const unique=[...new Map(cells.map(pos=>[pos.join(","),pos])).values()].slice(0,8);
    if(!fxFrame){fxDrawCount=0;lastFxPaint=0;}
    const duration=pepper?1200:900;
    fxBursts.push({cells:unique,pepper,duration,born:performance.now(),seed:Math.random()*20});fxBursts=fxBursts.slice(-2);
    machine.classList.add("is-fire");
    clearTimeout(edgeTimer);edgeTimer=setTimeout(()=>machine.classList.remove("is-fire"),duration);
    fxCanvas.dataset.active="true";fxCanvas.dataset.effect="fire";fxCanvas.dataset.theme=pepper?"pepper":"fire";
    if(!fxFrame)fxFrame=requestAnimationFrame(paintFX);
  }
  reduced.addEventListener("change",()=>{if(reduced.matches)stopTransient();});
  document.addEventListener("visibilitychange",()=>{machine.classList.toggle("is-suspended",document.hidden);if(document.hidden)stopTransient();});
  window.addEventListener("pagehide",stopTransient);
  function clear(){svg.replaceChildren();$("particles").replaceChildren();reels.querySelectorAll(".is-winning,.is-exploding,.is-scatter").forEach(e=>e.classList.remove("is-winning","is-exploding","is-scatter"));}
  function line(win){
    svg.replaceChildren();const poly=document.createElementNS("http://www.w3.org/2000/svg","polyline");
    poly.setAttribute("points",win.rows.map((r,c)=>`${c*100+50},${r*100+50}`).join(" "));svg.append(poly);
    for(const[c,r]of win.cells){columns[c].track.children[r]?.classList.add("is-winning");const dot=document.createElementNS(poly.namespaceURI,"circle");dot.setAttribute("cx",c*100+50);dot.setAttribute("cy",r*100+50);dot.setAttribute("r",3);svg.append(dot);}
  }
  async function cascade(previous,next,wins){
    const removed=new Set(wins.flatMap(w=>w.cells.map(([c,r])=>`${c},${r}`)));
    for(const key of removed){const[c,r]=key.split(",").map(Number);columns[c].track.children[r]?.classList.add("is-exploding");}
    await pause(350);clear();const animations=[];
    for(let c=0;c<5;c++){
      const kept=previous[c].map((_,r)=>r).filter(r=>!removed.has(`${c},${r}`)),added=4-kept.length;column(c,next[c]);
      if(!reduced.matches&&!document.hidden){const height=columns[c].track.clientHeight/4;
        [...columns[c].track.children].forEach((el,r)=>{const d=r<added?-(added+1)*height:(kept[r-added]-r)*height;
          if(d)animations.push(animate(el,[{transform:`translateY(${d}px)`,opacity:r<added?.25:1},{transform:"translateY(0)",opacity:1}],{duration:260,delay:c*20,easing:"cubic-bezier(.2,.7,.2,1)"}).finished.catch(()=>{}));});}
    }
    current=next;await Promise.all(animations);
  }
  function callout(label,value,kind="line"){
    if(!fxEnabled||document.hidden)return;
    const el=$("win-callout");$("callout-label").textContent=label;$("callout-value").textContent=value;el.dataset.kind=kind;
    for(const a of el.getAnimations())a.cancel();
    animate(el,reduced.matches?[{opacity:1},{opacity:0}]:[{opacity:0,transform:"translateY(8px) scale(.9)"},{opacity:1,transform:"translateY(0) scale(1.03)",offset:.2},{opacity:1,transform:"translateY(0) scale(1)",offset:.7},{opacity:0,transform:"translateY(-6px) scale(1)"}],{duration:reduced.matches?240:950,easing:"ease-out"});
  }
  function celebration(title,value,copy,kicker="VEGAS PIT",{autoMs=0,kind="win"}={}){
    $("celebration-kicker").textContent=kicker;$("celebration-title").textContent=title;$("celebration-value").textContent=value;$("celebration-copy").textContent=copy;
    const overlay=$("celebration"),button=$("celebration-close");overlay.dataset.kind=kind;button.textContent=autoMs&&kind==="entry"?"Начать бонус":"Продолжить";
    $("celebration-art").className=`vegas-symbol-art vegas-art-${kind==="entry"?"scatter":"wild"}`;
    overlay.hidden=false;overlay.setAttribute("aria-labelledby","vegas-celebration-title");overlay.showModal();
    const inert=[...page.children].filter(el=>el!==machine).concat([...machine.children].filter(el=>el!==overlay));inert.forEach(el=>el.inert=true);button.focus();
    return new Promise(resolve=>{
      let done=false,timer=0;
      function finish(){if(done)return;done=true;clearTimeout(timer);overlay.close();overlay.hidden=true;inert.forEach(el=>el.inert=false);button.removeEventListener("click",finish);overlay.removeEventListener("keydown",keys);overlay.removeEventListener("cancel",cancel);resolve();}
      function cancel(e){e.preventDefault();finish();}
      function keys(e){if(e.key==="Escape"){e.preventDefault();e.stopPropagation();finish();}if(e.key==="Tab"){e.preventDefault();button.focus();}}
      button.addEventListener("click",finish);overlay.addEventListener("keydown",keys);overlay.addEventListener("cancel",cancel);
      if(autoMs)timer=setTimeout(finish,reduced.matches&&kind==="entry"?300:autoMs);
    });
  }
  async function stopReels(field){
    await pause(420);
    let scatters=0;
    for(let c=0;c<5;c++){
      const suspense=scatters===2&&!reduced.matches&&!document.hidden;
      if(suspense){
        columns[c].column.classList.add("is-anticipating");
        message("Два Scatter уже есть… ждём барабан!");
        for(let pulse=0;pulse<3;pulse++){tone(440+pulse*110,0,.1,"triangle",.10);await pause(280);}
      }
      columns[c].column.classList.remove("is-anticipating");
      columns[c].column.classList.add("is-stopped");column(c,field[c]);
      scatters+=field[c].filter(key=>key==="scatter").length;
      tone(240+c*70,0,.055);await pause(110);
    }
    machine.classList.remove("is-spinning");current=field;
  }
  async function presentPurchase(data){
    const purchase=data.bonus_purchase;await stopReels(purchase.grid);
    state=data.state;controls();$("multiplier").textContent="×2";
    const cells=[];purchase.grid.forEach((col,c)=>col.forEach((key,r)=>{if(key==="scatter"){columns[c].track.children[r].classList.add("is-scatter");cells.push([c,r]);}}));
    fireFX(cells);cue("bonus");callout("БОНУС КУПЛЕН",`${purchase.spins} FREE SPINS`,"bonus");
    await celebration("БОНУС КУПЛЕН",`${purchase.spins} FREE SPINS`,`Стоимость ${money(purchase.cost)} · ставка ${money(purchase.bet)}. Вращения начнутся автоматически.`,"VEGAS PIT · BONUS BUY",{autoMs:2000,kind:"entry"});
    message(`Бесплатных вращений: ${state.free_spins} · ставка не списывается`);
  }
  async function present(data,automatic=false){
    const result=data.result,first=result.rounds[0],bonusBefore=state.bonus.win;await stopReels(first.grid);let total=0;
    for(const[i,round]of result.rounds.entries()){
      if(i)await cascade(result.rounds[i-1].grid,round.grid,result.rounds[i-1].wins);
      $("multiplier").textContent=`×${round.multiplier}`;if(!round.wins.length)break;
      total+=round.amount;countAmount($("win"),total);if(result.free)countAmount($("bonus-total"),bonusBefore+total);
      const pepperWins=round.wins.filter(w=>w.symbol==="toto");
      const pepperCells=[...new Map(pepperWins.flatMap(w=>w.cells).map(pos=>[pos.join(","),pos])).values()];
      if(pepperWins.length||round.multiplier>=3||round.amount>=result.bet*8)fireFX(pepperWins.length?pepperCells:round.wins.flatMap(w=>w.cells),!!pepperWins.length);
      if(pepperWins.length&&!reduced.matches&&!document.hidden){
        for(const [c,r] of pepperCells){
          const el=columns[c].track.children[r];if(el?.dataset.symbol!=="toto")continue;
          animate(el.children[0],[{transform:"scale(1)"},{transform:"translateY(-3px) scale(1.07)",offset:.4},{transform:"scale(1)"}],{duration:700,easing:"ease-out"});
        }
      }
      for(const win of round.wins.slice(0,2)){clear();line(win);message(`Линия ${win.line} · ${symbols.get(win.symbol).name} ×${win.count} · +${money(win.amount)}`);cue("line",i);await pause(170);}
      callout(pepperWins.length?"ПЕРЧИК ЖЖЁТ!":round.multiplier>1?`КАСКАД ×${round.multiplier}`:"ВЫИГРЫШ",`+${money(round.amount)}`,pepperWins.length?"fire":"line");if(i)cue("cascade");
      round.wins.flatMap(w=>w.cells).forEach(([c,r])=>columns[c].track.children[r]?.classList.add("is-winning"));message(`${round.wins.length} выигрышных линий · каскад +${money(round.amount)}`);await pause(280);
    }
    state=data.state;if(state.free_spins)autoPlay=false;controls();setAmount($("win"),result.payout);
    if(result.bonus_adjustment){callout("ВОЗВРАТ БОНУСА",`+${money(result.bonus_adjustment)}`,"bonus");await pause(700);}
    if(result.awarded){
      reels.querySelectorAll('[data-symbol="scatter"]').forEach(el=>el.classList.add("is-scatter"));cue("bonus");
      if(result.free){callout("ЕЩЁ КРУГИ!",`+${result.awarded} FREE SPINS`,"bonus");await pause(800);}
      else await celebration("БОНУСНЫЙ СТИНТ",`+${result.awarded} FREE SPINS`,`Ставка ${money(state.bonus_bet)} зафиксирована. Вращения начнутся автоматически.`,"SCATTER · VEGAS",{autoMs:2000,kind:"entry"});
    }else if(result.payout>=result.bet*8){
      if(result.free){callout(result.payout>=result.bet*25?"MEGA WIN":"BIG WIN",money(result.payout),"bonus");cue("cascade");await pause(700);}
      else{cue("summary");await celebration(result.payout>=result.bet*25?"MEGA WIN":"BIG WIN",money(result.payout),"Все выигрышные линии зачислены на игровой баланс.","VEGAS PIT",{autoMs:automatic?2500:0});}
    }
    if(result.free&&!state.free_spins){cue("summary");await celebration("БОНУС ЗАВЕРШЁН",money(state.bonus.win),`Общий выигрыш за ${state.bonus.played} вращений. Вся сумма уже на игровом балансе.`,"ИТОГ БОНУСНОГО СТИНТА",{kind:"summary"});}
    message(result.free&&!state.free_spins?"Бонусный стинт завершён":state.free_spins?`Бесплатных вращений: ${state.free_spins} · ставка не списывается`:result.payout?`На баланс зачислено ${money(result.payout)}`:"Нет выигрышных комбинаций");
  }
  async function request(action="spin",automatic=false){
    if(dailySending)return;
    if(busy||!$("celebration").hidden||$("purchase").open||$("auto-dialog").open||$("topup-dialog").open||(!automatic&&autoPlay&&action==="spin"))return;
    if(automatic&&((!state.free_spins&&!autoPlay)||(state.free_spins&&bonusPaused)||autoBlocked||document.hidden||pageSuspended))return;
    if(action!=="spin")autoPlay=false;
    clearTimeout(autoTimer);autoTimer=0;
    if(!automatic&&action==="spin"&&state.free_spins)bonusPaused=false;
    if(action==="reset"&&!confirm("Сбросить только свой тестовый баланс и бесплатные вращения?")){queueBonus();return;}
    if(cfg.closed)return;
    if(!pending)pending={request_id:crypto.randomUUID(),revision:state.revision,bet:cfg.bets[betIndex],scenario:action==="buy_bonus"?"random":($("scenario")?.value||"random"),action,...(cfg.wallet_id?{wallet_id:cfg.wallet_id}:{})};
    const paidAuto=automatic&&autoPlay&&!state.free_spins&&pending.action==="spin";
    let seriesComplete=false;
    busy=true;stopTransient();clear();controls();setAmount($("win"),0);message(pending.action==="reset"?"Сбрасываем тестовый баланс…":pending.action==="buy_bonus"?"Открываем бонусный стинт…":"Барабаны вращаются…");
    if(pending.action!=="reset"){columns.forEach(({column:el},c)=>{column(c,current[c],true);el.classList.remove("is-stopped");});machine.classList.add("is-spinning");}
    try{
      unlockAudio(!automatic);
      const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000);let response;
      try{lastRequestAt=performance.now();response=await fetch(cfg.spin_url,{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json","X-CSRFToken":page.querySelector('[name="csrfmiddlewaretoken"]').value},body:JSON.stringify(pending),signal:controller.signal});}finally{clearTimeout(timer);}
      let data;try{data=await response.json();}catch{throw new Error("Сервер не подтвердил результат. Повтори запрос — новая ставка не спишется.");}
      if(!response.ok){if(data.state){state=data.state;pending=null;}if(data.closed){cfg.closed=true;autoPlay=false;}if(response.status===400||response.status===403)pending=null;throw new Error(data.error||"Не удалось выполнить прокрутку.");}
      pending=null;autoBlocked=false;
      if(paidAuto&&autoPlay&&Number.isFinite(autoRemaining)){
        autoRemaining--;if(autoRemaining===0){autoPlay=false;seriesComplete=true;}
      }
      if(data.bonus_purchase){await presentPurchase(data);}
      else if(data.result){await present(data,automatic);}
      else{state=data.state;bonusPaused=false;message("Тестовый баланс сброшен до $5 000");$("multiplier").textContent="×1";}
      if($("scenario"))$("scenario").value="random";
      if(seriesComplete&&!state.free_spins)message(`Серия из ${autoCount} вращений завершена`);
    }catch(error){autoPlay=false;autoBlocked=true;message(error.name==="AbortError"?"Нет подтверждения сервера. Повтори запрос — без повторного списания.":error.message);}
    finally{machine.classList.remove("is-spinning");columns.forEach(({column:el,track},c)=>{el.classList.remove("is-anticipating");el.classList.add("is-stopped");if(track.children.length!==4)column(c,current[c]);});busy=false;controls();if(!automatic)$("spin").focus({preventScroll:true});queueBonus();}
  }
  function autoQuote(){
    for(const option of page.querySelectorAll("[data-auto-count]"))option.setAttribute("aria-pressed",String(Number(option.dataset.autoCount)===autoCount));
    $("auto-quote").textContent=unlimited?`${autoCount?`${autoCount} вращений`:"Без ограничения вращений"} · без списания тестового баланса`:autoCount?`${autoCount} вращений · ${money(cfg.bets[betIndex]*autoCount)} при текущей ставке`:`Ставка ${money(cfg.bets[betIndex])} за вращение`;
    $("auto-start").textContent=autoCount?`Запустить ${autoCount}`:"Запустить";
  }
  $("auto").addEventListener("click",()=>{
    if(autoPlay){autoPlay=false;clearTimeout(autoTimer);controls();return;}
    if(busy||pending||state.free_spins)return;
    autoQuote();$("auto-dialog").showModal();$("auto-cancel").focus();
  });
  for(const option of page.querySelectorAll("[data-auto-count]"))option.addEventListener("click",()=>{autoCount=Number(option.dataset.autoCount);autoQuote();});
  $("auto-cancel").addEventListener("click",()=>$("auto-dialog").close());
  document.addEventListener("vegas:topup-open",()=>{autoPlay=false;clearTimeout(autoTimer);controls();});
  document.addEventListener("vegas:topup-close",queueBonus);
  document.addEventListener("vegas:closed",()=>{cfg.closed=true;autoPlay=false;clearTimeout(autoTimer);controls();});
  document.addEventListener("vegas:topup-state",event=>{
    const incoming=event.detail;
    if(!busy&&!pending&&incoming.revision>=state.revision){state=incoming;controls();}
  });
  $("auto-start").addEventListener("click",()=>{
    $("auto-dialog").close();autoRemaining=autoCount||Infinity;autoPlay=true;autoBlocked=false;unlockAudio(true);controls();queueBonus();
  });
  $("spin").addEventListener("click",()=>request());$("reset")?.addEventListener("click",()=>request("reset"));
  function closePurchase(){const dialog=$("purchase");dialog.close();dialog.hidden=true;}
  $("buy").addEventListener("click",()=>{
    if(pending?.action==="buy_bonus"){request();return;}
    if(busy||pending||state.free_spins||!$("celebration").hidden)return;
    const stake=cfg.bets[betIndex],cost=stake*cfg.bonus_buy.multiplier;if(!canAfford(cost))return;
    $("purchase-bet").textContent=money(stake);$("purchase-cost").textContent=money(cost);$("purchase-balance").textContent=unlimited?"∞":money(state.balance-cost);$("purchase-spins").textContent=cfg.bonus_buy.spins;
    $("purchase-confirm").textContent=`Купить за ${money(cost)}`;
    $("purchase").hidden=false;$("purchase").showModal();$("purchase-cancel").focus();
  });
  $("purchase-cancel").addEventListener("click",closePurchase);
  $("purchase").addEventListener("cancel",e=>{e.preventDefault();closePurchase();});
  $("purchase-confirm").addEventListener("click",()=>{closePurchase();request("buy_bonus");});
  $("minus").addEventListener("click",()=>{betIndex=Math.max(0,betIndex-1);controls();});$("plus").addEventListener("click",()=>{betIndex=Math.min(cfg.bets.length-1,betIndex+1);controls();});
  let oldOverflow="";
  function fullscreen(on){if(on){oldOverflow=document.body.style.overflow;document.body.style.overflow="hidden";}else document.body.style.overflow=oldOverflow;page.classList.toggle("is-fullscreen",on);$("fullscreen").setAttribute("aria-pressed",String(on));scheduleFit();}
  $("fullscreen").addEventListener("click",()=>fullscreen(!page.classList.contains("is-fullscreen")));
  $("shop").addEventListener("click",e=>{if(busy||pending){e.preventDefault();message("Дождись подтверждения текущего вращения");return;}autoPlay=false;clearTimeout(autoTimer);controls();});
  $("exit").addEventListener("click",()=>{autoPlay=false;clearTimeout(autoTimer);stopAudio();stopTransient();});
  document.addEventListener("keydown",e=>{
    if(e.key==="Escape"&&page.classList.contains("is-fullscreen")&&$("celebration").hidden&&!$("purchase").open&&!$("auto-dialog").open&&!$("topup-dialog").open)fullscreen(false);
    if(e.code!=="Space"&&e.key!==" ")return;
    if(e.isComposing||e.ctrlKey||e.altKey||e.metaKey||e.defaultPrevented)return;
    if(!$("celebration").hidden||$("purchase").open||$("auto-dialog").open||$("topup-dialog").open||e.target.closest('input,textarea,select,[contenteditable]:not([contenteditable="false"])'))return;
    // Works from the initial body focus and every game button. Suppress native
    // button activation/scrolling, including held-key repeats, to send one spin.
    e.preventDefault();if(!e.repeat)request();
  });
  grid(current);controls();fitStage();dailyRequest();if(cfg.last)setAmount($("win"),cfg.last.payout);else if(state.free_spins)$("multiplier").textContent="×2";queueBonus();
})();
