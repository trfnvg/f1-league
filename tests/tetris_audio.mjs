import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
const source=await fs.readFile(new URL('../league/static/league/tetris-audio.js',import.meta.url),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function fixture({saved=null,blockedStorage=false}={}) {
  let stored=saved,contexts=0;
  const requests=[];
  const media={paused:true,currentTime:9,playbackRate:1,
    play(){this.paused=false;return new Promise((resolve,reject)=>requests.push({resolve,reject}));},
    pause(){this.paused=true;}};
  const element=()=>({value:'28',events:{},attributes:{},focus(){},
    addEventListener(type,fn){this.events[type]=fn;},setAttribute(key,value){this.attributes[key]=value;},
    classList:{toggle(){}},click(){this.events.click();}});
  const button=element(),volume=element();
  class AudioContext {
    constructor(){contexts++;this.state='suspended';this.currentTime=0;this.destination={};}
    createGain(){return {gain:{value:0,setTargetAtTime(value){this.value=value;}},connect(){}};}
    createMediaElementSource(){return {connect(){}};}
    resume(){this.state='running';return Promise.resolve();}
    suspend(){this.state='suspended';return Promise.resolve();}
  }
  const scope={window:{AudioContext},localStorage:{
    getItem(){if(blockedStorage)throw Error('storage disabled');return stored;},
    setItem(_key,value){if(blockedStorage)throw Error('storage disabled');stored=value;},
  }};
  vm.runInNewContext(source,scope);
  return {music:new scope.window.PitStackAudio(media,button,volume),media,button,volume,requests,
    get contexts(){return contexts;},get saved(){return stored;}};
}
{
  const f=fixture();assert.equal(f.contexts,0);assert.equal(f.requests.length,0,'No autoplay/context creation on page load');
  f.music.setPlaying(true,true);assert.equal(f.media.currentTime,0);assert.equal(f.contexts,1);
  f.requests.shift().resolve();await tick();
  f.button.click();assert.equal(f.media.paused,true);assert.equal(f.music.active,true);
  assert.equal(JSON.parse(f.saved).enabled,false);
  f.volume.value='42';f.volume.events.input();f.requests.shift().resolve();await tick();
  assert.equal(f.music.enabled,true);assert.equal(f.music.volume,.42);assert.equal(f.contexts,1);
  f.music.setPace(999);assert.equal(f.media.playbackRate,1.048);assert.equal(f.media.preservesPitch,true);
  f.music.setPlaying(false);assert.equal(f.media.paused,true);assert.equal(f.music.context.state,'suspended');
  const restored=fixture({saved:f.saved});assert.equal(restored.music.volume,.42);
  restored.music.setPlaying(true);restored.music.setPlaying(false);
  restored.requests.shift().resolve();await tick();assert.equal(restored.media.paused,true,'Late play completion cannot resume paused gameplay');
}
{
  const f=fixture({saved:JSON.stringify({enabled:false,volume:.18})});
  f.music.setPlaying(true);assert.equal(f.contexts,0);assert.equal(f.requests.length,0);
  f.button.click();assert.equal(f.contexts,1);f.media.paused=true;
  f.requests.shift().reject(Error('Autoplay blocked'));await tick();assert.equal(f.music.blocked,true);
  f.button.click();assert.equal(f.music.enabled,true,'Blocked sound button retries instead of muting');
  f.requests.shift().resolve();await tick();assert.equal(f.music.blocked,false);
}
{
  for(const options of [{saved:'invalid json'},{blockedStorage:true}]) {
    const f=fixture(options);f.music.setPlaying(true);f.button.click();
    f.requests.shift().reject(Error('aborted'));await tick();
    assert.equal(f.media.paused,true);assert.equal(f.music.blocked,false,'Stale rejection ignored');
  }
}
console.log('Pit Stack audio passed: no autoplay, preferences, gain reuse, mute/volume, pace cap, pause races, blocked playback retries and unavailable storage.');
