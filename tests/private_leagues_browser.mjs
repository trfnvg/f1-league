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
from importlib import import_module
from types import SimpleNamespace
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.core.management import call_command
from django.test import Client,override_settings
from django.contrib.auth.models import User
from django.apps import apps
from django.db import connection
from django.utils import timezone
from datetime import timedelta
from league.models import Season,Event,Prediction,Score,League
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
    for i in range(7,29):
        Event.objects.create(season_year=season.year,name=f'Гран-при {i}',round_number=i,deadline=timezone.now()+timedelta(days=i*7),race_datetime=timezone.now()+timedelta(days=i*7+1))
    c=Client();c.force_login(owner)
    urls={'/':reverse('league:friend_leagues')+'?all=1','/overview/':reverse('league:home'),'/detail/':reverse('league:friend_league',args=[ls.league_id]),'/create/':reverse('league:friend_league_create'),'/event/':reverse('league:friend_league_event',args=[ls.league_id,event.pk]),'/join/':reverse('league:friend_league_join',args=[token]),'/settings/':reverse('league:friend_league_settings',args=[ls.league_id])}
    pages={name:c.get(url).content.decode() for name,url in urls.items()}
    pages['/invites/']=c.post(reverse('league:friend_league_invites',args=[ls.league_id])).content.decode()
    pages['/delete/']=c.get(reverse('league:friend_league_delete',args=[ls.league_id])).content.decode()
    Event.objects.filter(pk=event.pk).update(deadline=timezone.now()-timedelta(hours=1))
    pages['/closed-gp/']=c.get(reverse('league:friend_league',args=[ls.league_id])).content.decode()
    Event.objects.filter(pk=event.pk).update(deadline=event.deadline)
    Event.objects.filter(pk=event.pk).update(deadline=timezone.now()-timedelta(days=2),race_datetime=timezone.now()-timedelta(days=1))
    pages['/review/']=c.get(reverse('league:friend_league_event',args=[ls.league_id,event.pk]),{'manage':'1'}).content.decode()
    Event.objects.filter(pk=event.pk).update(deadline=event.deadline,race_datetime=event.race_datetime)
    owner.username='trfnvg';owner.save(update_fields=['username'])
    player=User.objects.get(username='George_Russell')
    Prediction.objects.create(user=player,event=event,p1='russell')
    Score.objects.create(user=player,event=event,points=245,prediction_points=242,duel_adjustment=3)
    import_module('league.migrations.0043_register_fastlap_main').register_main(apps,SimpleNamespace(connection=connection))
    main=League.objects.get(legacy_key='original-friends')
    pages['/main/']=c.get(reverse('league:friend_league',args=[main.pk])).content.decode()
    pages['/']=c.get(reverse('league:friend_leagues'),{'all':'1'}).content.decode()
    pages['/avatars/']=c.get(reverse('league:player_profile',args=[owner.pk])).content.decode()
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
      if(!['/avatars/','/overview/'].includes(url))assert.equal(await page.locator('.leagues-page').count(),1);
      if(url==='/overview/'){
        assert.equal(await page.locator('#calendar').count(),1);
        assert.ok(await page.locator('.nightshift-nav-item').count()>=5);
        assert.equal(await page.locator('.nightshift-sidebar').isVisible(),width>780);
        assert.equal(await page.locator('.nightshift-mobile-nav').isVisible(),width<=780);
        if(width<=1100)assert.equal(await page.locator('.site-menu-btn').isVisible(),true);
      }
      if(url==='/avatars/'){
        // Exercise every historical avatar variant under the actual profile
        // page's inline styles, including the blue opponent and editable state.
        await page.evaluate(()=>{
          const fixture=document.createElement('div');fixture.className='duel-player-b';
          for(const name of ['mini-avatar','table-avatar','western-avatar','duel-avatar','round-winner-avatar','leagues-avatar']){
            const avatar=document.createElement('span');avatar.className=name;
            avatar.style.cssText='display:inline-flex;width:64px;height:64px';fixture.append(avatar);
          }
          document.querySelector('main').append(fixture);
        });
      }
      const avatarSelector='.mini-avatar,.table-avatar,.profile-avatar,.western-avatar,.duel-avatar,.round-winner-avatar,.leagues-avatar';
      await page.locator(avatarSelector).evaluateAll(avatars=>{
        const svg='<svg xmlns="http://www.w3.org/2000/svg" width="180" height="100"><path fill="#4ba" d="M0 0h180v100H0z"/><circle fill="#fc8" cx="90" cy="50" r="35"/></svg>';
        for(const avatar of avatars){
          const img=document.createElement('img');img.src='data:image/svg+xml,'+encodeURIComponent(svg);
          avatar.replaceChildren(img);
        }
      });
      const checkAvatars=async()=>assert.deepEqual(await page.locator(avatarSelector).evaluateAll(avatars=>avatars.flatMap(avatar=>{
        const style=getComputedStyle(avatar),image=getComputedStyle(avatar.querySelector('img')),box=avatar.getBoundingClientRect();
        const valid=style.borderRadius==='50%'&&style.boxShadow==='none'&&['Top','Right','Bottom','Left'].every(side=>style[`border${side}Width`]==='0px'&&style[`padding${side}`]==='0px')&&Math.abs(box.width-box.height)<1&&image.objectFit==='cover'&&image.objectPosition==='50% 50%';
        return valid?[]:[{className:avatar.className,border:style.border,shadow:style.boxShadow,width:box.width,height:box.height}];
      })),[],`${width} ${url}: player avatars have no frames and share a circular centre-cover crop`);
      await checkAvatars();
      if(url==='/avatars/'){
        assert.equal(await page.locator('.profile-avatar-editable').count(),1);
        await page.locator('.profile-avatar-editable').hover();await checkAvatars();
        await page.locator('.profile-avatar-editable').evaluate(node=>node.setAttribute('aria-expanded','true'));
        await checkAvatars();
      }
      if(url==='/detail/'){
        assert.equal(await page.locator('.leaderboard-table tbody tr').count(),4);
        const table=page.locator('.leaderboard-scroll-x');
        await table.evaluate(node=>node.scrollLeft=node.scrollWidth);
        const safe=await page.locator('.leaderboard-table tbody tr').evaluateAll(rows=>rows.every(row=>{
          const name=row.querySelector('.col-player').getBoundingClientRect(),points=row.querySelector('.col-total').getBoundingClientRect();return name.right<=points.left+1;
        }));
        assert.ok(safe,`${width}: pinned names and scores do not overlap after scrolling`);
        await page.locator('.league-switch summary').click();
        assert.ok(await page.locator('.league-switch a').last().isVisible());
        await page.locator('.league-switch summary').click();
      }
      if(url==='/')assert.equal(await page.locator('.leagues-card h3').first().innerText(),'Fastlap Main');
      if(url==='/main/'){
        assert.equal(await page.locator('.leaderboard-table tbody tr').count(),1);
        assert.equal(await page.locator('.total-chip').innerText(),'245');
      }
      if(url==='/closed-gp/'){
        assert.equal(await page.locator('#current-gp-title').innerText(),'Гран-при Монако');
        assert.match(await page.locator('.league-race-status').innerText(),/Прогнозы закрыты/);
        assert.match(await page.locator('.league-race-cta').innerText(),/Смотреть прогнозы/);
      }
      if(url==='/delete/'){
        assert.equal(await page.locator('#delete-confirmation').getAttribute('required'),'');
        assert.equal(await page.locator('.league-delete-confirm form[method="post"]').count(),1);
      }
      if(url==='/review/'){
        await page.locator('.league-day-panel summary').click();
        assert.equal(await page.locator('#id_drivers input').count(),22);
        assert.equal(await page.locator('#id_drivers input:disabled').count(),22);
        await page.locator('#id_use_official').uncheck();
        assert.equal(await page.locator('#id_drivers input:disabled').count(),0);
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      }
      if(process.env.LEAGUE_PREVIEW_DIR&&['/','/overview/','/detail/','/closed-gp/','/settings/','/delete/'].includes(url)){
        await fs.mkdir(process.env.LEAGUE_PREVIEW_DIR,{recursive:true});
        await page.screenshot({path:path.join(process.env.LEAGUE_PREVIEW_DIR,`leagues-${width}-${url==='/'?'index':url.replaceAll('/','')}.png`),fullPage:true});
      }
    }
    assert.deepEqual(errors,[],`${width}: browser runtime errors`);
    await page.close();
  }
  console.log('Nightshift shell and private leagues: 13 real Django pages × 5 desktop/mobile widths passed, including navigation breakpoints, player avatar variants, 23 GP columns and league actions.');
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
