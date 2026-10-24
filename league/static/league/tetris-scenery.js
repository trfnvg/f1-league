/* Lightweight vector panoramas: crisp at any DPR, no per-frame scenery work. */
(function () {
  'use strict';
  const venues = [
    {name:'Лазурный Гран-при',tag:'RIVIERA',sky:'#173e58',horizon:'#ae9383',accent:'#72d9df',kind:'coast'},
    {name:'Пески и скорость',tag:'DESERT',sky:'#352e50',horizon:'#b87b58',accent:'#edb17c',kind:'desert'},
    {name:'Ночная гонка',tag:'NIGHT RACE',sky:'#111a38',horizon:'#3c3663',accent:'#b7a0f1',kind:'city'},
    {name:'Альпийский автодром',tag:'ALPINE',sky:'#173746',horizon:'#849a9b',accent:'#94cbb6',kind:'mountain'},
  ];
  function panorama(v) {
    let landscape='';
    if(v.kind==='coast' || v.kind==='city') {
      for(let i=0;i<26;i++) {
        const x=i*56-20, h=50+(i*47%155), y=490-h;
        landscape+=`<rect x="${x}" y="${y}" width="44" height="${h}" fill="${i%2?'#203347':'#2b4055'}"/>`;
        for(let k=0;k<4;k++) landscape+=`<path d="M${x+9} ${y+16+k*24}h25" stroke="${v.accent}" opacity="${v.kind==='city'?'.5':'.2'}" stroke-width="3"/>`;
      }
      if(v.kind==='coast') landscape+='<path d="M0 485H1400V650H0Z" fill="#25536a"/><path d="M0 520H1400M0 553H1400M0 602H1400" stroke="#85b2bb" opacity=".2"/><path d="M80 580h120l-25 15h-70zM1100 555h150l-30 18h-90z" fill="#c2c8c8"/><path d="M138 580v-70l-38 65h38M1160 555v-85l-42 80h42" fill="#b7c4c9"/>';
    } else if(v.kind==='desert') {
      landscape='<path d="M0 410Q220 290 440 440T880 400T1400 400V650H0" fill="#73565b"/><path d="M0 520Q280 370 570 510T1100 460T1400 500V700H0" fill="#99705f"/><path d="M80 450V275h80v175M1110 440V240h58v200" fill="#343440"/><path d="M65 275h110l-55-60zM1098 240h82l-41-45z" fill="#484052"/><path d="M95 300h50m-50 18h50m-50 18h50M1120 267h39m-39 18h39" stroke="#d5ab8d" opacity=".5"/>';
    } else {
      landscape='<path d="M0 500L190 200l180 280L590 150l210 320 190-260 240 240 170-240v440H0" fill="#445969"/><path d="m190 200-66 105 66-24 55 20zm400-50-78 118 78-35 60 24zm400 60-65 90 65-23 57 18z" fill="#becad0"/><path d="M0 570L240 360l210 200 280-240 230 240 230-180 210 120v200H0" fill="#29474a"/>';
      for(let i=0;i<30;i++) { const x=i*50,y=500+i*19%70; landscape+=`<path d="M${x} ${y-75}l-28 85h56z" fill="#203c3e"/>`; }
    }
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1400 900" preserveAspectRatio="xMidYMid slice"><defs><linearGradient id="sky-${v.kind}" x2="0" y2="1"><stop stop-color="${v.sky}"/><stop offset="1" stop-color="${v.horizon}"/></linearGradient></defs><path fill="url(#sky-${v.kind})" d="M0 0h1400v900H0z"/><circle cx="1120" cy="155" r="48" fill="${v.accent}" opacity=".3"/><path d="M50 195h280M960 270h350M80 120h190" stroke="#d6dce3" stroke-width="2" opacity=".15"/>${landscape}<path d="M0 655Q700 520 1400 640V900H0" fill="#171f2a"/><path d="M-60 780Q600 570 1460 760" fill="none" stroke="#89929c" stroke-width="5"/><path d="M-60 790Q600 580 1460 770" fill="none" stroke="#d7cbc4" stroke-width="14"/><path d="M-60 790Q600 580 1460 770" fill="none" stroke="#b7504a" stroke-width="14" stroke-dasharray="42 42"/><path d="M0 860Q650 650 1400 850" fill="none" stroke="#a8b5bf" stroke-width="3" stroke-dasharray="60 55" opacity=".35"/><g fill="#273342" stroke="#8194a3" stroke-width="2"><path d="M25 625V525h265v100zM1110 625V525h265v100z"/><path d="M12 525l25-30h265v30zM1098 525l25-30h265v30z"/></g><path d="M42 548h230m-230 18h230m-230 18h230M1128 548h230m-230 18h230m-230 18h230" stroke="${v.accent}" opacity=".45" stroke-width="4"/><g transform="translate(160 740)"><path d="M-30 10h95l-14-18H10z" fill="${v.accent}"/><path d="M3-8h28l12 18H-8z" fill="#1b2834"/><path d="M-34 9h105M-17-10h44" stroke="#111821" stroke-width="8"/><path d="M-20 6v14m67-14v14" stroke="#080e18" stroke-width="13"/></g></svg>`;
  }
  window.PitStackScenery = class {
    constructor(host, label, random=Math.random) {
      this.host=host;this.label=label;this.random=random;
      this.layers=[...host.children]; this.slot=0;this.current=-1;this.stage=-1;this.bag=[];
      this.reset();
    }
    reset() { this.stage=-1;this.bag=[];this.update(0); }
    update(lines) {
      const stage=Math.floor(lines/10);
      if(stage===this.stage) return;
      this.stage=stage;
      if(!this.bag.length) {
        this.bag=venues.map((_,i)=>i);
        for(let i=this.bag.length-1;i>0;i--) {const j=Math.floor(this.random()*(i+1));[this.bag[i],this.bag[j]]=[this.bag[j],this.bag[i]];}
        if(this.bag.at(-1)===this.current) [this.bag[0],this.bag[this.bag.length-1]]=[this.bag.at(-1),this.bag[0]];
      }
      this.current=this.bag.pop(); const v=venues[this.current];this.slot=1-this.slot;
      // Only trusted, local constants become markup; never user input.
      this.layers[this.slot].innerHTML=panorama(v);
      this.layers.forEach((layer,i)=>layer.classList.toggle('is-visible',i===this.slot));
      this.label.textContent=v.tag;this.label.title=v.name;
      this.host.parentElement.style.setProperty('--venue-accent',v.accent);
    }
  };
})();
