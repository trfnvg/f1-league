import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
const scope={}; vm.runInNewContext(await fs.readFile(new URL('../league/static/league/tetris-engine.js',import.meta.url),'utf8'),scope);
const {Game,TYPES,SHAPES,cells}=scope.PitStack;
function settle(game){ for(let i=0;i<3;i++) game.update(100); }
function boardInvariant(game){
  assert.equal(game.board.length,20);
  for(const row of game.board){ assert.equal(row.length,10); for(const type of row) assert.ok(type===null||TYPES.includes(type)); }
  assert.ok(Number.isSafeInteger(game.score));
  if(game.piece) assert.ok(game.fits(game.piece));
}
assert.equal(TYPES.length,7);
{
  const game=new Game(()=>5/7+.001);game.start();
  const matrix=JSON.stringify(game.piece.matrix),serial=game.spawnSerial;
  assert.equal(game.turn(),true);assert.notEqual(JSON.stringify(game.piece.matrix),matrix);
  assert.equal(game.turn(-1),true);assert.equal(JSON.stringify(game.piece.matrix),matrix);
  assert.equal(game.turn(0),false);game.drop();assert.equal(game.spawnSerial,serial+1);
}
{
  const game=new Game(()=>0);game.start();
  game.elapsed=44990;game.update(10);
  assert.equal(game.pace,0);assert.equal(game.gravity,800,'45 seconds no longer increases difficulty');
  game.elapsed=3600000;
  assert.equal(game.pace,0);assert.equal(game.gravity,800,'Even a long run cannot increase speed without lines');
  game.pause();const elapsed=game.elapsed;
  for(let i=0;i<100;i++)game.update(100);
  assert.equal(game.elapsed,elapsed,'Pause must not increase difficulty');
  game.start();assert.equal(game.elapsed,0);assert.equal(game.gravity,800);
  game.level=999;game.update(100);
  assert.equal(game.piece.y,5);assert.ok(game.fallClock<1e-6);
  game.update(50);assert.equal(game.piece.y,8);assert.ok(game.fallClock<1e-6);
  assert.equal(game.lockDelay,220);
}
{
  const frames=[48,43,38,33,28,23,18,13,8,6,5,5,5,4,4,4,3,3,3,2,2,2,2,2,2,2,2,2,2,1];
  const game=new Game(()=>0);game.start();
  for(let index=0;index<frames.length;index++) {
    game.level=index+1;
    assert.equal(game.pace,index);
    assert.equal(game.gravity,frames[index]*1000/60,`NES speed tier ${index}`);
  }
  for(const before of [9,19,49,89,99,119,129,159,189,279,289,299,999]) {
    game.start();game.lines=before;game.level=1+Math.floor(before/10);
    game.board[19].fill('J');game.clearing=[19];game.phase='clearing';game.resolveClear();
    assert.equal(game.lines,before+1);
    assert.equal(game.level,1+Math.floor((before+1)/10),'Every ten cleared lines advances exactly one tier');
    assert.equal(game.gravity,frames[Math.min(29,Math.floor((before+1)/10))]*1000/60);
  }
  for(const [steps,dt] of [[2,100],[4,50],[12,1000/60]]) {
    game.start();game.level=30;
    for(let i=0;i<steps;i++)game.update(dt);
    assert.equal(game.piece.y,11,'Fast gravity handles multiple cells and different frame intervals');
    assert.ok(game.fallClock<1e-6);
  }
  game.start();game.level=30;game.fallClock=16;
  game.down();assert.equal(game.piece.y,0);assert.equal(game.fallClock,16);
  game.update(1);assert.equal(game.piece.y,1,'Soft drop must not postpone natural high-speed gravity');
  assert.equal(game.score,1,'Natural gravity adds no soft-drop points');
}
for(const type of TYPES) assert.equal(SHAPES[type].flat().filter(Boolean).length,4);
for(let index=0;index<TYPES.length;index++)for(let turns=0;turns<4;turns++) {
  const game=new Game(()=>index/7+.001);game.start();
  for(let y=17;y<20;y++)for(let x=0;x<10;x++)if((x+y)%3!==0)game.board[y][x]='J';
  for(let i=0;i<turns;i++)game.turn();
  if(turns%2)game.move(-1);else game.move(1);
  const before=JSON.stringify({board:game.board,piece:game.piece,score:game.score,elapsed:game.elapsed});
  const landing=game.landing();
  assert.ok(game.fits(landing));assert.equal(game.fits({...landing,y:landing.y+1}),false);
  assert.equal(JSON.stringify({board:game.board,piece:game.piece,score:game.score,elapsed:game.elapsed}),before,'Ghost projection is read-only');
  const expected=JSON.stringify(cells(landing));game.drop();
  assert.equal(JSON.stringify(game.lastLock.cells),expected,'Ghost exactly matches actual hard-drop landing');
  assert.equal(game.lockSerial,1);
}
for(let index=0;index<7;index++){
  const game=new Game(()=>index/7+.001);game.start();
  assert.equal(game.piece.type,TYPES[index]); assert.equal(cells(game.piece).length,4);
  for(let step=0;step<30;step++) game.move(-1);
  assert.equal(Math.min(...cells(game.piece).map(p=>p.x)),0);
  for(let turn=0;turn<8;turn++){game.turn();assert.ok(game.fits(game.piece));}
  for(let step=0;step<30;step++) game.move(1);
  assert.equal(Math.max(...cells(game.piece).map(p=>p.x)),9);
  game.drop(); boardInvariant(game);
  assert.equal(game.board.flat().filter(Boolean).length,4);
}
for(let count=1;count<=4;count++){
  const game=new Game(()=>0);game.start();
  for(let y=20-count;y<20;y++) game.board[y]=Array(10).fill('J');
  for(let y=20-count;y<20;y++) game.board[y][5]=null;
  game.piece={type:'I',matrix:[[1],[1],[1],[1]],x:5,y:16};
  game.lock(); assert.equal(game.phase,'clearing');assert.equal(game.clearing.length,count);
  assert.equal(game.move(1),false);settle(game);
  assert.equal(game.lines,count);assert.equal(game.score,[0,40,100,300,1200][count]);
  assert.equal(game.lastClearCells.length,count*10,'Visual snapshot retains cleared cells without changing score');
  assert.equal(game.board.flat().filter(Boolean).length,4-count);
  boardInvariant(game);
}
{
  const game=new Game(()=>0);game.start(); game.lines=9;
  game.board[19]=Array(10).fill('J'); game.board[19][5]=null;
  game.piece={type:'I',matrix:[[1],[1],[1],[1]],x:5,y:16};game.lock();settle(game);
  assert.equal(game.level,2);assert.equal(game.score,40);assert.ok(game.gravity<800);
  const y=game.piece.y;game.pause();for(let i=0;i<100;i++)game.update(100);
  assert.equal(game.piece.y,y);assert.equal(game.drop(),false);assert.equal(game.move(1),false);
  game.pause();for(let i=0;i<10;i++)game.update(100);assert.ok(game.piece.y>y);
  game.level=999;assert.equal(game.gravity,1000/60);
}
{
  const game=new Game(()=>3/7+.001);game.start();
  for(let i=0;i<20;i++)game.drop();
  assert.equal(game.phase,'over');assert.equal(game.piece,null);assert.equal(game.drop(),false);
  game.start();assert.equal(game.phase,'running');assert.equal(game.score,0);assert.equal(game.lines,0);
  assert.equal(game.board.flat().filter(Boolean).length,0);
  const score=game.score;game.down();assert.equal(game.score,score+1);
  game.drop();assert.ok(game.score>score+1);
  for(let i=0;i<100;i++)game.move(-1);
  game.piece.y=18;game.update(100);game.update(100);game.update(100);
  assert.equal(game.board.flat().filter(Boolean).length,4);
  game.update(60);assert.equal(game.board.flat().filter(Boolean).length,8);
}
let seed=14;const random=()=>{seed=(1664525*seed+1013904223)>>>0;return seed/4294967296;};
const game=new Game(random);let runs=0;
for(let step=0;step<150000;step++){
  if(['ready','over'].includes(game.phase)){game.start();runs++;}
  const action=Math.floor(random()*7);
  if(action===0)game.move(-1);if(action===1)game.move(1);if(action===2)game.turn();
  if(action===3)game.down();if(action===4)game.drop();
  game.update(20+random()*80);boardInvariant(game);
}
console.log(`Pit Stack rules passed: all 30 NES speed tiers, line-only progression, no timer acceleration, high-speed frame independence, seven shapes, walls/rotation, clears/scoring, pause, soft/hard drop, lock delay, restart; 150000 stress steps across ${runs} runs.`);
