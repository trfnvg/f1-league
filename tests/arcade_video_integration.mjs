import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const source=await fs.readFile(new URL('../league/static/league/doodle-jump.js',import.meta.url),'utf8');
const functions=source.slice(source.indexOf('  function registerAttempt()'),source.indexOf('  function finishIntro()'));
const calls=[],starts=[],clips=[];
const postJSON=(url,data)=>{
  calls.push({url,data});
  if(url==='start')return new Promise(resolve=>starts.push(resolve));
  return Promise.resolve({records:[]});
};
const recorder={begin(){const clip={uploaded:[],stopped:0,discarded:0,stop(){this.stopped++;},upload(id){this.uploaded.push(id);},discard(){this.discarded++;}};clips.push(clip);return clip;}};
const state=new Function('postJSON','videoRecorder',`
  const canvas={dataset:{startUrl:'start',finishUrl:'finish'}},csrfToken='csrf';
  let adminSandbox=false,adminBossTestMode=false,attemptSequence=0,attemptId=null;
  let videoRun=null,videoSession=null,finishedVideo=null,finalScore=0,pendingFinish=false,scoreSubmitted=false;
  function applyLeaderboard(){}
  ${functions}
  return {start:registerAttempt,finish(score){
    finalScore=score;videoSession.score=score;finishedVideo=videoRun;finishedVideo.stop();videoRun=null;submitScore();
  },reset(){attemptSequence++;videoSession=null;attemptId=null;pendingFinish=false;scoreSubmitted=false;},id:()=>attemptId};
`)(postJSON,recorder);
const flush=()=>new Promise(resolve=>setTimeout(resolve,0));
state.start();state.finish(111);state.reset();state.start();
starts[0]({attempt_id:10});await flush();
assert.deepEqual(calls.find(call=>call.url==='finish').data,{attempt_id:10,score:111});
assert.deepEqual(clips[0].uploaded,[10]);
assert.equal(state.id(),null,'A late start response cannot overwrite the next attempt');
starts[1]({attempt_id:11});await flush();state.finish(222);await flush();
assert.deepEqual(calls.filter(call=>call.url==='finish')[1].data,{attempt_id:11,score:222});
assert.deepEqual(clips[1].uploaded,[11]);
assert.equal(clips[0].stopped,1);assert.equal(clips[1].stopped,1);
console.log('Cowboy GP video integration: delayed start, fast restart and finish responses keep each complete video bound to its own attempt.');
