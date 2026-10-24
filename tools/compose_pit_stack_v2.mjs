// "Parc Ferme" — original mellow retro/orchestral racing score, D minor.
// 80 bars / 200 seconds at 96 BPM. No external music, samples or quoted melodies.
import fs from 'node:fs/promises';
import path from 'node:path';
const output=process.argv[2];
if(!output)throw Error('Usage: node tools/compose_pit_stack_v2.mjs /path/to/parc-ferme.wav');
const sr=44100,bpm=96,step=60/bpm/4,bars=80,duration=bars*16*step,n=Math.round(sr*duration);
const left=new Float32Array(n),right=new Float32Array(n);
let seed=829;const noise=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/2147483648-1;};
function note(midi,time,length,volume,kind='pad',pan=0) {
  const start=Math.round(time*sr),count=Math.ceil(length*sr),hz=440*2**((midi-69)/12);
  const lg=Math.sqrt((1-pan)/2),rg=Math.sqrt((1+pan)/2);
  for(let i=0;i<count;i++) {
    const t=i/sr,p=2*Math.PI*hz*t;
    const attack=kind==='pad'?.24:kind==='brass'?.045:.015;
    const release=kind==='pad'?.35:kind==='brass'?.18:.07;
    const env=Math.min(1,t/attack)*Math.max(0,Math.min(1,(length-t)/release));
    let wave;
    if(kind==='pad')wave=.82*Math.sin(p+.008*Math.sin(2*Math.PI*.3*t))+.07*Math.sin(2*p)+.035*Math.sin(3*p);
    else if(kind==='brass')wave=.8*Math.sin(p)+.14*Math.sin(2*p)+.06*Math.sin(3*p);
    else if(kind==='bass')wave=Math.sin(p)+.06*Math.sin(3*p);
    else wave=(Math.sin(p)+.12*Math.sin(3*p))*Math.exp(-t*6);
    const value=wave*volume*env,index=(start+i)%n;
    left[index]+=value*lg;right[index]+=value*rg;
  }
}
function drum(time,kind,volume) {
  const start=Math.round(time*sr),length=kind==='kick'?.2:.1;
  let low=0;
  for(let i=0;i<length*sr;i++) {
    const t=i/sr;low+=(noise()-low)*.12;
    const wave=kind==='kick'?Math.sin(2*Math.PI*(44*t+.5*(1-Math.exp(-t/.02))))*Math.exp(-t*26):low*Math.exp(-t*35);
    const v=wave*volume*Math.min(1,t/.003)*Math.min(1,(length-t)/.015),index=(start+i)%n;
    left[index]+=v;right[index]+=v;
  }
}
const chords=[[50,53,57],[46,50,53],[53,57,60],[48,52,55],[43,46,50],[46,50,53],[53,57,60],[45,49,52]];
// Broad rising fifths and dotted answering phrases evoke a racing broadcast;
// the tune itself is newly composed rather than the official F1 theme.
const phrases=[
 [[0,62,3],[4,69,3],[10,65,5]], [[2,65,4],[8,62,6]],
 [[0,65,4],[6,72,4],[12,69,3]], [[0,67,5],[8,64,6]],
 [[0,62,4],[6,65,3],[11,67,4]], [[2,65,4],[9,62,5]],
 [[0,69,5],[8,65,6]], [[0,64,4],[6,61,3],[12,57,3]],
];
for(let bar=0;bar<bars;bar++) {
  const chord=chords[bar%8],time=bar*16*step;
  const intro=bar<8,outro=bar>=72,breathing=(bar>=24&&bar<32)||(bar>=48&&bar<56);
  const answering=bar>=32&&bar<48;
  const density=intro||outro?.6:breathing?.7:1;
  for(let i=0;i<3;i++)note(chord[i],time,16*step+.18,.052*density,'pad',(i-1)*.4);
  note(chord[0]-12,time,7*step,.06*density,'bass');
  if(!breathing && !intro && !outro)note(chord[0]-12,time+9*step,5*step,.045,'bass');
  const ticks=breathing||outro?[4]:intro?[2,10]:[2,8,12];
  for(const [i,tick] of ticks.entries())note(chord[(i+bar)%3]+12,time+tick*step,step*2,.018*density,'bell',i%2?.4:-.4);
  // Half the bars intentionally leave room around the melody.
  if(!intro && !outro && !breathing && (bar%2===0 || answering)) {
    for(const [tick,midi,held] of phrases[bar%8])
      note(midi+(answering?-12:0),time+tick*step,held*step,.047,'brass',answering?.15:-.12);
  }
  if(!intro && !outro && !breathing) {
    drum(time,'kick',.075);if(bar%2===0)drum(time+10*step,'kick',.045);
    if(bar%2===1)drum(time+12*step,'snare',.018);
  }
  if(bar%8===6)note(chord[2]+12,time+12*step,3*step,.012,'bell',.25);
}
for(const channel of [left,right]) {
  const dry=channel.slice(),delay=Math.round(step*3*sr),longDelay=Math.round(step*7*sr);
  for(let i=0;i<n;i++)channel[i]+=.16*dry[(i-delay+n)%n]+.055*dry[(i-longDelay+n)%n];
}
let peak=0,squares=0;
for(let i=0;i<n;i++){peak=Math.max(peak,Math.abs(left[i]),Math.abs(right[i]));squares+=(left[i]**2+right[i]**2)/2;}
const gain=Math.min(.62/peak,.075/Math.sqrt(squares/n)),wav=Buffer.alloc(44+n*4);
wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);
wav.writeUInt16LE(1,20);wav.writeUInt16LE(2,22);wav.writeUInt32LE(sr,24);wav.writeUInt32LE(sr*4,28);
wav.writeUInt16LE(4,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(n*4,40);
for(let i=0;i<n;i++) {
  const edge=Math.min(1,i/220,(n-1-i)/220);
  wav.writeInt16LE(Math.round(left[i]*gain*edge*32767),44+i*4);
  wav.writeInt16LE(Math.round(right[i]*gain*edge*32767),46+i*4);
}
await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,wav);
console.log(JSON.stringify({output,title:'Parc Ferme',bpm,bars,duration,peak:peak*gain,rms:Math.sqrt(squares/n)*gain,bytes:wav.length}));
