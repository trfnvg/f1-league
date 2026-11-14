/* Read-only virtual balances. Poll only while the strip is visible. */
(() => {
  "use strict";
  const root=document.getElementById("vegas-balances");if(!root)return;
  const cfg=JSON.parse(document.getElementById("vegas-config").textContent);
  const list=document.getElementById("vegas-balances-list"),more=document.getElementById("vegas-balances-more"),status=document.getElementById("vegas-balances-status");
  const whole=new Intl.NumberFormat("ru-RU",{style:"currency",currency:"USD",maximumFractionDigits:0});
  const cents=new Intl.NumberFormat("ru-RU",{style:"currency",currency:"USD",maximumFractionDigits:2});
  const money=n=>(n%100?cents:whole).format(n/100);
  const ownMoney=n=>cfg.unlimited_balance===true?"∞":money(n);
  const text=(el,value)=>{if(el.textContent!==value)el.textContent=value;};
  let ownBalance=cfg.state.balance,revision=0,pages=1,timer=0,controller=null,visible=false,active=true;
  const rows=new Map();
  function row(player){
    let li=rows.get(player.id);
    if(!li){
      li=document.createElement("li");li.dataset.player=String(player.id);
      const rank=document.createElement("span"),name=document.createElement("span"),amount=document.createElement("strong");
      rank.className="vegas-balance-rank";name.className="vegas-balance-name";li.append(rank,name,amount);rows.set(player.id,li);
    }
    li.classList.toggle("is-you",player.is_you);
    text(li.children[0],player.is_you?"ТЫ":String(player.rank).padStart(2,"0"));
    text(li.children[1],player.name);if(li.children[1].title!==player.name)li.children[1].title=player.name;
    text(li.children[2],player.is_you?ownMoney(ownBalance):money(player.balance));
    return li;
  }
  function render(players){
    const own={...cfg.player,is_you:true,balance:ownBalance};
    const items=[own,...players.filter(p=>p.id!==own.id)];
    const ids=new Set(items.map(p=>p.id));
    for(const [id,li] of rows)if(!ids.has(id)){li.remove();rows.delete(id);}
    // Move existing nodes only when their position changed; don't interrupt
    // horizontal scrolling/focus or recreate names on each refresh.
    items.forEach((p,index)=>{const li=row(p);if(list.children[index]!==li)list.insertBefore(li,list.children[index]||null);});
  }
  render([]);
  function stop(){clearTimeout(timer);timer=0;controller?.abort();}
  async function refresh(){
    clearTimeout(timer);
    if(!visible||!active||document.hidden||controller)return;
    more.disabled=true;
    const requestController=new AbortController();controller=requestController;
    const timeout=setTimeout(()=>requestController.abort(),10000),startedRevision=revision;
    try{
      let offset=0,next=null,players=[];
      for(let page=0;page<pages;page++){
        const url=new URL(cfg.balances_url,location.href);url.searchParams.set("offset",String(offset));
        const response=await fetch(url,{credentials:"same-origin",cache:"no-store",signal:requestController.signal});
        if(!response.ok)throw new Error("balances");
        const data=await response.json();players.push(...data.players);next=data.next_offset;
        if(cfg.wallet_id&&data.wallet_id!==cfg.wallet_id)throw new Error("competition changed");
        if(data.closed)document.dispatchEvent(new Event("vegas:closed"));
        if(startedRevision===revision&&Number.isSafeInteger(data.own_balance)){
          ownBalance=data.own_balance;
          if(data.own_state)document.dispatchEvent(new CustomEvent("vegas:topup-state",{detail:data.own_state}));
        }
        if(next===null)break;offset=next;
      }
      const unique=[...new Map(players.map(p=>[p.id,p])).values()];
      render(unique);more.hidden=next===null;status.textContent="Сейчас";
    }catch(error){if(active&&!document.hidden)status.textContent="Обновим чуть позже";}
    finally{
      clearTimeout(timeout);controller=null;more.disabled=false;
      if(visible&&active&&!document.hidden)timer=setTimeout(refresh,15000);
    }
  }
  document.addEventListener("vegas:balance",event=>{ownBalance=event.detail.balance;revision++;const li=rows.get(cfg.player.id);if(li)li.children[2].textContent=ownMoney(ownBalance);});
  more.addEventListener("click",()=>{pages++;more.disabled=true;refresh();});
  document.addEventListener("visibilitychange",()=>{if(document.hidden)stop();else refresh();});
  window.addEventListener("pagehide",()=>{active=false;stop();});
  window.addEventListener("pageshow",()=>{active=true;refresh();});
  if("IntersectionObserver" in window)new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible)refresh();else stop();}).observe(root);
  else{visible=true;refresh();}
})();
