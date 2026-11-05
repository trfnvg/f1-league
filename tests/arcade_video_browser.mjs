// Real canvas recording, IndexedDB, multipart transport and video playback.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
const pw=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const script=await fs.readFile(new URL('../league/static/league/arcade-video.js',import.meta.url),'utf8');
let config, parts=[], uploaded=null, initCalls=0, partCalls=0, completeCalls=0, mode='normal', failOnce=false;
const html=`<!doctype html><html><head><meta charset="utf-8"></head><body>
<input name="csrfmiddlewaretoken" value="test-csrf"><section id="tetris-machine"><canvas id="source" width="320" height="640"></canvas><b id="score">25</b></section>
<div id="arcade-video-notice"><p id="arcade-video-status"></p><button id="arcade-video-retry" hidden>Повторить</button></div>
<script type="application/json" id="arcade-video-config">{"game":"tetris","initUrl":"/init","partSize":5242880,"maxSize":1073741824}</script>
<script src="/recorder.js"></script><script>
window.frame=0;const canvas=document.getElementById('source'),ctx=canvas.getContext('2d');
setInterval(()=>{ctx.fillStyle='#10151d';ctx.fillRect(0,0,320,640);ctx.fillStyle='#ee6359';ctx.fillRect((frame++*4)%280,240,40,40);},30);
window.recorder=ArcadeVideo.create(canvas,'Pit Stack',document.getElementById('score'));
</script></body></html>`;
const server=http.createServer(async(req,res)=>{
  const url=req.url.split('?')[0];
  if(req.method==='GET') {
    if(url==='/'){res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html);return;}
    if(url==='/recorder.js'){res.setHeader('Content-Type','text/javascript; charset=utf-8');res.end(script);return;}
    if(url==='/video' && uploaded){
      const range=req.headers.range?.match(/bytes=(\d+)-(\d*)/);
      res.setHeader('Content-Type',config.mime);res.setHeader('Accept-Ranges','bytes');
      if(range){const start=Number(range[1]),end=range[2]?Math.min(Number(range[2]),uploaded.length-1):uploaded.length-1;
        res.writeHead(206,{'Content-Range':`bytes ${start}-${end}/${uploaded.length}`,'Content-Length':end-start+1});res.end(uploaded.subarray(start,end+1));}
      else {res.setHeader('Content-Length',uploaded.length);res.end(uploaded);}return;
    }
    res.writeHead(404);res.end();return;
  }
  assert.equal(req.headers['x-csrftoken'],'test-csrf');
  const chunks=[];for await(const chunk of req)chunks.push(chunk);
  const body=Buffer.concat(chunks);
  res.setHeader('Content-Type','application/json');
  if(url==='/init'){
    initCalls++;config=JSON.parse(body);
    if(mode==='not-best'){res.writeHead(409);res.end('{"error":"not best"}');return;}
    res.end(JSON.stringify({id:'upload',received:parts.reduce((s,b)=>s+b.length,0),completed:false,part_url:'/part',complete_url:'/complete'}));return;
  }
  if(url==='/part'){
    partCalls++;
    if(mode==='retry' && !failOnce){failOnce=true;res.writeHead(503);res.end('{"error":"network failure"}');return;}
    const form=await new Response(body,{headers:{'Content-Type':req.headers['content-type']}}).formData();
    parts.push(Buffer.from(await form.get('chunk').arrayBuffer()));
    res.end(JSON.stringify({received:parts.reduce((s,b)=>s+b.length,0)}));return;
  }
  if(url==='/complete'){completeCalls++;uploaded=Buffer.concat(parts);assert.equal(uploaded.length,config.size);res.end('{"saved":true}');return;}
  res.writeHead(404);res.end('{}');
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const engine=process.env.BROWSER||'chromium',browser=await pw[engine].launch({headless:true});
const errors=[];
try {
  const context=await browser.newContext();const page=await context.newPage();
  page.on('pageerror',error=>errors.push(String(error)));
  const base=`http://127.0.0.1:${server.address().port}`;
  await page.goto(base);
  await page.evaluate(()=>{window.run=recorder.begin();});
  await page.waitForTimeout(2400);
  const meta=await page.evaluate(async()=>{await run.stop();return {...run.meta,failed:run.failed,failure:run.failure};});
  assert.equal(meta.failed,false,JSON.stringify(meta));assert.ok(meta.size>500);assert.ok(meta.duration_ms>=2300);
  await page.evaluate(()=>run.upload(1));
  assert.equal(completeCalls,1);assert.ok(['video/webm','video/mp4'].includes(config.mime));
  await page.evaluate(async()=>{
    const video=document.createElement('video');video.muted=true;video.src='/video';document.body.append(video);window.playback=video;
    window.playbackEnded=false;video.onended=()=>window.playbackEnded=true;await video.play();
  });
  await page.waitForFunction(()=>playback.currentTime>0.5);
  assert.equal(await page.evaluate(()=>playback.videoWidth),320);
  await page.waitForFunction(()=>window.playbackEnded,null,{timeout:10000});
  const count=await page.evaluate(()=>new Promise(resolve=>{const r=indexedDB.open('fastlap-arcade-video');r.onsuccess=()=>{
    const q=r.result.transaction('chunks').objectStore('chunks').count();q.onsuccess=()=>resolve(q.result);
  };}));
  assert.equal(count,0,'Successful upload removes local chunks');
  mode='not-best';const previousComplete=completeCalls;
  await page.evaluate(()=>{window.run=recorder.begin();});await page.waitForTimeout(500);await page.evaluate(()=>run.upload(2));
  assert.equal(completeCalls,previousComplete,'Non-record attempts never replace the stored file');
  mode='retry';parts=[];uploaded=null;
  await page.evaluate(()=>{window.run=recorder.begin();});await page.waitForTimeout(600);await page.evaluate(()=>run.upload(3));
  assert.equal(await page.locator('#arcade-video-retry').isVisible(),true);
  await page.locator('#arcade-video-retry').click();
  try {await page.waitForFunction(()=>document.getElementById('arcade-video-status').textContent==='Видео рекорда сохранено.',null,{timeout:5000});}
  catch(error){console.error({initCalls,partCalls,completeCalls},await page.evaluate(()=>({status:document.getElementById('arcade-video-status').textContent,meta:run.meta,failure:run.failure,error:run.lastUploadError})));throw error;}
  assert.equal(completeCalls,previousComplete+1);
  await page.evaluate(()=>{window.MediaRecorder=undefined;window.unsupported=recorder.begin();});
  assert.equal(await page.evaluate(()=>unsupported),null);
  assert.deepEqual(errors,[]);
  console.log(`Arcade video ${engine}: complete encoded video played to the end; disk-backed chunks, replacement gate, retry, unsupported browser and cleanup passed (${initCalls} init / ${partCalls} parts).`);
  await context.close();
} finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
