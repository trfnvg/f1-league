// Ephemeral in-memory Django database; the user's database is never migrated.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const rendered=spawnSync(process.env.PYTHON_BIN||'python3',['-c',`
import os,json
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.core.management import call_command
from django.test import Client,override_settings
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from league.models import Season,Event
from league.leagues import create_league,create_invite,accept_invite
from django.urls import reverse
call_command('migrate',verbosity=0)
with override_settings(ALLOWED_HOSTS=['testserver'],STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}}):
    owner=User.objects.create_user('Long_administrator_name',is_staff=True)
    season=Season.get_active()
    event=Event.objects.create(season_year=season.year,name='Гран-при Монако',round_number=6,deadline=timezone.now()+timedelta(days=2),race_datetime=timezone.now()+timedelta(days=3))
    ls=create_league(owner=owner,name='Гоночная компания друзей с очень длинным названием',season=season,start_event=event,ruleset='paddock')
    _,token=create_invite(actor=owner,league_season=ls)
    for name in ['Аня','Очень_длинное_имя_участника','George_Russell']:
        accept_invite(user=User.objects.create_user(name),token=token)
    c=Client();c.force_login(owner)
    urls={'/':reverse('league:friend_leagues'),'/detail/':reverse('league:friend_league',args=[ls.league_id]),'/create/':reverse('league:friend_league_create'),'/event/':reverse('league:friend_league_event',args=[ls.league_id,event.pk]),'/join/':reverse('league:friend_league_join',args=[token])}
    pages={name:c.get(url).content.decode() for name,url in urls.items()}
    pages['/invites/']=c.post(reverse('league:friend_league_invites',args=[ls.league_id])).content.decode()
    print(json.dumps(pages))
`],{cwd:root,encoding:'utf8',env:{...process.env,DATABASE_URL:'sqlite:///:memory:'},maxBuffer:8*1024*1024});
assert.equal(rendered.status,0,rendered.stderr);
const pages=JSON.parse(rendered.stdout);
const server=http.createServer(async(req,res)=>{
  const url=new URL(req.url,'http://localhost');
  if(pages[url.pathname]){res.setHeader('Content-Type','text/html; charset=utf-8');res.end(pages[url.pathname]);return;}
  const target=path.resolve(root,'league/static',url.pathname.replace(/^\/static\//,''));
  if(!url.pathname.startsWith('/static/')||!target.startsWith(path.join(root,'league/static')+path.sep)){res.writeHead(404);res.end();return;}
  try{res.setHeader('Content-Type',({'.js':'text/javascript','.css':'text/css','.png':'image/png','.webp':'image/webp'})[path.extname(target)]||'application/octet-stream');res.end(await fs.readFile(target));}
  catch{res.writeHead(404);res.end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true});
try{
  for(const width of [320,390,768,1101,1440]){
    const page=await browser.newPage({viewport:{width,height:900}});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    for(const url of Object.keys(pages)){
      await page.goto(`http://127.0.0.1:${server.address().port}${url}`,{waitUntil:'networkidle'});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,`${width} ${url}: horizontal page overflow`);
      assert.equal(await page.locator('.leagues-page').count(),1);
      if(url==='/detail/'){
        assert.equal(await page.locator('.leagues-standing').count(),4);
        const safe=await page.locator('.leagues-standing').evaluateAll(rows=>rows.every(row=>{
          const name=row.querySelector('.leagues-player').getBoundingClientRect(),points=row.querySelector('.leagues-points').getBoundingClientRect();return name.right<=points.left;
        }));
        assert.ok(safe,`${width}: names and scores do not overlap`);
      }
      if(process.env.LEAGUE_PREVIEW_DIR&&['/','/detail/','/invites/'].includes(url)){
        await fs.mkdir(process.env.LEAGUE_PREVIEW_DIR,{recursive:true});
        await page.screenshot({path:path.join(process.env.LEAGUE_PREVIEW_DIR,`leagues-${width}-${url==='/'?'index':url.replaceAll('/','')}.png`),fullPage:true});
      }
    }
    assert.deepEqual(errors,[],`${width}: browser runtime errors`);
    await page.close();
  }
  console.log('Private leagues: 6 real Django pages × 5 desktop/mobile widths passed.');
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
