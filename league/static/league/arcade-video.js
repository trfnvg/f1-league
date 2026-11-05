/* Canvas-only video. Disk-backed chunks, best-run uploads, no camera/microphone. */
(() => {
  'use strict';
  const configNode = document.getElementById('arcade-video-config');
  if (!configNode) return;
  const config = JSON.parse(configNode.textContent);
  const status = document.getElementById('arcade-video-status');
  const retry = document.getElementById('arcade-video-retry');
  const machine=document.querySelector('#tetris-machine,.doodle-machine,.arcade-machine');
  const noticeRoot=document.getElementById('arcade-video-notice');
  if(machine && noticeRoot)machine.before(noticeRoot);
  const notice = text => { if (status) status.textContent = text; };
  let database, retryRun = null;
  const open = () => database ??= new Promise((resolve, reject) => {
    const request = indexedDB.open('fastlap-arcade-video', 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore('runs', {keyPath:'id'});
      request.result.createObjectStore('chunks', {keyPath:'key'});
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(Error('Хранилище видео недоступно.'));
  });
  async function write(store, value) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(store, 'readwrite');
      const request=tx.objectStore(store).put(value);
      request.onerror=()=>reject(request.error);
      tx.oncomplete = resolve;
      tx.onerror = tx.onabort = () => reject(tx.error || Error('Недостаточно места для видео.'));
    });
  }
  const range = id => IDBKeyRange.bound(id+':', id+':\uffff');
  async function remove(id) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(['runs','chunks'], 'readwrite');
      tx.objectStore('runs').delete(id);tx.objectStore('chunks').delete(range(id));
      tx.oncomplete = resolve;tx.onerror = () => reject(tx.error);
    });
  }
  async function readSlice(id, offset, size) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const blobs = [];let position=0, remaining=size;
      const tx = db.transaction('chunks');
      const request = tx.objectStore('chunks').openCursor(range(id));
      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        const cursor=request.result;
        if (!cursor || !remaining) { resolve(new Blob(blobs));return; }
        const blob=cursor.value.blob || new Blob([cursor.value.bytes]);
        if (position+blob.size>offset) {
          const from=Math.max(0,offset-position), count=Math.min(remaining,blob.size-from);
          blobs.push(blob.slice(from,from+count));remaining-=count;
        }
        position+=blob.size;cursor.continue();
      };
    });
  }
  async function post(url, data) {
    const token=document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || '';
    const form=data instanceof FormData;
    const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),90000);
    try {
      const response=await fetch(url,{method:'POST',credentials:'same-origin',signal:controller.signal,
        headers:{'X-CSRFToken':token,...(form?{}:{'Content-Type':'application/json'})},
        body:form?data:JSON.stringify(data)});
      if(response.redirected)throw Error('Войди в аккаунт для загрузки видео.');
      const result=await response.json();
      if(!response.ok){const error=Error(result.error||'Не удалось загрузить видео.');error.status=response.status;throw error;}
      return result;
    } finally {clearTimeout(timeout);}
  }
  class Run {
    constructor(canvas, title, scoreNode) {
      this.meta={id:crypto.randomUUID(),game:config.game,created:Date.now(),size:0,stopped:false};
      this.queue=Promise.resolve();this.index=0;this.failed=false;this.pendingChunks=0;
      this.output=document.createElement('canvas');
      const width=Math.min(480,canvas.width), height=Math.max(1,Math.round(canvas.height/canvas.width*width));
      this.output.width=width;this.output.height=height+64;
      const ctx=this.output.getContext('2d',{alpha:false});
      const draw=()=>{
        try {
          ctx.fillStyle='#10151d';ctx.fillRect(0,0,width,height+64);
          ctx.fillStyle='#f0f3f8';ctx.font='bold 16px sans-serif';ctx.fillText(title,12,23);
          ctx.font='14px sans-serif';ctx.fillText('Очки: '+(scoreNode?.textContent||'0'),12,47);
          ctx.drawImage(canvas,0,64,width,height);
          if(canvas.id==='tetris-canvas') {
            const fx=document.getElementById('tetris-feedback'),next=document.getElementById('tetris-next');
            if(fx)ctx.drawImage(fx,0,64,width,height);
            if(next)ctx.drawImage(next,width-68,4,60,53);
          }
        } catch(error) {this.failure=error.message;this.fail();}
      };
      draw();
      if(this.failed)throw Error('Игровое поле недоступно для записи.');
      const mime=['video/mp4;codecs=avc1.42E01E','video/webm;codecs=vp8','video/mp4','video/webm']
        .find(type=>MediaRecorder.isTypeSupported(type));
      if(!mime)throw Error('Браузер не поддерживает запись видео игры.');
      this.stream=this.output.captureStream(12);
      try {this.recorder=new MediaRecorder(this.stream,{mimeType:mime,videoBitsPerSecond:240000});}
      catch(error){this.stream.getTracks().forEach(track=>track.stop());throw error;}
      this.meta.mime=this.recorder.mimeType.split(';')[0];
      this.done=new Promise(resolve=>{this.resolve=resolve;});
      this.recorder.ondataavailable=event=>{
        if(!event.data.size || this.failed)return;
        const key=this.meta.id+':'+String(this.index++).padStart(10,'0');
        const blob=event.data;
        this.meta.size+=event.data.size;
        if(this.meta.size>config.maxSize || blob.size>16*1024*1024 || ++this.pendingChunks>3){this.fail();return;}
        // WebKit can fail persisting a recorder-owned Blob after its encoder
        // releases the backing object. Own the small chunk's bytes explicitly.
        this.queue=this.queue.then(async()=>write('chunks',{key,bytes:await blob.arrayBuffer()}))
          .catch(error=>{this.failure=error.message||String(error);this.fail();}).finally(()=>this.pendingChunks--);
      };
      this.recorder.onerror=event=>{this.failure=event.error?.message||'Ошибка кодировщика';this.fail();};
      this.recorder.onstop=async()=>{
        clearInterval(this.timer);this.stream.getTracks().forEach(track=>track.stop());
        this.meta.stopped=true;this.meta.duration_ms=Math.max(1,Date.now()-this.meta.created);
        try {await this.queue;if(!this.failed)await write('runs',this.meta);}catch(error){this.failure=error.message||String(error);this.failed=true;}
        if(this.failed)notice('Полная запись не получилась. Результат игры сохранится независимо от видео.');
        this.resolve(this);
      };
      try {this.recorder.start(10000);}
      catch(error){this.stream.getTracks().forEach(track=>track.stop());throw error;}
      this.timer=setInterval(draw,1000/12);
      this.queue=write('runs',this.meta).catch(error=>{this.failure=error.message;this.fail();});
      notice('Записывается только игровое поле. Видео рекорда доступно по ссылке.');
    }
    fail() {this.failed=true;if(this.recorder?.state!=='inactive')this.recorder?.stop();}
    stop() {if(this.recorder?.state!=='inactive')this.recorder?.stop();return this.done;}
    async discard() {await this.stop();await remove(this.meta.id).catch(()=>{});}
    async upload(attemptId) {
      if(this.uploading)return this.uploading;
      this.uploading=this.send(attemptId).finally(()=>{this.uploading=null;});
      return this.uploading;
    }
    async send(attemptId) {
      try {
        await this.stop();
        if(this.failed || !this.meta.size){await this.discard();return;}
        this.meta.attemptId=attemptId;await write('runs',this.meta);
        const session=await post(config.initUrl,{game:config.game,attempt_id:attemptId,
          mime:this.meta.mime,size:this.meta.size,duration_ms:this.meta.duration_ms});
        let offset=session.received;
        if(!session.completed) {
          while(offset<this.meta.size) {
            notice(`Видео рекорда загружается: ${Math.floor(offset/this.meta.size*100)}%. Не закрывай страницу.`);
            const chunk=await readSlice(this.meta.id,offset,Math.min(config.partSize,this.meta.size-offset));
            const data=new FormData();data.append('part',String(Math.floor(offset/config.partSize)+1));data.append('chunk',chunk,'part');
            const result=await post(session.part_url,data);
            if(result.received<=offset)throw Error('Загрузка видео остановилась.');
            offset=result.received;
          }
          await post(session.complete_url,{});
        }
        await remove(this.meta.id);
        if(retryRun===this){retryRun=null;if(retry)retry.hidden=true;}
        notice('Видео рекорда сохранено.');
      } catch(error) {
        this.lastUploadError=error.message||String(error);
        if(error.status===409){await this.discard();notice('Результат сохранён. Видео этой попытки не заменяет текущий рекорд.');}
        else {retryRun=this;if(retry)retry.hidden=false;notice('Видео не загружено. Предыдущая запись сохранена; можно повторить загрузку.');}
      }
    }
  }
  retry?.addEventListener('click',()=>retryRun?.upload(retryRun.meta.attemptId));
  const supported=()=>window.MediaRecorder && HTMLCanvasElement.prototype.captureStream && window.indexedDB;
  window.ArcadeVideo={create(canvas,title,scoreNode){
    let current=null;
    return {begin(){
      if(current && current.recorder?.state!=='inactive')void current.discard();
      if(!supported()){notice('Этот браузер не поддерживает полную видеозапись.');return null;}
      try {current=new Run(canvas,title,scoreNode);return current;}
      catch {notice('Запись недоступна в этом браузере.');return null;}
    }};
  }};
  // Resume interrupted uploads on the next visit; stale local video is removed.
  if(supported())open().then(db=>new Promise((resolve,reject)=>{
    const request=db.transaction('runs').objectStore('runs').getAll();
    request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
  })).then(async runs=>{
    for(const meta of runs){
      if(Date.now()-meta.created>24*3600000){await remove(meta.id);continue;}
      if(meta.game!==config.game || !meta.stopped || !meta.attemptId)continue;
      const run=Object.create(Run.prototype);run.meta=meta;run.done=Promise.resolve(run);run.failed=false;
      run.stop=()=>run.done;await run.upload(meta.attemptId);
    }
  }).catch(()=>notice('Хранилище записи недоступно; игра продолжает работать.'));
})();
