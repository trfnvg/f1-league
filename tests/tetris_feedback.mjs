import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
const scope={window:{}};
vm.runInNewContext(await fs.readFile(new URL('../league/static/league/tetris-feedback.js',import.meta.url),'utf8'),scope);
function fixture(reduced=false) {
  const calls=[],classes=new Set(),ctx={
    setTransform(){},clearRect(){},save(){},restore(){},beginPath(){},rect(){},clip(){},translate(){},rotate(){},
    createLinearGradient(){calls.push('gradient');return {addColorStop(){}};},
    fillRect(...args){assert.ok(args.every(Number.isFinite));assert.ok(args[2]>=0 && args[3]>=0);calls.push(args);},
  };
  const canvas={width:320,height:640,getContext:()=>ctx};
  const lights={classList:{add:c=>classes.add(c),remove:c=>classes.delete(c),toggle(c,on){if(on)classes.add(c);else classes.delete(c);}},offsetWidth:0};
  const feedback=new scope.window.PitStackFeedback(canvas,lights,{I:'#3ee6ed'},reduced);
  const game={phase:'running',paused:false,lockSerial:1,clearSerial:0,
    lastLock:{type:'I',cells:[0,1,2,3].map(x=>({x,y:19}))},lastClearCells:[],lastClear:0,
    clearClock:0,clearing:[]};
  return {feedback,game,classes,calls};
}
{
  const {feedback,game,classes}=fixture(),snapshot=JSON.stringify(game);
  feedback.observe(game);feedback.step(70);
  assert.ok(feedback.squash(1,19)<1 && feedback.squash(1,19)>.94);
  assert.equal(feedback.squash(7,19),1);
  const age=feedback.lock.age;feedback.step(50,true);assert.equal(feedback.lock.age,age,'Pause freezes landing animation');
  feedback.paint();feedback.step(50);feedback.step(50);assert.equal(feedback.squash(1,19),1);
  assert.equal(JSON.stringify(game),snapshot,'Effects do not mutate physics state');
  game.clearSerial=1;game.lastClear=4;game.lastClearCells=Array.from({length:40},(_,i)=>({x:i%10,y:16+Math.floor(i/10),type:'I'}));
  feedback.observe(game);assert.equal(feedback.chips.length,80);assert.ok(classes.has('is-celebrating'));
  assert.equal(feedback.echoes.length,4);assert.ok(feedback.echoes.every(echo=>echo.gold));
  game.paused=true;feedback.observe(game);assert.ok(classes.has('is-paused'));
  feedback.step(50,true);assert.equal(feedback.chips[0].age,0);
  game.paused=false;game.clearSerial++;feedback.observe(game);assert.equal(feedback.chips.length,120,'Particle work is capped');
  assert.equal(feedback.echoes.length,8,'Line echoes are bounded too');
  feedback.paint();
  for(let i=0;i<21;i++)feedback.step(50);
  assert.equal(feedback.active,false);assert.equal(feedback.chips.length,0);assert.ok(!classes.has('is-celebrating'));
  feedback.paint();feedback.step(50);assert.equal(feedback.dirty,false,'Settled feedback does not request redraws');
  feedback.reset();assert.equal(feedback.active,false);
}
for(let count=1;count<=4;count++) {
  const {feedback,game,calls}=fixture();
  game.phase='clearing';game.clearing=Array.from({length:count},(_,i)=>19-i);
  feedback.observe(game);
  const rows=feedback.charge.rows;
  for(const ms of [0,35,90,145,179]) {
    game.clearClock=ms;const snapshot=JSON.stringify(game);
    feedback.observe(game);feedback.paint();
    assert.equal(feedback.charge.age,ms,'Light pass follows the real engine clock');
    assert.equal(feedback.charge.rows,rows,'No row snapshot allocations on every frame');
    assert.equal(JSON.stringify(game),snapshot,'Light pass cannot affect the game');
  }
  game.paused=true;const age=feedback.charge.age;
  feedback.step(50,true);feedback.observe(game);assert.equal(feedback.charge.age,age);
  assert.equal(calls.filter(call=>call==='gradient').length,1,'One reusable light ramp, not per-frame gradients');
  game.paused=false;game.phase='running';feedback.observe(game);assert.equal(feedback.charge,null);
  feedback.reset();feedback.paint();feedback.step(50);assert.equal(feedback.dirty,false);
}
{
  const {feedback}=fixture();
  const piece={type:'I',x:4,y:0,matrix:[[1],[1],[1],[1]]};
  const landing={...piece,y:16},snapshot=JSON.stringify({piece,landing});
  feedback.trace(piece,landing);assert.equal(feedback.trail.columns.length,1);
  assert.equal(feedback.trail.columns[0].bottom,20,'Drop trail includes the full column, not just its top tile');
  feedback.paint();feedback.step(50,true);assert.equal(feedback.trail.age,0);
  for(let i=0;i<3;i++)feedback.step(50);
  assert.equal(feedback.trail,null);assert.equal(feedback.active,false);
  feedback.paint();feedback.step(50);assert.equal(feedback.dirty,false);
  feedback.trace(piece,{...piece,y:1});assert.equal(feedback.trail,null,'Short drops do not add visual clutter');
  assert.equal(JSON.stringify({piece,landing}),snapshot);
}
{
  const {feedback,game,classes}=fixture(true);
  game.clearSerial=1;game.lastClear=4;game.lastClearCells=Array.from({length:40},()=>({x:0,y:19,type:'I'}));
  feedback.observe(game);assert.equal(feedback.lock,null);assert.equal(feedback.chips.length,0,'Reduced motion has no squash or particles');
  assert.equal(feedback.echoes.length,0);
  feedback.trace({type:'I',x:3,y:0,matrix:[[1]]},{y:19});assert.equal(feedback.trail,null);
  assert.ok(classes.has('is-celebrating'));game.phase='over';feedback.observe(game);
  assert.equal(feedback.active,false);assert.ok(!classes.has('is-celebrating'),'Game over cancels all finite effects');
}
console.log('Pit Stack feedback passed: read-only 1–4 line sweeps, bounded shards/echoes, one cached light ramp, landing/drop trails, finite lights, pause, reduced motion, cleanup and idle redraw suppression.');
