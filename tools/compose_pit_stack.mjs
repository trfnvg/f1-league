// Original composition: "Grid Lights", 32 bars, A minor, 128 BPM, 60-second loop.
// Deterministic offline chiptune renderer; no samples, licensed music or runtime DSP.
import fs from 'node:fs/promises';
import path from 'node:path';

const output=process.argv[2];
if(!output) throw new Error('Usage: node tools/compose_pit_stack.mjs /path/to/grid-lights.wav');
const sampleRate=44100,bpm=128,step=60/bpm/4,duration=32*16*step;
const length=Math.round(sampleRate*duration),left=new Float32Array(length),right=new Float32Array(length);
const frequency=midi=>440*2**((midi-69)/12);
let seed=731;
const noise=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/2147483648-1;};
function voice(midi,time,seconds,volume,kind='lead',pan=0) {
  const start=Math.round(time*sampleRate),count=Math.ceil(seconds*sampleRate),hz=frequency(midi);
  const lg=Math.sqrt((1-pan)/2),rg=Math.sqrt((1+pan)/2);
  for(let i=0;i<count;i++) {
    const t=i/sampleRate,phase=2*Math.PI*hz*t;
    const attack=Math.min(1,t/.004),release=Math.min(1,(seconds-t)/.025);
    let wave;
    if(kind==='bass') wave=Math.sin(phase)+.18*Math.sin(3*phase);
    else if(kind==='arp') wave=Math.sin(phase)+.22*Math.sin(2*phase)+.08*Math.sin(4*phase);
    else wave=(Math.sin(phase)+Math.sin(3*phase)/3+Math.sin(5*phase)/5+Math.sin(7*phase)/7)*.73;
    const envelope=attack*Math.max(0,release)*(kind==='arp'?Math.exp(-t*17):.75+.25*Math.exp(-t*12));
    const value=wave*envelope*volume,index=(start+i)%length;
    left[index]+=value*lg;right[index]+=value*rg;
  }
}
function drum(time,kind,volume) {
  const seconds=kind==='kick'?.18:kind==='snare'?.14:.045,start=Math.round(time*sampleRate);
  for(let i=0;i<seconds*sampleRate;i++) {
    const t=i/sampleRate;
    let value;
    if(kind==='kick') value=Math.sin(2*Math.PI*(46*t+40*.018*(1-Math.exp(-t/.018))))*Math.exp(-t*27);
    else value=(noise()-(i%2?-.2:.2))*Math.exp(-t*(kind==='snare'?38:100));
    const envelope=Math.min(1,t/.001)*Math.min(1,(seconds-t)/.008);
    const index=(start+i)%length;left[index]+=value*volume*envelope;right[index]+=value*volume*envelope;
  }
}
const chords=[[45,48,52],[41,45,48],[48,52,55],[43,47,50],[45,48,52],[41,45,48],[42,45,48],[40,44,47]];
const hooks=[
 [81,0,76,0,79,0,76,74,72,0,74,0,76,0,72,0],
 [77,0,76,0,72,0,69,0,72,74,76,0,77,0,76,0],
 [76,0,79,0,84,0,83,81,79,0,76,0,74,0,72,0],
 [74,0,79,0,78,79,83,0,81,0,79,0,74,0,71,0],
 [81,0,79,76,81,0,84,0,83,81,79,0,76,0,72,0],
 [77,0,81,0,79,77,76,0,72,0,74,0,77,0,76,0],
 [74,0,77,0,81,0,79,77,76,0,74,0,72,0,69,0],
 [76,0,80,0,83,0,80,76,74,0,71,0,68,0,71,0],
];
for(let bar=0;bar<32;bar++) {
  const chord=chords[bar%8],section=Math.floor(bar/8),hook=hooks[bar%8];
  for(let tick=0;tick<16;tick++) {
    const time=(bar*16+tick)*step;
    const note=hook[tick];
    if(note) {
      // B section opens up into a lower, spacious answering phrase.
      const midi=section===2?note-12:note;
      const next=hook[tick+1],seconds=next?step*.82:step*1.7;
      if(section!==2 || tick%4===0 || tick===10 || tick===14)
        voice(midi,time,seconds,section===2?.075:.065,'lead',-.1);
      if(section===3 && tick%4===0)voice(midi-12,time,step*1.5,.018,'lead',.35);
    }
    if(tick%2===0)voice(chord[(tick/2)%3]+12,time,step*.8,.022,'arp',tick%4===0?-.5:.5);
    if(tick%4===0 || tick===10)voice(chord[0]+(tick===8?12:0),time,step*1.5,.1,'bass');
    if(tick===0 || tick===8 || (section!==2 && tick===11))drum(time,'kick',.18);
    if(tick===4 || tick===12)drum(time,'snare',.043);
    if(tick%2===0)drum(time,'hat',tick%4===0?.012:.018);
    if(bar%8===7 && tick>=14)drum(time,'snare',.025);
  }
}
// Small stereo echo wraps over the bar boundary, preserving the musical loop.
for(const channel of [left,right]) {
  const dry=channel.slice(),delay=Math.round(step*3*sampleRate);
  for(let i=0;i<length;i++)channel[i]+=.12*dry[(i-delay+length)%length];
}
let peak=0,squares=0;
for(let i=0;i<length;i++)peak=Math.max(peak,Math.abs(left[i]),Math.abs(right[i]));
const gain=.82/peak;
const wav=Buffer.alloc(44+length*4);
wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);
wav.writeUInt16LE(1,20);wav.writeUInt16LE(2,22);wav.writeUInt32LE(sampleRate,24);wav.writeUInt32LE(sampleRate*4,28);
wav.writeUInt16LE(4,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(length*4,40);
for(let i=0;i<length;i++) {
  // Microfade only at the splice prevents a click without an audible beat gap.
  const edge=Math.min(1,i/96,(length-1-i)/96);
  const l=left[i]*gain*edge,r=right[i]*gain*edge;squares+=(l*l+r*r)/2;
  wav.writeInt16LE(Math.round(l*32767),44+i*4);wav.writeInt16LE(Math.round(r*32767),46+i*4);
}
await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,wav);
console.log(JSON.stringify({output,title:'Grid Lights',bpm,bars:32,duration,sampleRate,channels:2,
  peak:.82,rms:Math.sqrt(squares/length),bytes:wav.length}));
