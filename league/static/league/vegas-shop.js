/* Server-owned purchases and single-use event inventory; lab stays read-only. */
(() => {
  "use strict";
  const root=document.getElementById("casino-shop");if(!root)return;
  document.body.append(root);document.body.classList.add("casino-shop-open");
  const $=id=>document.getElementById(`shop-${id}`);
  const products=new Map(JSON.parse($("products").textContent).map(p=>[p.key,p]));
  const unlimited=JSON.parse($("unlimited").textContent)===true;
  $("balance").textContent=unlimited?"∞":new Intl.NumberFormat("ru-RU",{style:"currency",currency:"USD",maximumFractionDigits:2}).format(JSON.parse($("wallet").textContent)/100);
  if(unlimited)$("balance").setAttribute("aria-label","Неограниченный тестовый баланс");
  const dialog=$("product-dialog"),tip=$("tooltip"),hover=matchMedia("(hover:hover) and (pointer:fine)"),motion=matchMedia("(prefers-reduced-motion: reduce)");
  let active=null,tipTarget=null;
  const cfg=JSON.parse($("config").textContent),targeted=new Set(["wheel","teamorder","constructors"]);
  let inventory=cfg,sending=false;
  const date=value=>new Intl.DateTimeFormat("ru-RU",{timeZone:"Europe/Moscow",day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}).format(new Date(value))+" МСК";
  function refreshInventory(body){
    if(inventory&&body.state.revision<inventory.state.revision)return;
    inventory=body;
    $("balance").textContent=new Intl.NumberFormat("ru-RU",{style:"currency",currency:"USD",maximumFractionDigits:2}).format(body.state.balance/100);
    for(const [key,item] of Object.entries(body.items)){
      const label=root.querySelector(`[data-item-state="${key}"]`);
      if(label)label.textContent=item.applied?"ПРИМЕНЕНО":item.owned?"КУПЛЕНО":"";
    }
    const selected=$("league").value;
    $("league").replaceChildren(...body.leagues.map(league=>{const option=document.createElement("option");option.value=league.id;option.textContent=league.name;return option;}));
    if(body.leagues.some(l=>String(l.id)===selected))$("league").value=selected;
    updateTargets();renderItem();
  }
  function updateTargets(){
    const selected=$("target").value,league=inventory?.leagues.find(l=>String(l.id)===$("league").value);
    const empty=document.createElement("option");empty.value="";empty.textContent="Выбери игрока";
    $("target").replaceChildren(empty,...(league?.targets||[]).map(player=>{const option=document.createElement("option");option.value=player.id;option.textContent=player.name;return option;}));
    if(league?.targets.some(p=>String(p.id)===selected))$("target").value=selected;
  }
  function renderItem(){
    if(!active||!inventory)return;
    const key=active.dataset.product,p=products.get(key),item=inventory.items[key];
    $("buy").hidden=item.owned;$("apply").hidden=!item.owned||item.applied;
    $("buy").textContent=`Купить · ${p.price}`;$("apply").textContent="Применить в выбранной лиге";
    $("buy").disabled=sending||!inventory.can_buy||inventory.state.balance<p.cost;
    $("activation").hidden=!item.owned||item.applied;
    $("target-field").hidden=!targeted.has(key);
    $("league").disabled=$("target").disabled=sending||!inventory.can_apply;
    $("apply").disabled=sending||!inventory.can_apply||!$("league").value||(targeted.has(key)&&!$("target").value);
    $("detail-note").textContent=item.applied?`Применено · ${item.league}${item.target?" → "+item.target:""}. Повторное применение недоступно.`:
      item.owned?(inventory.can_apply?"Куплено. Выбери лигу: предмет можно применить только один раз.":`Куплено. Применение: с ${date(inventory.deadline)} до ${inventory.race_at?date(inventory.race_at):"старта гонки"}.`):
      !inventory.can_buy?"Покупки доступны после дедлайна аркады и до старта гонки при участии в лиге «Паддок».":
      inventory.state.balance<p.cost?"Недостаточно игровых денег. Цена и баланс проверяются сервером.":"Можно купить один раз за этап и сразу применить в выбранной лиге.";
  }
  async function requestInventory(action){
    if(!cfg||sending||!active)return;
    sending=true;renderItem();
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000);
    try{
      const body={wallet_id:cfg.wallet_id,product:active.dataset.product};
      if(action==="apply"){body.league_season_id=Number($("league").value);if(targeted.has(body.product))body.target_id=Number($("target").value);}
      const response=await fetch(action==="buy"?cfg.buy_url:cfg.apply_url,{method:"POST",credentials:"same-origin",signal:controller.signal,
        headers:{"Content-Type":"application/json","X-CSRFToken":root.querySelector('[name="csrfmiddlewaretoken"]').value},body:JSON.stringify(body)});
      if(!response.headers.get("Content-Type")?.includes("application/json"))throw new Error("Обнови страницу и проверь вход в аккаунт.");
      const data=await response.json();if(!response.ok)throw new Error(data.error||"Не удалось сохранить действие.");
      refreshInventory(data);
    }catch(error){$("detail-note").textContent=error.name==="AbortError"?"Нет подтверждения сервера. Повтори действие — повторного списания не будет.":error.message;}
    finally{clearTimeout(timer);sending=false;$("buy").disabled=!inventory.can_buy||inventory.state.balance<products.get(active.dataset.product).cost;$("apply").disabled=!inventory.can_apply||!$("league").value||(targeted.has(active.dataset.product)&&!$("target").value);clearTimeout(inventoryTimer);inventoryTimer=setTimeout(pollInventory,15000);}
  }
  $("buy").addEventListener("click",()=>requestInventory("buy"));$("apply").addEventListener("click",()=>requestInventory("apply"));
  $("league").addEventListener("change",()=>{updateTargets();renderItem();});$("target").addEventListener("change",renderItem);
  let inventoryTimer=0;
  async function pollInventory(){
    clearTimeout(inventoryTimer);if(!cfg||document.hidden||sending)return;
    try{const response=await fetch(cfg.status_url,{credentials:"same-origin",cache:"no-store"});if(response.ok)refreshInventory(await response.json());}catch(_){}
    finally{if(!document.hidden)inventoryTimer=setTimeout(pollInventory,15000);}
  }
  if(cfg){refreshInventory(cfg);inventoryTimer=setTimeout(pollInventory,15000);}
  document.addEventListener("visibilitychange",()=>{clearTimeout(inventoryTimer);if(!document.hidden)pollInventory();});
  window.addEventListener("pagehide",()=>clearTimeout(inventoryTimer));
  window.addEventListener("pageshow",()=>{if(cfg)pollInventory();});
  function hideTip(){tip.hidden=true;tipTarget?.removeAttribute("aria-describedby");tipTarget=null;}
  function showTip(button){
    if(!hover.matches||dialog.open)return;
    const p=products.get(button.dataset.product);if(!p)return;
    hideTip();tipTarget=button;button.setAttribute("aria-describedby",tip.id);
    $("tip-kind").textContent=p.kind;$("tip-title").textContent=p.name;$("tip-price").textContent=p.price;$("tip-copy").textContent=p.description;
    $("tip-timing").textContent=p.timing;
    tip.hidden=false;
    const rect=button.getBoundingClientRect(),box=tip.getBoundingClientRect();
    tip.style.left=`${Math.max(12,Math.min(innerWidth-box.width-12,rect.left+rect.width/2-box.width/2))}px`;
    tip.style.top=`${Math.max(12,Math.min(innerHeight-box.height-12,rect.top-box.height-10))}px`;
  }
  function close(){dialog.close();active?.focus({preventScroll:true});}
  for(const button of root.querySelectorAll("[data-product]")){
    button.addEventListener("pointerenter",()=>showTip(button));button.addEventListener("pointerleave",hideTip);
    button.addEventListener("focus",()=>showTip(button));button.addEventListener("blur",hideTip);
    button.addEventListener("click",()=>{
      const p=products.get(button.dataset.product);if(!p)return;
      hideTip();active=button;
      for(const [id,key] of [["name","name"],["kind","kind"],["price","price"],["description","description"],["rule","rule"],["timing","timing"]])$("detail-"+id).textContent=p[key];
      $("detail-art").className=`shop-detail-art shop-item-art shop-item-${p.key}`;
      renderItem();
      dialog.showModal();$("close").focus({preventScroll:true});
    });
  }
  $("close").addEventListener("click",close);$("done").addEventListener("click",close);
  dialog.addEventListener("click",e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)close();}});
  dialog.addEventListener("cancel",()=>{hideTip();});
  window.addEventListener("scroll",hideTip,{passive:true});window.addEventListener("resize",hideTip);
  root.addEventListener("scroll",hideTip,{passive:true});
  document.addEventListener("keydown",e=>{if(e.key==="Escape")hideTip();});

  const shelves=root.querySelector(".shop-shelves"),shelfButtons=[...shelves.querySelectorAll("[data-product]")];
  let shelfFrame=0;
  function updateShelf(){
    shelfFrame=0;
    const rect=shelves.getBoundingClientRect();
    const shown=shelfButtons.map((button,index)=>({index,rect:button.getBoundingClientRect()})).filter(item=>item.rect.left+item.rect.width/2>rect.left&&item.rect.left+item.rect.width/2<rect.right);
    if(shown.length)$("shelf-position").textContent=`${shown[0].index+1}–${shown[shown.length-1].index+1} / ${shelfButtons.length}`;
    $("shelf-prev").disabled=shelves.scrollLeft<=2;
    $("shelf-next").disabled=shelves.scrollLeft+shelves.clientWidth>=shelves.scrollWidth-2;
  }
  function scheduleShelf(){if(!shelfFrame)shelfFrame=requestAnimationFrame(updateShelf);}
  function moveShelf(direction){
    const step=(shelfButtons[0]?.getBoundingClientRect().width||150)+(parseFloat(getComputedStyle(shelves).columnGap)||0);
    shelves.scrollBy({left:direction*step,behavior:motion.matches?"auto":"smooth"});
  }
  $("shelf-prev").addEventListener("click",()=>moveShelf(-1));
  $("shelf-next").addEventListener("click",()=>moveShelf(1));
  shelves.addEventListener("scroll",()=>{hideTip();scheduleShelf();},{passive:true});
  window.addEventListener("resize",scheduleShelf);
  updateShelf();

  // One short sequence at a time; no background polling or animation work
  // while the shop is offscreen, a product is open, or motion is disabled.
  const dealer=$("dealer");
  if(!dealer)return;
  let timer=null,inView=false,running=false,pageActive=true,turn=0;
  const gestures=["greet","blink","toss","blink","blink","toss"];
  const poses={
    blink:[["blink",130]],
    greet:[["greet",700]],
    toss:[["prepare",180],["release",1000],["catch",200]],
  };
  function pose(name){
    dealer.dataset.pose=name;
    dealer.classList.toggle("is-tossing",name==="release");
    dealer.classList.toggle("is-greeting",name==="greet");
  }
  function stopDealer(){
    clearTimeout(timer);timer=null;running=false;pose("idle");
    dealer.dataset.animating="false";
  }
  function nextGesture(){
    const frames=poses[gestures[turn++%gestures.length]];
    let frame=0;
    function advance(){
      if(!running)return;
      if(frame===frames.length){
        pose("idle");timer=setTimeout(nextGesture,2800+Math.random()*1400);return;
      }
      const [name,duration]=frames[frame++];pose(name);
      timer=setTimeout(advance,duration);
    }
    advance();
  }
  function syncDealer(){
    if(!inView||!pageActive||document.hidden||motion.matches||dialog.open){stopDealer();return;}
    if(running)return;
    running=true;dealer.dataset.animating="true";
    timer=setTimeout(nextGesture,1200);
  }
  if("IntersectionObserver" in window){
    const observer=new IntersectionObserver(entries=>{
      inView=entries[0].isIntersecting;syncDealer();
    },{threshold:0});
    observer.observe(dealer);
  }else{inView=true;syncDealer();}
  motion.addEventListener("change",syncDealer);
  document.addEventListener("visibilitychange",syncDealer);
  // MutationObserver also covers browsers without the dialog toggle event.
  new MutationObserver(syncDealer).observe(dialog,{attributes:true,attributeFilter:["open"]});
  window.addEventListener("pagehide",()=>{pageActive=false;stopDealer();});
  window.addEventListener("pageshow",()=>{pageActive=true;syncDealer();});
})();
