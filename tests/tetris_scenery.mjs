import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';

// Control image completion order: slow/failed downloads must never blank the
// current scene or let an obsolete request overwrite a newer venue.
const pending=[];
class Image {
  decode(){return new Promise((resolve,reject)=>pending.push({image:this,resolve,reject}));}
}
const scope={window:{},Image};
vm.runInNewContext(await fs.readFile(new URL('../league/static/league/tetris-scenery.js',import.meta.url),'utf8'),scope);
const Scenery=scope.window.PitStackScenery;
function fixture(){
  const children=[0,1].map(()=>({image:null,visible:false,replaceChildren(image){this.image=image;},
    classList:{toggle(_name,on){children.find(child=>child.classList===this).visible=on;}}}));
  const label={textContent:'old'},host={children,getAttribute(name){return '/art/'+name.slice(9)+'-retro-v1.webp';},parentElement:{style:{setProperty(){}}}};
  return {children,label,scenery:new Scenery(host,label,()=>.3)};
}
{
  const {children,label,scenery}=fixture();
  pending.shift().resolve();await scenery.ready;
  assert.equal(scenery.current,0);assert.equal(label.textContent,'МОНАКО');
  assert.equal(pending.length,1,'Only the next venue is prefetched');
  const old=children.find(layer=>layer.visible).image;
  const failed=scenery.update(10);pending.shift().reject(new Error('offline'));
  assert.equal(await failed,false);assert.equal(scenery.current,0);
  assert.equal(children.find(layer=>layer.visible).image,old,'Keep old pixels after download failure');
  const recovered=scenery.update(20);pending.shift().resolve();assert.equal(await recovered,true);
  assert.notEqual(scenery.current,0);assert.equal(children.filter(layer=>layer.visible).length,1);
  pending.shift().resolve();await Promise.resolve();
}
{
  const {children,scenery}=fixture();
  const old=pending.shift(),newer=scenery.update(10),latest=pending.shift();
  latest.resolve();assert.equal(await newer,true);const current=scenery.current;
  old.resolve();assert.equal(await scenery.ready,false);
  assert.equal(scenery.current,current,'Stale download cannot overwrite a newer stage');
  assert.equal(children.filter(layer=>layer.visible).length,1);
  pending.shift().resolve();await Promise.resolve();
  const reset=scenery.reset();
  // Reset may reuse the next prefetched image or start one additional load.
  for(const request of pending.splice(0))request.resolve();
  assert.equal(await reset,true);assert.equal(scenery.stage,0);
  assert.equal(children.length,2);
}
console.log('Pit Stack scenery passed: decode-before-show, single next prefetch, failure retention, recovery, stale completion protection and reset.');
