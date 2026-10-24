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
    const ext=path.extname(target),types={'.js':'text/javascript','.css':'text/css','.png':'image/png'};
    res.setHeader('Content-Type',types[ext]||'application/octet-stream');res.end(await fs.readFile(target));
  }catch {res.writeHead(404);res.end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true});
const errors=[];
try {
  for(const [name,width,height,mobile] of [['desktop',1440,1000,false],['mobile',390,844,true],['small-mobile',320,568,true]]) {
    const context=await browser.newContext({viewport:{width,height},deviceScaleFactor:mobile?3:2,isMobile:mobile,hasTouch:mobile});
    const page=await context.newPage();
    page.on('pageerror',e=>errors.push(String(e)));
    await page.route('https://**/*',route=>route.abort());
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.waitForFunction(()=>!!window.PitStack);
    await page.evaluate(()=>{
      const start=window.PitStack.Game.prototype.start;
      window.PitStack.Game.prototype.start=function(){window.__game=this;return start.call(this);};
    });
    await page.locator('#tetris-start').click();
    await page.waitForFunction(()=>window.__game?.phase==='running');
    await page.waitForFunction(()=>document.getElementById('tetris-overlay').hidden);
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
    if(mobile){
      const rect=await page.locator('[data-action="left"]').boundingBox();
      const before=await page.evaluate(()=>window.__game.piece.x);
      await page.touchscreen.tap(rect.x+rect.width/2,rect.y+rect.height/2);
      assert.equal(await page.evaluate(()=>window.__game.piece.x),before-1);
    }
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
    assert.equal(contrast.image,'none','No illustration behind the play surface');
    for(const ratio of contrast.ratios) assert.ok(ratio>=4.5,`${name}: each tile has at least 4.5:1 contrast, got ${ratio}`);
    const measure=()=>page.evaluate(()=>{
      const machine=document.getElementById('tetris-machine').getBoundingClientRect();
      const canvas=document.getElementById('tetris-canvas'),board=canvas.getBoundingClientRect();
      const controls=document.querySelector('.tetris-controls').getBoundingClientRect();
      const telemetry=document.querySelector('.tetris-telemetry').getBoundingClientRect();
      return {aspect:board.height/board.width,canvasAspect:canvas.height/canvas.width,top:board.top-machine.top,
        bottom:machine.bottom-board.bottom,controls:machine.bottom-controls.bottom,
        gap:telemetry.left-board.right,overflow:document.documentElement.scrollWidth-window.innerWidth,
        fullscreen:document.body.classList.contains('tetris-fullscreen'), machineWidth:machine.width,
        toolbarButtons:Array.from(document.querySelectorAll('.tetris-toolbar button')).map(button=>{
          const rect=button.getBoundingClientRect();return [rect.left-machine.left,rect.right-machine.right];
        }),
        toolbarFits:Array.from(document.querySelectorAll('.tetris-toolbar button')).every(button=>{
          const rect=button.getBoundingClientRect();return rect.left>=machine.left && rect.right<=machine.right;
        }),
        controlsFit:Array.from(document.querySelectorAll('.tetris-controls button')).every(button=>{
          const rect=button.getBoundingClientRect();return rect.left>=machine.left && rect.right<=machine.right;
        })};
    });
    let metrics=await measure();
    assert.ok(Math.abs(metrics.aspect-2)<.01,`${name}: undistorted board ${JSON.stringify(metrics)}`);
    assert.equal(metrics.canvasAspect,2);assert.ok(metrics.gap>0);assert.ok(metrics.top>=0);assert.ok(metrics.bottom>0);
    assert.ok(metrics.controls>=0);assert.ok(metrics.overflow<=1,`${name}: no page overflow`);
    assert.ok(metrics.toolbarFits,`${name}: toolbar buttons stay inside cabinet ${JSON.stringify(metrics)}`);
    assert.ok(metrics.controlsFit,`${name}: all control buttons stay inside cabinet`);
    await page.locator('#tetris-fullscreen').click();
    await page.waitForFunction(()=>document.getElementById('tetris-machine').classList.contains('is-fullscreen'));
    metrics=await measure();assert.ok(metrics.fullscreen);assert.ok(metrics.controls>=0);assert.ok(metrics.top>=0);
    assert.ok(Math.abs(metrics.aspect-2)<.01);
    await page.waitForFunction(()=>{
      const canvas=document.getElementById('tetris-canvas');
      const pixel=canvas.getContext('2d').getImageData(2,2,1,1).data;
      return pixel[0]+pixel[1]+pixel[2]>0;
    });
    if(process.env.TETRIS_PREVIEW_DIR) await page.screenshot({path:path.join(process.env.TETRIS_PREVIEW_DIR,`tetris-${name}.png`)});
    await page.locator('#tetris-fullscreen').click();
    await page.waitForFunction(()=>!document.body.classList.contains('tetris-fullscreen'));
    await page.setViewportSize({width:844,height:390});
    await page.locator('#tetris-fullscreen').click();
    metrics=await measure();assert.ok(metrics.controls>=0);assert.ok(metrics.top>=0);
    assert.ok(Math.abs(metrics.aspect-2)<.01);
    console.log(`${name}: keyboard, pause/resume, ${mobile?'touch, ':''}inline/fullscreen/landscape geometry, no backdrop and all seven tile contrasts >= 4.5:1 passed`);
    await context.close();
  }
  assert.deepEqual(errors,[],'No browser script errors');
} finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
