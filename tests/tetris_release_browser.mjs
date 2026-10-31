// Real public template + real keyboard + Python authoritative verifier, synthetic data only.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
const root=new URL('..',import.meta.url),pythonBin=process.env.PYTHON_BIN||'python3';
const automation=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const rendered=spawnSync(pythonBin,['-c',`
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django;django.setup()
from django.test import override_settings
from django.template.loader import render_to_string
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from types import SimpleNamespace
from league.arcade_rewards import WHEEL_SECTORS
with override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}}):
    print(render_to_string('arcade_tetris.html',dict(user=User(id=1,username='Release player'),
        arcade_scoring_open=True,arcade_library_mode=True,tetris_save_results=True,
        tetris_start_url='/start',tetris_finish_url='/finish',tetris_board_url='/board',
        leaderboard_title='Глобальный рейтинг',current_season={'year':2026},
        wheel_event=SimpleNamespace(id=1,name='Сан-Паулу, Бразилия',deadline=timezone.now()+timedelta(days=1)),
        wheel_sectors=list(WHEEL_SECTORS),now=timezone.now())))
`],{cwd:root,env:{...process.env,DATABASE_URL:'sqlite:///:memory:'},encoding:'utf8'});
assert.equal(rendered.status,0,rendered.stderr);
const attempts=new Map(),proofs=[];let serial=0,board={records:[],total_attempts:0,board_title:'Глобальный рейтинг'};
const server=http.createServer(async(req,res)=>{
  const url=new URL(req.url,'http://localhost');
  const send=(data,status=200)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(data));};
  if(url.pathname==='/start') {
    const id=++serial,seed=540+id;attempts.set(id,{seed,started:Date.now()});
    send({attempt_id:id,seed,rules_version:1,max_ticks:864000,max_inputs:30000});return;
  }
  if(url.pathname==='/finish') {
    let body='';for await(const chunk of req)body+=chunk;
    const proof=JSON.parse(body),attempt=attempts.get(proof.attempt_id);proofs.push(proof);
    assert.ok(attempt);assert.equal('score' in proof,false);
    const result=spawnSync(pythonBin,['-c',`import json,sys;from league.tetris_rules import verify;d=json.load(sys.stdin);print(verify(d['seed'],d['ticks'],d['inputs'],d['elapsed']))`],
      {cwd:root,encoding:'utf8',input:JSON.stringify({...proof,seed:attempt.seed,elapsed:(Date.now()-attempt.started)/1000})});
    if(result.status!==0){send({error:result.stderr},400);return;}
    const score=Number(result.stdout.trim());
    board={records:[{rank:1,username:'Release player',score,attempts:1,is_current_user:true}],
      record:score,board_record:score,board_attempts:1,rank:1,total_attempts:1,board_title:'Глобальный рейтинг'};
    send(board);return;
  }
  if(url.pathname==='/board'){send(board);return;}
  if(url.pathname==='/'){res.setHeader('Content-Type','text/html; charset=utf-8');res.end(rendered.stdout);return;}
  const base=path.resolve(new URL('league/static',root).pathname),target=path.resolve(base,url.pathname.replace(/^\/static\//,''));
  if(!url.pathname.startsWith('/static/')||!target.startsWith(base+path.sep)){res.writeHead(404);res.end();return;}
  try {const ext=path.extname(target);res.setHeader('Content-Type',({'.js':'text/javascript','.css':'text/css','.webp':'image/webp','.png':'image/png','.svg':'image/svg+xml','.m4a':'audio/mp4'})[ext]||'application/octet-stream');res.end(await fs.readFile(target));}
  catch{res.writeHead(404);res.end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await automation[process.env.BROWSER_ENGINE||'chromium'].launch(),errors=[];
try {
  for(const width of [1440,390,320]) {
    const context=await browser.newContext({viewport:{width,height:900},hasTouch:width<500,isMobile:width<500,reducedMotion:'reduce'});
    const page=await context.newPage();page.on('pageerror',error=>errors.push(String(error)));
    await page.route('https://**/*',route=>route.abort());
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    // The live bonus panel must load its shared CSS, not render as an unstyled
    // gradient strip and an original-size hub image below the new game.
    await page.locator('.arcade-wheel-label').first().waitFor();
    const wheel=await page.locator('.arcade-wheel-machine').boundingBox();
    assert.ok(wheel.width>150 && wheel.width<=380);
    assert.ok(Math.abs(wheel.width-wheel.height)<2,'Wheel must remain square');
    const disc=await page.locator('#arcade-wheel-disc').boundingBox();
    assert.ok(disc.width>130 && Math.abs(disc.width-disc.height)<2);
    const hub=await page.locator('.arcade-wheel-hub img').boundingBox();
    assert.ok(hub.width<=90 && hub.height<=90,'Hub image must be constrained');
    assert.equal(await page.locator('.arcade-wheel-layout').evaluate(el=>getComputedStyle(el).display),'grid');
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    if(process.env.TETRIS_PREVIEW_DIR) {
      await page.locator('#arcade-wheel-panel').screenshot({path:path.join(process.env.TETRIS_PREVIEW_DIR,`tetris-bonus-${width}.png`)});
    }
    await page.locator('#tetris-start').click();
    await page.waitForFunction(()=>document.getElementById('tetris-overlay').hidden);
    await page.keyboard.press('KeyP');
    const ticks=await page.evaluate(()=>window.PitStackActiveSession.ticks);
    await page.waitForTimeout(180);
    assert.equal(await page.evaluate(()=>window.PitStackActiveSession.ticks),ticks,'Pause is excluded from replay');
    await page.keyboard.press('Space');
    for(let i=0;i<60;i++) {
      if(await page.locator('#tetris-overlay-title').textContent()==='Финиш!')break;
      await page.keyboard.press('Space');await page.waitForTimeout(70);
    }
    await page.waitForFunction(()=>document.getElementById('tetris-save-status').textContent==='Результат сохранён.');
    assert.ok(board.board_record>0);
    assert.equal(await page.locator('#tetris-leaderboard-list .arcade-record-score').textContent(),board.board_record.toLocaleString('ru-RU'));
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    if(process.env.TETRIS_PREVIEW_DIR)await page.screenshot({path:path.join(process.env.TETRIS_PREVIEW_DIR,`tetris-release-${width}.png`),fullPage:true});
    await context.close();
    console.log(`Pit Stack public ${width}px: seed issued, pause excluded, keyboard hard drops, server-verified finish, saved leaderboard and no overflow passed.`);
  }
  assert.equal(proofs.length,3);assert.deepEqual(errors,[]);
} finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
