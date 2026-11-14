/* Read-only showroom: there are no purchases or wallet writes on this page. */
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
