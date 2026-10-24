import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
const scope={window:{}};
vm.runInNewContext(await fs.readFile(new URL('../league/static/league/tetris-feedback.js',import.meta.url),'utf8'),scope);
function fixture(reduced=false) {
  const classes=new Set(),ctx={setTransform(){},clearRect(){},fillRect(){}};
  const canvas={width:320,height:640,getContext:()=>ctx};
  const lights={classList:{add:c=>classes.add(c),remove:c=>classes.delete(c),toggle(c,on){if(on)classes.add(c);else classes.delete(c);}},offsetWidth:0};
  const feedback=new scope.window.PitStackFeedback(canvas,lights,{I:'#3ee6ed'},reduced);
  const game={phase:'running',paused:false,lockSerial:1,clearSerial:0,
    lastLock:{type:'I',cells:[0,1,2,3].map(x=>({x,y:19}))},lastClearCells:[],lastClear:0};
  return {feedback,game,classes};
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
  game.paused=true;feedback.observe(game);assert.ok(classes.has('is-paused'));
  feedback.step(50,true);assert.equal(feedback.chips[0].age,0);
  game.paused=false;game.clearSerial++;feedback.observe(game);assert.equal(feedback.chips.length,120,'Particle work is capped');
  for(let i=0;i<21;i++)feedback.step(50);
  assert.equal(feedback.active,false);assert.equal(feedback.chips.length,0);assert.ok(!classes.has('is-celebrating'));
  feedback.paint();feedback.step(50);assert.equal(feedback.dirty,false,'Settled feedback does not request redraws');
  feedback.reset();assert.equal(feedback.active,false);
}
{
  const {feedback,game,classes}=fixture(true);
  game.clearSerial=1;game.lastClear=4;game.lastClearCells=Array.from({length:40},()=>({x:0,y:19,type:'I'}));
  feedback.observe(game);assert.equal(feedback.lock,null);assert.equal(feedback.chips.length,0,'Reduced motion has no squash or particles');
  assert.ok(classes.has('is-celebrating'));game.phase='over';feedback.observe(game);
  assert.equal(feedback.active,false);assert.ok(!classes.has('is-celebrating'),'Game over cancels all finite effects');
}
console.log('Pit Stack feedback passed: read-only physics, subtle isolated squash, bounded particles, finite lights, pause, reduced motion, cleanup and idle redraw suppression.');
