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
    const ext=path.extname(target),types={'.js':'text/javascript','.css':'text/css','.png':'image/png','.webp':'image/webp'};
    res.setHeader('Content-Type',types[ext]||'application/octet-stream');res.end(await fs.readFile(target));
  }catch {res.writeHead(404);res.end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true});
const errors=[];
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
  await touch('touchStart',[{x,y,id:1}]);await page.keyboard.press('Space');await touch('touchEnd',[]);
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
    });
    const titleArtwork=await page.locator('#tetris-scenery .is-visible img').getAttribute('src');
    await page.locator('#tetris-start').click();
    await page.waitForFunction(()=>window.__game?.phase==='running');
    await page.waitForFunction(()=>document.getElementById('tetris-overlay').hidden);
    assert.equal(await page.locator('#tetris-scenery .is-visible img').getAttribute('src'),titleArtwork,
      'Starting the game keeps the title-screen artwork');
    const x=await page.evaluate(()=>window.__game.piece.x);
    await page.keyboard.press('ArrowLeft');
    assert.equal(await page.evaluate(()=>window.__game.piece.x),x-1);
    await page.keyboard.press('KeyD');
    assert.equal(await page.evaluate(()=>window.__game.piece.x),x);
    await page.keyboard.press('ArrowDown');
    assert.equal(await page.evaluate(()=>window.__game.score),1);
    await page.keyboard.press('Space');
    assert.equal(await page.evaluate(()=>window.__game.board.flat().filter(Boolean).length),4);
    await page.locator('#tetris-pause').click();
    assert.equal(await page.evaluate(()=>window.__game.paused),true);
    const snapshot=await page.evaluate(()=>JSON.stringify(window.__game.piece));
    await page.waitForTimeout(900);
    assert.equal(await page.evaluate(()=>JSON.stringify(window.__game.piece)),snapshot);
    await page.locator('#tetris-start').click();
    assert.equal(await page.evaluate(()=>window.__game.paused),false);
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
    await page.setViewportSize({width:844,height:390});
    await page.locator('#tetris-fullscreen').click();
    metrics=await measure();assert.ok(metrics.top>=0);
    assert.ok(Math.abs(metrics.aspect-2)<.01);
    console.log(`${name}: keyboard, pause/resume, ${mobile?'trusted touch taps/drags/flick/cancel/multitouch/next-piece guards, ':''}ten full-resolution art venues, inline/fullscreen/landscape geometry, opaque field and all seven tile contrasts >= 4.5:1 passed`);
    await context.close();
  }
  assert.deepEqual(errors,[],'No browser script errors');
} finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
