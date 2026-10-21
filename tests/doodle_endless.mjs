import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const source=await fs.readFile(new URL('../league/static/league/doodle-endless.js',import.meta.url),'utf8');
const scope={};new Function('window',source)(scope);
const {Director,worlds}=scope.FastlapEndless;
function seeded(seed){return ()=>{seed=(1664525*seed+1013904223)>>>0;return seed/4294967296;};}
let arcs=0,options=0,moving=0,breaking=0;
for(const width of [390,600])for(let seed=1;seed<=24;seed++){
  const director=new Director(13800,seeded(seed));
  let previous={x:width/2,y:0},early=0,late=0;
  for(let i=0;i<15000;i++){
    const score=13800+previous.y/11,plan=director.plan(previous,width,score);
    const t=(720+Math.sqrt(720**2-2*1240*plan.gap))/1240;
    const speed=Math.min(440,width*.62)*1.2;
    const reversalReach=speed*(t-.2*(1-Math.exp(-10*t)));
    assert.ok(plan.gap>0&&plan.gap<720**2/(2*1240));
    assert.ok(Math.abs(plan.primary.x-previous.x)<reversalReach*.85,'Anchor reachable even after reversing full horizontal velocity');
    assert.ok(Math.abs(plan.primary.x-previous.x)+(previous.range||0)+plan.primary.range<=director.reach(plan.gap,width),
      'Both moving platforms remain reachable across their complete motion envelopes');
    if(i%3===2)assert.equal(plan.primary.kind,'normal','A permanent rest foothold every third jump');
    if(plan.primary.kind==='moving')moving++;
    if(plan.primary.kind==='break')breaking++;
    if(score<18000)assert.ok(plan.gap>=122&&plan.gap<=148);
    if(score>=25000)assert.ok(plan.gap>=140&&plan.gap<=178);
    if(plan.extra){
      options++;if(score<18000)early++;if(score>25000)late++;
      assert.ok(Math.abs(plan.extra.x-previous.x)+12+(previous.range||0)<=director.reach(plan.gap*.5,width));
      assert.ok(Math.abs(plan.extra.x-plan.primary.x)+12+plan.primary.range<=director.reach(plan.gap*.5,width));
    }
    assert.ok(Number.isFinite(plan.primary.y));
    previous=plan.primary;arcs++;
  }
  assert.ok(previous.y/11>100000);
  assert.equal(director.difficulty(13000),0);assert.equal(director.difficulty(18000),0);
  assert.equal(director.difficulty(25000),1);assert.equal(director.difficulty(1e9),1);
  const seen=new Set([director.world]);let score=13800;
  for(let section=0;section<100;section++){
    assert.equal(director.nextAt-score,1500);
    const before=director.world;score=director.nextAt;director.advance(score);
    assert.notEqual(director.world,before);seen.add(director.world);
  }
  assert.equal(seen.size,Object.keys(worlds).length);
  const threshold=director.nextAt;director.advance(threshold+50);
  assert.equal(director.nextAt,threshold+1500,'Bonus overshoot does not shift future thresholds');
}
assert.ok(moving>arcs*.25&&breaking>arcs*.1,'Hard routes actually include moving and single-use footholds');
console.log(`Endless planner: ${arcs} reachable primary arcs (${moving} moving, ${breaking} breaking), ${options} two-way optional arcs; 48 seeded mobile/desktop runs beyond 100000 points; all seven worlds, bounded difficulty and exact 1500-point intervals passed`);
