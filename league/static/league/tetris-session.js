(function () {
  'use strict';
  const STEP=1000/60, ACTIONS=['left','right','rotate','rotateCCW','down','drop'];
  const byId=id=>document.getElementById(`tetris-${id}`);
  const status=message=>{const node=byId('save-status');if(node)node.textContent=message;};
  function paintBoard(data) {
    const list=byId('leaderboard-list');if(!list||!data||!Array.isArray(data.records))return;
    const text=(tag,value,css)=>{const node=document.createElement(tag);node.textContent=String(value??'');if(css)node.className=css;return node;};
    const rows=data.records.map(record=>{
      const row=document.createElement('li');if(record.is_current_user)row.className='is-you';
      const score=text('span','', 'arcade-record-score');score.append(text('strong',Number(record.score).toLocaleString('ru-RU')));
      const attempts=text('span','', 'arcade-attempt-count');attempts.append(text('strong',Number(record.attempts).toLocaleString('ru-RU')));
      row.append(text('span',String(record.rank).padStart(2,'0'),'arcade-rank'),text('span',record.username,'arcade-driver-name'),score,attempts);return row;
    });
    if(!rows.length)rows.push(text('li','Пока нет рекордов — начни первый заезд.','arcade-board-empty'));
    list.replaceChildren(...rows);
    const title=byId('leaderboard-title'),total=byId('total-attempts');
    if(title)title.textContent=data.board_title;
    if(total)total.textContent=Number(data.total_attempts||0).toLocaleString('ru-RU');
  }
  async function post(url,payload) {
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),10000);
    try {
      const token=document.querySelector('#tetris-csrf-form input[name="csrfmiddlewaretoken"]')?.value||'';
      const response=await fetch(url,{method:'POST',credentials:'same-origin',signal:controller.signal,
        headers:{'Content-Type':'application/json','X-CSRFToken':token},body:JSON.stringify(payload)});
      if(response.redirected)throw Error('Войди в аккаунт и обнови страницу.');
      const data=await response.json();
      if(!response.ok){const error=Error(data.error||'Не удалось связаться с сервером.');error.status=response.status;throw error;}
      return data;
    } catch(error) {
      if(error.name==='AbortError')throw Error('Сервер не ответил. Попробуй ещё раз.');
      if(error instanceof SyntaxError)throw Error('Сервер недоступен. Попробуй ещё раз.');
      throw error;
    } finally {clearTimeout(timeout);}
  }
  class PitStackSession {
    constructor(element) {
      this.element=element;this.enabled=element?.dataset.saveResults==='true';
      this.inputs=[];this.ticks=0;this.accumulator=0;this.pending=null;this.saving=null;this.ended=false;
      this.maxTicks=864000;this.maxInputs=30000;
      this.lastInputTick=-1;this.commandsAtTick=0;
    }
    async begin() {
      if(this.saving)await this.saving;
      if(this.pending){await this.save();if(this.pending)throw Error('Сначала повтори сохранение предыдущего заезда.');}
      status(this.enabled?'Подключаем заезд…':'');
      const data=this.enabled?await post(this.element.dataset.startUrl,{}):{seed:Math.floor(Math.random()*4294967296)};
      if(this.enabled && (!Number.isInteger(data.attempt_id)||!Number.isInteger(data.seed)||data.rules_version!==1))
        throw Error('Обнови страницу: версия игры изменилась.');
      this.attemptId=data.attempt_id;this.version=data.rules_version;
      this.maxTicks=data.max_ticks||864000;this.maxInputs=data.max_inputs||30000;
      this.inputs=[];this.ticks=0;this.accumulator=0;this.ended=false;
      this.lastInputTick=-1;this.commandsAtTick=0;
      status('');return window.PitStack.createRandom(data.seed);
    }
    record(action,game) {
      if(!this.enabled)return true;
      if(this.inputs.length>=this.maxInputs){game.finish();return false;}
      if(this.lastInputTick!==this.ticks){this.lastInputTick=this.ticks;this.commandsAtTick=0;}
      if(this.commandsAtTick>=8)return false;
      this.commandsAtTick++;
      this.inputs.push([this.ticks,ACTIONS.indexOf(action)]);return true;
    }
    advance(game,ms) {
      if(game.paused)return;
      this.accumulator+=ms;
      while(this.accumulator+1e-7>=STEP && ['running','clearing'].includes(game.phase)) {
        game.update(STEP);this.ticks++;
        this.accumulator=Math.max(0,this.accumulator-STEP);
        if(this.enabled && this.ticks>=this.maxTicks){game.finish();break;}
      }
    }
    finish() {
      if(this.ended)return;this.ended=true;
      if(!this.enabled)return;
      this.pending={attempt_id:this.attemptId,rules_version:this.version,ticks:this.ticks,inputs:this.inputs};
      this.save();
    }
    async save() {
      if(this.saving)return this.saving;
      if(!this.pending)return;
      status('Проверяем и сохраняем результат…');
      this.saving=(async()=>{
        try {const data=await post(this.element.dataset.finishUrl,this.pending);this.pending=null;paintBoard(data);status('Результат сохранён.');}
        catch(error){if([400,409].includes(error.status))this.pending=null;status(error.message);}
        finally {this.saving=null;const retry=byId('retry-save');if(retry)retry.hidden=!this.pending;}
      })();
      return this.saving;
    }
  }
  window.PitStackSession=PitStackSession;
  const results=byId('results'),retry=byId('retry-save');
  if(retry)retry.addEventListener('click',()=>window.PitStackActiveSession?.save());
  if(results?.dataset.boardUrl) {
    let timer=0,request=null,epoch=0;
    async function refresh(){
      if(document.hidden)return;
      const current=epoch;
      request=new AbortController();
      try {const response=await fetch(results.dataset.boardUrl,{credentials:'same-origin',signal:request.signal});if(response.ok)paintBoard(await response.json());}catch{}
      finally {if(current===epoch){request=null;if(!document.hidden)timer=setTimeout(refresh,15000);}}
    }
    document.addEventListener('visibilitychange',()=>{epoch++;clearTimeout(timer);request?.abort();if(!document.hidden)timer=setTimeout(refresh,500);});
    window.addEventListener('pagehide',()=>{epoch++;clearTimeout(timer);request?.abort();});
    window.addEventListener('pageshow',event=>{if(event.persisted){epoch++;clearTimeout(timer);timer=setTimeout(refresh,500);}});
    timer=setTimeout(refresh,15000);
  }
})();
