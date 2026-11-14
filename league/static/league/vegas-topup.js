/* Claims and credits are owned by the server, never by browser storage. */
(() => {
  "use strict";
  const config=document.getElementById("vegas-config");if(!config)return;
  const cfg=JSON.parse(config.textContent),urls=cfg.topup_urls;
  const $=name=>document.getElementById("vegas-topup-"+name);
  const dialog=$("dialog"),trigger=document.getElementById("vegas-topup");
  let data=null,sending=false,timer=0,controller=null;
  const date=value=>new Intl.DateTimeFormat("ru-RU",{timeZone:"Europe/Moscow",day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}).format(new Date(value))+" МСК";
  function render(){
    if(!data)return;
    $("status").textContent=data.reason||"Выбери задание и активируй его до выполнения.";
    $("event").textContent=data.event?data.event.name+(data.event.deadline?" · до "+date(data.event.deadline):""):"Нет доступного этапа";
    const active=data.active;
    $("active").hidden=!active;$("choices").hidden=!!active;
    if(active){
      $("active-text").textContent=active.text;
      $("active-meta").textContent=active.league+" · "+active.label;
      $("submit-area").hidden=active.status!=="active";
    }
    const selected=$("league").value;
    $("league").replaceChildren(...data.leagues.map(league=>{
      const option=document.createElement("option");option.value=league.id;option.textContent=league.name;return option;
    }));
    if(data.leagues.some(league=>league.id===selected))$("league").value=selected;
    $("league").disabled=sending||!data.can_activate;
    $("tasks").replaceChildren(...data.tasks.map(task=>{
      const button=document.createElement("button"),caption=document.createElement("small");
      button.type="button";button.dataset.task=task.key;button.textContent=task.text;
      caption.textContent=task.available?"Активировать · награда "+new Intl.NumberFormat("ru-RU").format(data.reward/100):task.status;button.append(caption);
      button.disabled=sending||!data.can_activate||!task.available;
      button.addEventListener("click",()=>send("activate",{league_id:$("league").value,event_id:data.event.id,task:task.key}));return button;
    }));
    $("history").replaceChildren(...data.history.filter(claim=>!active||claim.id!==active.id).map(claim=>{
      const li=document.createElement("li");li.textContent=claim.text+" · "+claim.label+" · "+claim.event;return li;
    }));
    $("submit").disabled=$("cancel").disabled=sending;
  }
  function sync(body){
    if(cfg.wallet_id&&body.wallet_id!==cfg.wallet_id)throw new Error("Зачёт изменился. Обнови страницу игры.");
    data=body.topup;render();
    if(body.state)document.dispatchEvent(new CustomEvent("vegas:topup-state",{detail:body.state}));
  }
  async function fetchData(url,body){
    const request=new AbortController();controller=request;
    const timeout=setTimeout(()=>request.abort(),10000);
    try{
      const options={credentials:"same-origin",cache:"no-store",signal:request.signal};
      if(body){options.method="POST";options.headers={"Content-Type":"application/json","X-CSRFToken":document.querySelector('#vegas-page input[name="csrfmiddlewaretoken"]').value};options.body=JSON.stringify(body);}
      const response=await fetch(url,options),result=await response.json();
      if(!response.ok)throw new Error(result.error||"Не удалось выполнить запрос. Обнови окно и попробуй ещё раз.");
      return result;
    }finally{clearTimeout(timeout);if(controller===request)controller=null;}
  }
  function poll(){clearTimeout(timer);if(dialog.open&&!document.hidden)timer=setTimeout(load,15000);}
  async function load(){
    if(sending||controller||!dialog.open||document.hidden)return;
    try{sync(await fetchData(urls.status));}
    catch(error){if(dialog.open)$("status").textContent=error.name==="AbortError"?"Нет ответа сервера. Закрой и открой окно для повтора.":error.message;}
    finally{poll();}
  }
  async function send(action,body){
    if(sending||!data)return;
    sending=true;clearTimeout(timer);controller?.abort();render();$("status").textContent="Сохраняем…";
    const url=action==="activate"?urls.activate:urls[action].replace("/0/","/"+data.active.id+"/");
    try{sync(await fetchData(url,body));}
    catch(error){if(dialog.open)$("status").textContent=error.name==="AbortError"?"Нет подтверждения сервера. Обнови окно перед повтором.":error.message;}
    finally{sending=false;$("submit").disabled=$("cancel").disabled=false;if(data){$("league").disabled=!data.can_activate;for(const button of $("tasks").querySelectorAll("button")){const task=data.tasks.find(t=>t.key===button.dataset.task);button.disabled=!data.can_activate||!task.available;}}poll();}
  }
  trigger.addEventListener("click",()=>{document.dispatchEvent(new Event("vegas:topup-open"));dialog.showModal();$("close").focus();load();});
  $("close").addEventListener("click",()=>dialog.close());
  $("submit").addEventListener("click",()=>send("submit",{note:$("note").value}));
  $("cancel").addEventListener("click",()=>send("cancel",{}));
  dialog.addEventListener("keydown",event=>event.stopPropagation());
  dialog.addEventListener("close",()=>{clearTimeout(timer);controller?.abort();document.dispatchEvent(new Event("vegas:topup-close"));});
  document.addEventListener("visibilitychange",()=>{if(document.hidden){clearTimeout(timer);controller?.abort();}else load();});
  window.addEventListener("pagehide",()=>{clearTimeout(timer);controller?.abort();});
})();
