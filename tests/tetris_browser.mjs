// Database-free rendering of the real Django template + real Chromium UI.
// PYTHON_BIN=/path/to/venv/python PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs node tests/tetris_browser.mjs
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const python=spawnSync(process.env.PYTHON_BIN||'python3',['-c',`
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.test import override_settings
from django.template.loader import render_to_string
from django.contrib.auth.models import User
with override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}):
    print(render_to_string('arcade_tetris.html', {'user': User(id=1,username='Test admin',is_staff=True), 'current_season': {'year':2026}}))
`],{cwd:root,encoding:'utf8',env:{...process.env,DATABASE_URL:'sqlite:///:memory:'}});
assert.equal(python.status,0,python.stderr);
const server=http.createServer(async(req,res)=>{
  if(req.url.split('?')[0]==='/') {res.setHeader('Content-Type','text/html; charset=utf-8');res.end(python.stdout);return;}
  const url=new URL(req.url,'http://localhost');
  const relative=url.pathname.replace(/^\/static\//,'');
  const target=path.resolve(root,'league/static',relative);
  if(!url.pathname.startsWith('/static/')||!target.startsWith(path.join(root,'league/static')+path.sep)){res.writeHead(404);res.end();return;}
  try {
    const ext=path.extname(target),types={'.js':'text/javascript','.css':'text/css','.png':'image/png','.webp':'image/webp','.m4a':'audio/mp4'};
    res.setHeader('Content-Type',types[ext]||'application/octet-stream');res.end(await fs.readFile(target));
  }catch {res.writeHead(404);res.end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true});
const errors=[];
async function checkFeedback(page,name) {
  const nextFrame=()=>page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  const snapshot=()=>page.evaluate(()=>JSON.stringify({board:window.__game.board,piece:window.__game.piece,score:window.__game.score}));
  await page.evaluate(()=>{
    const g=window.__game;g.board.forEach(row=>row.fill(null));
    g.piece={type:'T',matrix:window.PitStack.SHAPES.T.map(row=>row.slice()),x:3,y:2};
    g.fallClock=-100000;g.lockSerial=0;g.lastLock=null;g.clearSerial=0;g.lastClear=0;
    window.__feedback.reset();g.revision++;
  });
  await nextFrame();
  const sample=()=>page.evaluate(()=>{
    const c=document.getElementById('tetris-canvas'),ctx=c.getContext('2d'),p=window.PitStack.cells(window.__game.landing())[0];
    return [...ctx.getImageData(Math.floor((p.x*32+16)*c.width/320),Math.floor((p.y*32+1)*c.height/640),1,1).data].slice(0,3).reduce((a,b)=>a+b);
  });
  const before=await snapshot(),on=await sample();
  await page.locator('#tetris-ghost').click();await nextFrame();
  const off=await sample();assert.ok(on>off+30,`${name}: thin ghost outline is visible and can be disabled (${on}/${off})`);
  assert.equal(await snapshot(),before,'Ghost toggle is read-only');
  await page.locator('#tetris-ghost').click();await nextFrame();
  assert.equal(await page.locator('#tetris-ghost').getAttribute('aria-pressed'),'true');
  await page.evaluate(()=>{
    const g=window.__game;g.board.forEach(row=>row.fill(null));
    for(let y=16;y<20;y++){g.board[y].fill('J');g.board[y][5]=null;}
    g.piece={type:'I',matrix:[[1],[1],[1],[1]],x:5,y:16};
    g.score=0;g.lines=0;g.level=1;g.clearSerial=0;g.lockSerial=0;g.lastLock=null;
    window.__feedback.reset();g.revision++;
  });
  await page.locator('#tetris-canvas').focus();await page.keyboard.press('Enter');
  await page.waitForFunction(()=>window.__game.clearSerial===1 && window.__feedback.chips.length>0);
  await page.evaluate(()=>{
    window.__freezeFeedback=true;window.__feedback.chips.forEach(chip=>chip.age=85);
    window.__feedback.dirty=true;window.dispatchEvent(new Event('resize'));
  });
  assert.equal(await page.evaluate(()=>window.__game.score),1200);
  assert.equal(await page.locator('#tetris-track-lights').evaluate(node=>node.classList.contains('is-celebrating')),true);
  assert.equal(await page.locator('#tetris-track-lights i').count(),10);
  assert.equal(await page.locator('#tetris-feedback').evaluate(node=>getComputedStyle(node).pointerEvents),'none');
  const rails=await page.evaluate(()=>{
    const r=node=>node.getBoundingClientRect();
    const machine=r(document.getElementById('tetris-machine')),board=r(document.getElementById('tetris-board'));
    const telemetry=r(document.querySelector('.tetris-telemetry')),[left,right]=[...document.querySelectorAll('#tetris-track-lights > div')].map(r);
    const a=document.getElementById('tetris-canvas'),b=document.getElementById('tetris-feedback');
    return {outside:left.right<=board.left && right.left>=board.right,
      fits:left.left>=machine.left && right.right<=telemetry.left,samePixels:a.width===b.width && a.height===b.height};
  });
  assert.deepEqual(rails,{outside:true,fits:true,samePixels:true},'Lights stay outside the field and clear of telemetry, at matching DPR');
  const x=await page.evaluate(()=>window.__game.piece.x);await page.keyboard.press('ArrowLeft');
  assert.equal(await page.evaluate(()=>window.__game.piece.x),x-1,'Next piece remains controllable during particles/lights');
  assert.ok(await page.locator('#tetris-score').evaluate(node=>node.scrollWidth<=node.clientWidth),'Celebration score fits on one line');
  if(process.env.TETRIS_PREVIEW_DIR)await page.locator('#tetris-machine').screenshot({path:path.join(process.env.TETRIS_PREVIEW_DIR,`tetris-feedback-${name}.png`)});
  await page.evaluate(()=>{window.__game.score=1200000;window.__game.revision++;});await nextFrame();
  assert.ok(await page.locator('#tetris-score').evaluate(node=>node.scrollWidth<=node.clientWidth),'Large scores also fit the mobile panel');
  await page.evaluate(()=>{
    const g=window.__game;window.__freezeFeedback=false;window.__feedback.reset();
    g.board.forEach(row=>row.fill(null));g.lines=0;g.level=1;g.score=0;
    g.lockSerial=0;g.clearSerial=0;g.lastLock=null;g.lastClear=0;g.lastClearCells=[];
    g.fallClock=-100000;g.revision++;
  });
}
async function checkMusic(page) {
  const media=page.locator('#tetris-soundtrack'),sound=page.locator('#tetris-sound');
  await page.waitForFunction(()=>!document.getElementById('tetris-soundtrack').paused);
  await sound.click();assert.equal(await media.evaluate(m=>m.paused),true,'Mute stops decoding/playback');
  assert.equal(await page.evaluate(()=>window.__game.paused),false,'Sound controls do not pause gameplay');
  const x=await page.evaluate(()=>window.__game.piece.x);
  await page.locator('#tetris-volume').focus();await page.keyboard.press('ArrowRight');
  assert.equal(await page.locator('#tetris-volume').inputValue(),'29');
  assert.equal(await page.evaluate(()=>window.__game.piece.x),x,'Volume arrows must not move the piece');
  await page.waitForFunction(()=>!document.getElementById('tetris-soundtrack').paused);
  assert.equal(await page.evaluate(()=>window.__sound.volume),.29);
  await sound.focus();const serial=await page.evaluate(()=>window.__game.spawnSerial);
  await page.keyboard.press('Space');assert.equal(await media.evaluate(m=>m.paused),true);
  assert.equal(await page.evaluate(()=>window.__game.spawnSerial),serial,'Space on sound button must not hard-drop');
  await sound.click();await page.waitForFunction(()=>!document.getElementById('tetris-soundtrack').paused);
  await page.evaluate(()=>{window.__game.elapsed=45000*6;window.__game.revision++;});
  await page.waitForFunction(()=>document.getElementById('tetris-soundtrack').playbackRate>1.1);
  await media.evaluate(m=>{m.currentTime=m.duration-.12;});
  await page.waitForFunction(()=>document.getElementById('tetris-soundtrack').currentTime<1);
  assert.equal(await media.evaluate(m=>m.paused),false,'Track loops across the end');
  await page.evaluate(()=>{window.__game.elapsed=0;window.__game.revision++;window.dispatchEvent(new Event('blur'));});
  assert.equal(await media.evaluate(m=>m.paused),true,'Background/focus loss stops the soundtrack');
  assert.equal(await page.evaluate(()=>window.__game.paused),true);
  await page.locator('#tetris-start').click();await page.waitForFunction(()=>!document.getElementById('tetris-soundtrack').paused);
  const signal=await page.evaluate(async()=>{
    const bytes=await(await fetch(document.getElementById('tetris-soundtrack').src)).arrayBuffer();
    const decoded=await window.__sound.context.decodeAudioData(bytes);
    let peak=0,squares=0;
    for(let channel=0;channel<decoded.numberOfChannels;channel++)
      for(const sample of decoded.getChannelData(channel)){peak=Math.max(peak,Math.abs(sample));squares+=sample*sample;}
    return {seconds:decoded.duration,channels:decoded.numberOfChannels,peak,
      rms:Math.sqrt(squares/(decoded.length*decoded.numberOfChannels))};
  });
  // AudioBuffer decoding may expose AAC priming/padding that media.duration trims.
  assert.ok(Math.abs(signal.seconds-60)<.1,JSON.stringify(signal));assert.equal(signal.channels,2);
  assert.ok(signal.peak<.99 && signal.rms>.05,'Real decoded music is audible and has clipping headroom');
}
async function checkTouch(page,context) {
  const cdp=await context.newCDPSession(page);
  await page.locator('#tetris-canvas').scrollIntoViewIfNeeded();
  const rect=await page.locator('#tetris-canvas').boundingBox(),cell=rect.width/10;
  const x=rect.x+rect.width*.5,y=rect.y+rect.height*.3;
  const initialScroll=await page.evaluate(()=>window.scrollY);
  async function reset() {
    await page.evaluate(()=>{
      const game=window.__game;
      game.board.forEach(row=>row.fill(null));
      game.piece={type:'T',matrix:window.PitStack.SHAPES.T.map(row=>row.slice()),x:3,y:2};
      game.fallClock=-100000;game.lockClock=0;game.score=0;game.revision++;
    });
  }
  const touch=(type,points)=>cdp.send('Input.dispatchTouchEvent',{type,touchPoints:points});
  async function swipe(dx,dy,duration) {
    await touch('touchStart',[{x,y,id:1}]);
    for(let i=1;i<=3;i++) {
      await page.waitForTimeout(duration/3);
      await touch('touchMove',[{x:x+dx*i/3,y:y+dy*i/3,id:1}]);
    }
    await touch('touchEnd',[]);
  }
  await reset();
  const original=await page.evaluate(()=>JSON.stringify(window.__game.piece.matrix));
  await page.touchscreen.tap(rect.x+rect.width*.75,y);
  assert.notEqual(await page.evaluate(()=>JSON.stringify(window.__game.piece.matrix)),original,'Right tap rotates clockwise');
  await page.touchscreen.tap(rect.x+rect.width*.25,y);
  assert.equal(await page.evaluate(()=>JSON.stringify(window.__game.piece.matrix)),original,'Left tap reverses rotation');
  await reset();await swipe(cell*2.1,0,150);
  assert.equal(await page.evaluate(()=>window.__game.piece.x),5,'Finger drag moves cells, not the whole browser');
  await reset();await swipe(0,cell*3.1,500);
  assert.ok(await page.evaluate(()=>window.__game.score>=3),'Slow downward drag soft-drops');
  assert.equal(await page.evaluate(()=>window.__game.board.flat().filter(Boolean).length),0,'Soft drag does not lock');
  await reset();const before=await page.evaluate(()=>window.__game.spawnSerial);
  await swipe(0,Math.max(90,cell*4),30);
  assert.equal(await page.evaluate(()=>window.__game.board.flat().filter(Boolean).length),4,'Down flick hard-drops once');
  assert.equal(await page.evaluate(()=>window.__game.spawnSerial),before+1);
  await reset();await touch('touchStart',[{x,y,id:1}]);await touch('touchCancel',[]);
  assert.equal(await page.evaluate(()=>JSON.stringify(window.__game.piece.matrix)),original,'Cancelled touch cannot rotate');
  await reset();await touch('touchStart',[{x,y,id:1}]);
  await touch('touchStart',[{x,y,id:1},{x:x+20,y:y+20,id:2}]);await touch('touchEnd',[]);
  assert.equal(await page.evaluate(()=>JSON.stringify(window.__game.piece.matrix)),original,'Second finger cancels pending tap');
  await reset();const serial=await page.evaluate(()=>window.__game.spawnSerial);
  await touch('touchStart',[{x,y,id:1}]);await page.keyboard.press('Enter');await touch('touchEnd',[]);
  assert.equal(await page.evaluate(()=>window.__game.spawnSerial),serial+1,'Held finger must not affect next piece');
  assert.equal(await page.evaluate(()=>window.scrollY),initialScroll,'Gestures must not scroll the page');
  await cdp.detach();
}
try {
  for(const [name,width,height,mobile] of [['desktop',1440,1000,false],['mobile',390,844,true],['small-mobile',320,568,true]]) {
    const context=await browser.newContext({viewport:{width,height},deviceScaleFactor:mobile?3:2,isMobile:mobile,hasTouch:mobile});
    const page=await context.newPage();
    page.on('pageerror',e=>errors.push(String(e)));
    await page.route('https://**/*',route=>route.abort());
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.waitForFunction(()=>!!window.PitStack);
    await page.waitForFunction(()=>!!window.PitStackScenery);
    await page.waitForFunction(()=>{
      const image=document.querySelector('#tetris-scenery .is-visible img');
      return image?.complete && image.naturalWidth>=1500;
    });
    const tour=await page.evaluate(async()=>{
      const parent=document.createElement('div'),host=document.createElement('div'),label=document.createElement('span');
      for(const attr of document.getElementById('tetris-scenery').attributes)
        if(attr.name.startsWith('data-art-'))host.setAttribute(attr.name,attr.value);
      parent.append(host);host.append(document.createElement('div'),document.createElement('div'));
      const scenery=new window.PitStackScenery(host,label,()=>.3);
      await scenery.ready;
      const stages=[scenery.current];await scenery.update(9);const first=scenery.current;
      for(let i=1;i<40;i++){await scenery.update(i*10);stages.push(scenery.current);}
      return {first,stages,layers:host.children.length,visible:host.querySelectorAll('.is-visible').length,
        images:[...host.querySelectorAll('img')].map(image=>[image.naturalWidth,image.naturalHeight]),
        svgs:host.querySelectorAll('svg').length};
    });
    assert.equal(tour.first,tour.stages[0]);assert.equal(tour.layers,2);assert.equal(tour.visible,1);
    for(let i=1;i<tour.stages.length;i++)assert.notEqual(tour.stages[i],tour.stages[i-1]);
    for(let i=0;i<tour.stages.length;i+=10)assert.equal(new Set(tour.stages.slice(i,i+10)).size,10);
    assert.equal(tour.svgs,0,'Generated pixel art replaces old vector scenery');
    assert.equal(tour.images.length,2);for(const [w,h] of tour.images)assert.ok(w>=1500&&h>=1000,'Original art resolution retained');
    assert.equal(await page.locator('.tetris-controls,.tetris-bottom,.tetris-rules,.tetris-key-hint,#tetris-level,#tetris-status').count(),0,
      'No bottom controls, descriptions, level or status text');
    await page.evaluate(()=>{
      const start=window.PitStack.Game.prototype.start;
      window.PitStack.Game.prototype.start=function(){window.__game=this;return start.call(this);};
      const play=window.PitStackAudio.prototype.setPlaying;
      window.PitStackAudio.prototype.setPlaying=function(...args){
        window.__sound=this;(window.__audioEvents??=[]).push({args,stack:new Error().stack});
        return play.apply(this,args);
      };
      const observe=window.PitStackFeedback.prototype.observe,step=window.PitStackFeedback.prototype.step;
      window.PitStackFeedback.prototype.observe=function(game){window.__feedback=this;return observe.call(this,game);};
      window.PitStackFeedback.prototype.step=function(...args){if(!window.__freezeFeedback)return step.apply(this,args);};
    });
    assert.equal(await page.locator('#tetris-soundtrack').evaluate(media=>media.paused),true,'No title-screen autoplay');
    const titleArtwork=await page.locator('#tetris-scenery .is-visible img').getAttribute('src');
    await page.keyboard.press('Space');
    await page.waitForFunction(()=>window.__game?.phase==='running');
    await page.waitForFunction(()=>document.getElementById('tetris-overlay').hidden);
    try {
      await page.waitForFunction(()=>{
        const media=document.getElementById('tetris-soundtrack');
        return !media.paused && media.currentTime>0 && media.readyState>=2;
      },null,{timeout:8000});
    } catch(error) {
      console.error('Audio diagnostics',await page.locator('#tetris-soundtrack').evaluate(media=>({
        error:media.error?.message,code:media.error?.code,paused:media.paused,time:media.currentTime,
        ready:media.readyState,network:media.networkState,context:window.__sound?.context?.state,blocked:window.__sound?.blocked,
        phase:window.__game?.phase,pausedGame:window.__game?.paused,active:window.__sound?.active,events:window.__audioEvents,
      })));
      throw error;
    }
    assert.ok(await page.locator('#tetris-soundtrack').evaluate(media=>Math.abs(media.duration-60)<.1),'Real soundtrack is 60 seconds');
    assert.equal(await page.locator('#tetris-scenery .is-visible img').getAttribute('src'),titleArtwork,
      'Starting the game keeps the title-screen artwork');
    const x=await page.evaluate(()=>window.__game.piece.x);
    await page.keyboard.press('ArrowLeft');
    assert.equal(await page.evaluate(()=>window.__game.piece.x),x-1);
    await page.keyboard.press('KeyD');
    assert.equal(await page.evaluate(()=>window.__game.piece.x),x);
    await page.keyboard.press('ArrowDown');
    assert.equal(await page.evaluate(()=>window.__game.score),1);
    await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(()=>window.__game.board.flat().filter(Boolean).length),4);
    const serialBeforePause=await page.evaluate(()=>window.__game.spawnSerial);
    const scrollBeforePause=await page.evaluate(()=>window.scrollY);
    await page.keyboard.down('Space');
    await page.keyboard.down('Space');
    await page.keyboard.up('Space');
    assert.equal(await page.locator('#tetris-soundtrack').evaluate(media=>media.paused),true,'Music pauses with the game');
    assert.equal(await page.evaluate(()=>window.__game.paused),true);
    assert.equal(await page.evaluate(()=>window.__game.spawnSerial),serialBeforePause,'Space pauses without dropping');
    assert.equal(await page.evaluate(()=>window.scrollY),scrollBeforePause,'Space does not scroll the page');
    const snapshot=await page.evaluate(()=>JSON.stringify(window.__game.piece));
    await page.waitForTimeout(900);
    assert.equal(await page.evaluate(()=>JSON.stringify(window.__game.piece)),snapshot);
    await page.keyboard.press('Space');
    assert.equal(await page.evaluate(()=>window.__game.paused),false);
    await checkMusic(page);
    await checkFeedback(page,name);
    if(mobile) await checkTouch(page,context);
    // Exercise every actual renderer tile, not just colour constants in source.
    // A representative mixed stack also makes the optional screenshot useful.
    await page.evaluate(()=>{
      const types=window.PitStack.TYPES;
      window.__game.board.forEach(row=>row.fill(null));
      for(let x=0;x<7;x++) window.__game.board[19][x]=types[x];
      for(let y=16;y<19;y++) for(let x=0;x<10;x++) {
        if((x+y)%4!==0 && x<y-9) window.__game.board[y][x]=types[(x+y)%7];
      }
      window.__game.revision++;
    });
    await page.waitForTimeout(80);
    const contrast=await page.evaluate(()=>{
      const canvas=document.getElementById('tetris-canvas'),ctx=canvas.getContext('2d');
      const sample=(x,y)=>Array.from(ctx.getImageData(Math.floor(x*canvas.width/320),Math.floor(y*canvas.height/640),1,1).data).slice(0,3);
      const luminance=rgb=>rgb.map(v=>{const n=v/255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4;}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
      const background=luminance(sample(16,48));
      return {image:getComputedStyle(document.getElementById('tetris-machine')).backgroundImage,
        ratios:Array.from({length:7},(_,x)=>(luminance(sample(x*32+16,624))+.05)/(background+.05))};
    });
    assert.equal(contrast.image,'none','Scenery is isolated in its own layer; board remains opaque');
    for(const ratio of contrast.ratios) assert.ok(ratio>=4.5,`${name}: each tile has at least 4.5:1 contrast, got ${ratio}`);
    const measure=()=>page.evaluate(()=>{
      const machine=document.getElementById('tetris-machine').getBoundingClientRect();
      const canvas=document.getElementById('tetris-canvas'),board=canvas.getBoundingClientRect();
      const telemetry=document.querySelector('.tetris-telemetry').getBoundingClientRect();
      return {aspect:board.height/board.width,canvasAspect:canvas.height/canvas.width,top:board.top-machine.top,
        bottom:machine.bottom-board.bottom,
        gap:telemetry.left-board.right,overflow:document.documentElement.scrollWidth-window.innerWidth,
        fullscreen:document.body.classList.contains('tetris-fullscreen'), machineWidth:machine.width,
        toolbarButtons:Array.from(document.querySelectorAll('.tetris-toolbar button')).map(button=>{
          const rect=button.getBoundingClientRect();return [rect.left-machine.left,rect.right-machine.right];
        }),
        toolbarFits:Array.from(document.querySelectorAll('.tetris-toolbar button')).every(button=>{
          const rect=button.getBoundingClientRect();return rect.left>=machine.left && rect.right<=machine.right;
        })};
    });
    let metrics=await measure();
    assert.ok(Math.abs(metrics.aspect-2)<.01,`${name}: undistorted board ${JSON.stringify(metrics)}`);
    assert.equal(metrics.canvasAspect,2);assert.ok(metrics.gap>0);assert.ok(metrics.top>=0);assert.ok(metrics.bottom>0);
    assert.ok(metrics.overflow<=1,`${name}: no page overflow`);
    assert.ok(metrics.toolbarFits,`${name}: toolbar buttons stay inside cabinet ${JSON.stringify(metrics)}`);
    await page.locator('#tetris-fullscreen').click();
    await page.waitForFunction(()=>document.getElementById('tetris-machine').classList.contains('is-fullscreen'));
    metrics=await measure();assert.ok(metrics.fullscreen);assert.ok(metrics.top>=0);
    assert.ok(Math.abs(metrics.aspect-2)<.01);
    await page.waitForFunction(()=>{
      const canvas=document.getElementById('tetris-canvas');
      const pixel=canvas.getContext('2d').getImageData(2,2,1,1).data;
      return pixel[0]+pixel[1]+pixel[2]>0;
    });
    if(process.env.TETRIS_PREVIEW_DIR) await page.screenshot({path:path.join(process.env.TETRIS_PREVIEW_DIR,`tetris-${name}.png`)});
    if(mobile) await checkTouch(page,context);
    await page.locator('#tetris-fullscreen').click();
    await page.waitForFunction(()=>!document.body.classList.contains('tetris-fullscreen'));
    // Chromium's native window can finish exiting fullscreen after the DOM event.
    const windowSession=await context.newCDPSession(page);
    const {windowId}=await windowSession.send('Browser.getWindowForTarget');
    await windowSession.send('Browser.setWindowBounds',{windowId,bounds:{windowState:'normal'}});
    await windowSession.detach();
    await page.setViewportSize({width:844,height:390});
    await page.locator('#tetris-fullscreen').click();
    metrics=await measure();assert.ok(metrics.top>=0);
    assert.ok(Math.abs(metrics.aspect-2)<.01);
    console.log(`${name}: keyboard, pause/resume, ${mobile?'trusted touch taps/drags/flick/cancel/multitouch/next-piece guards, ':''}ten full-resolution art venues, inline/fullscreen/landscape geometry, opaque field and all seven tile contrasts >= 4.5:1 passed`);
    await page.evaluate(()=>{
      window.__game.paused=false;window.__game.finish();window.dispatchEvent(new Event('resize'));
    });
    await page.waitForFunction(()=>document.getElementById('tetris-overlay-title').textContent==='Финиш!');
    await page.locator('#tetris-canvas').focus();await page.keyboard.press('Space');
    await page.waitForFunction(()=>window.__game.phase==='running');
    assert.equal(await page.evaluate(()=>window.__game.score),0,'Space restarts after game over');
    await page.locator('#tetris-sound').click();
    await page.locator('#tetris-ghost').click();
    await page.reload();await page.waitForFunction(()=>!!window.PitStackAudio);
    assert.equal(await page.locator('#tetris-sound').getAttribute('aria-pressed'),'false','Muted preference survives reload');
    assert.equal(await page.locator('#tetris-volume').inputValue(),'29','Volume survives reload');
    assert.equal(await page.locator('#tetris-ghost').getAttribute('aria-pressed'),'false','Ghost preference survives reload');
    assert.equal(await page.locator('#tetris-soundtrack').evaluate(m=>m.paused),true);
    await context.close();
  }
  assert.deepEqual(errors,[],'No browser script errors');
} finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
