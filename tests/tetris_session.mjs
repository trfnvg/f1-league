import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
const source=await fs.readFile(new URL('../league/static/league/tetris-session.js',import.meta.url),'utf8');
const engine=await fs.readFile(new URL('../league/static/league/tetris-engine.js',import.meta.url),'utf8');
function fixture(enabled=true,videoRecorder=null) {
  const calls=[];let offline=false,start=0;
  const scope={window:{},document:{getElementById:()=>null,querySelector:()=>({value:'csrf-test'})},
    setTimeout,clearTimeout,AbortController,fetch:async(url,options)=>{
      const payload=JSON.parse(options.body);calls.push({url,payload,headers:options.headers});
      if(offline)throw Error('offline');
      return {ok:true,json:async()=>url==='start'?{attempt_id:++start,seed:19,rules_version:1,max_ticks:864000,max_inputs:30000}:{records:[]}};
    }};
  if(videoRecorder)scope.window.ArcadeVideo={create:()=>videoRecorder};
  vm.runInNewContext(engine,scope);vm.runInNewContext(source,scope);
  const run=new scope.window.PitStackSession({dataset:{saveResults:String(enabled),startUrl:'start',finishUrl:'finish'}});
  return {run,Game:scope.window.PitStack.Game,calls,set offline(value){offline=value;}};
}
{
  const events=[];
  const clip={stop:()=>events.push('stop'),upload:id=>events.push(['upload',id]),discard:()=>events.push('discard')};
  const f=fixture(true,{begin:()=>{events.push('begin');return clip;}});
  const game=new f.Game(await f.run.begin());
  assert.equal(events.length,0,'Video does not include the seed request or an old board');
  game.start();f.run.startVideo();f.run.finish();await f.run.saving;
  assert.deepEqual(events,['begin','stop',['upload',1]],'Video is stopped at game end and uploaded only after the result response');
  const preview=fixture(false,{begin:()=>{throw Error('Practice must not record');}});
  await preview.run.begin();preview.run.startVideo();preview.run.finish();
}
{
  const f=fixture();const game=new f.Game(await f.run.begin());game.start();
  assert.equal(f.calls[0].headers['X-CSRFToken'],'csrf-test');
  game.pause();f.run.advance(game,50);assert.equal(f.run.ticks,0,'Pause does not add replay time');game.pause();
  while(game.phase!=='over') {
    if(game.active){f.run.record('drop',game);game.drop();}
    if(game.phase!=='over')f.run.advance(game,50);
  }
  f.run.finish();await f.run.saving;
  const payload=f.calls.at(-1).payload;
  assert.equal(payload.attempt_id,1);assert.equal(payload.rules_version,1);
  assert.ok(payload.inputs.length>0);assert.ok(payload.ticks>0);
  assert.equal('score' in payload,false,'Client does not submit a trusted score');
  f.run.finish();assert.equal(f.calls.length,2,'Only one finish per run');
  assert.equal(f.run.pending,null);
}
{
  const f=fixture();const game=new f.Game(await f.run.begin());game.start();
  f.run.record('drop',game);game.drop();
  f.offline=true;f.run.finish();await f.run.saving;
  assert.ok(f.run.pending,'Network failure retains proof for a retry');
  f.offline=false;await f.run.begin();
  assert.equal(f.calls.filter(call=>call.url==='finish').length,2);
  assert.equal(f.run.attemptId,2,'Previous proof is saved before opening the next run');
}
{
  const f=fixture(false);const game=new f.Game(await f.run.begin());game.start();
  f.run.record('drop',game);game.drop();f.run.advance(game,50);f.run.finish();
  assert.equal(f.calls.length,0,'Guest and admin practice never call result APIs');
  assert.equal(f.run.inputs.length,0);
}
{
  const f=fixture();const game=new f.Game(await f.run.begin());game.start();
  for(let i=0;i<8;i++)assert.equal(f.run.record('left',game),true);
  assert.equal(f.run.record('left',game),false,'Queued input bursts stay within the verifier limit');
  assert.equal(f.run.inputs.length,8);assert.equal(game.phase,'running');
}
console.log('Pit Stack session passed: seeded start, fixed ticks, pause, action-only proof, CSRF, one finish, network retry and isolated guest/admin practice.');
