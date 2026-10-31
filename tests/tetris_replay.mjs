// PYTHON_BIN=/path/to/python node tests/tetris_replay.mjs
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
import {spawnSync} from 'node:child_process';
const scope={};vm.runInNewContext(await fs.readFile(new URL('../league/static/league/tetris-engine.js',import.meta.url),'utf8'),scope);
const {Game,createRandom,TYPES}=scope.PitStack,STEP=1000/60;
const actions=[g=>g.move(-1),g=>g.move(1),g=>g.turn(),g=>g.turn(-1),g=>g.down(),g=>g.drop()];
const runs=[];
for(let seed=0;seed<120;seed++) {
  const game=new Game(createRandom(seed)),random=createRandom(seed+9000);game.start();
  const inputs=[];let ticks=0;
  while(game.phase!=='over'&&ticks<10000) {
    if(game.active && random()<.7) {
      const action=Math.floor(random()*6);inputs.push([ticks,action]);actions[action](game);
    }
    if(game.phase==='over')break;
    game.update(STEP);ticks++;
  }
  assert.equal(game.phase,'over');runs.push({seed,ticks,inputs,expected:game.score});
}
const fixtures=[];
for(const count of [1,2,3,4])for(const level of [1,10,30]) {
  const game=new Game(createRandom(41));game.start();game.level=level;game.lines=(level-1)*10;
  for(let y=20-count;y<20;y++){game.board[y].fill('J');game.board[y][5]=null;}
  game.piece={type:'I',matrix:[[1],[1],[1],[1]],x:5,y:16};
  game.drop();for(let i=0;i<11;i++)game.update(STEP);
  fixtures.push({count,level,expected:{score:game.score,lines:game.lines,level:game.level,
    board:game.board.map(row=>row.map(type=>type===null?null:TYPES.indexOf(type))),
    piece:{x:game.piece.x,y:game.piece.y,kind:TYPES.indexOf(game.piece.type),matrix:game.piece.matrix}}});
}
const python=spawnSync(process.env.PYTHON_BIN||'python3',['-c',`
import json,sys
from league.tetris_rules import Game,verify
data=json.load(sys.stdin)
scores=[verify(r['seed'],r['ticks'],r['inputs'],r['ticks']/60+5) for r in data['runs']]
states=[]
for f in data['fixtures']:
    g=Game(41);g.level=f['level'];g.lines=(g.level-1)*10
    for y in range(20-f['count'],20):
        g.board[y]=[1]*10;g.board[y][5]=None
    g.kind=0;g.matrix=[[1],[1],[1],[1]];g.x=5;g.y=16
    g.action(5)
    for _ in range(11):g.update()
    states.append(dict(score=g.score,lines=g.lines,level=g.level,board=g.board,
        piece=dict(x=g.x,y=g.y,kind=g.kind,matrix=g.matrix)))
print(json.dumps(dict(scores=scores,states=states)))
`],{cwd:new URL('..',import.meta.url),encoding:'utf8',input:JSON.stringify({runs,fixtures}),maxBuffer:8*1024*1024});
assert.equal(python.status,0,python.stderr);
const result=JSON.parse(python.stdout);
assert.deepEqual(result.scores,runs.map(run=>run.expected),'All independently replayed scores agree');
for(let i=0;i<fixtures.length;i++)assert.deepEqual(result.states[i],JSON.parse(JSON.stringify(fixtures[i].expected)),`Clear fixture ${i}`);
console.log('Pit Stack server/client parity passed: 120 seeded full games, moves/rotations/drops, 1–4 line clears at low/high speed, board/next-piece/scoring agreement.');
