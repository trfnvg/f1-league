/* Original GPT pixel-art venues; bounded, decoded image crossfades. */
(function () {
  'use strict';
  const venues = [
    {id:'monaco',name:'Гран-при Монако',tag:'МОНАКО',accent:'#e6b47e'},
    {id:'las-vegas',name:'Гран-при Лас-Вегаса',tag:'ЛАС-ВЕГАС',accent:'#dc9cdd'},
    {id:'austin',name:'Гран-при США · Остин',tag:'ОСТИН',accent:'#e8b481'},
    {id:'shanghai',name:'Гран-при Китая · Шанхай',tag:'ШАНХАЙ',accent:'#accbd7'},
    {id:'suzuka',name:'Гран-при Японии · Сузука',tag:'СУЗУКА',accent:'#e0b4d4'},
    {id:'monza',name:'Гран-при Италии · Монца',tag:'МОНЦА',accent:'#c8cf99'},
    {id:'silverstone',name:'Гран-при Великобритании',tag:'СИЛЬВЕРСТОУН',accent:'#b3ccc5'},
    {id:'singapore',name:'Гран-при Сингапура',tag:'СИНГАПУР',accent:'#b7a6e5'},
    {id:'spa',name:'Гран-при Бельгии · Спа',tag:'СПА',accent:'#b6c99f'},
    {id:'abu-dhabi',name:'Гран-при Абу-Даби',tag:'АБУ-ДАБИ',accent:'#d4ade8'},
  ];
  window.PitStackScenery = class {
    constructor(host, label, random=Math.random) {
      this.host=host;this.label=label;this.random=random;
      this.layers=[...host.children];this.slot=0;this.current=-1;
      this.stage=-1;this.bag=[];this.generation=0;this.prefetched=null;
      // Django resolves each asset individually, including manifest/CDN hashes.
      this.sourceFor=id=>host.getAttribute('data-art-'+id);
      this.ready=this.reset();
    }
    shuffle() {
      this.bag=venues.map((_,i)=>i);
      for(let i=this.bag.length-1;i>0;i--) {
        const j=Math.min(i,Math.floor(this.random()*(i+1)));
        [this.bag[i],this.bag[j]]=[this.bag[j],this.bag[i]];
      }
      if(this.bag.at(-1)===this.current) {
        [this.bag[0],this.bag[this.bag.length-1]]=[this.bag.at(-1),this.bag[0]];
      }
    }
    load(index) {
      if(this.prefetched?.index===index) return this.prefetched.ready;
      const image=new Image();image.alt='';image.decoding='async';
      image.draggable=false;
      image.src=this.sourceFor(venues[index].id);
      return image.decode().then(()=>image).catch(()=>null);
    }
    prefetch() {
      if(!this.bag.length) this.shuffle();
      const index=this.bag.at(-1);
      if(this.prefetched?.index===index) return;
      const ready=this.load(index);
      this.prefetched={index,ready};
    }
    reset() {
      this.generation++;this.bag=[];
      if(this.current<0) {
        this.stage=-1;
        return this.update(0);
      }
      // Starting/restarting a run keeps the artwork already on the title screen.
      // Cancel pending old-run transitions and count this venue as stop one.
      this.stage=0;this.shuffle();
      this.bag.splice(this.bag.indexOf(this.current),1);
      this.prefetch();
      return Promise.resolve(true);
    }
    async update(lines) {
      const stage=Math.floor(lines/10);
      if(stage===this.stage) return;
      this.stage=stage;
      if(!this.bag.length) this.shuffle();
      // First page load matches preloaded/SSR artwork; subsequent tours shuffle.
      const index=this.current<0 && stage===0 ? 0 : this.bag.at(-1);
      this.bag.splice(this.bag.indexOf(index),1);
      const generation=++this.generation;
      const image=await this.load(index);
      if(!image || generation!==this.generation) return false;
      const venue=venues[index];
      this.current=index;this.slot=1-this.slot;
      this.layers[this.slot].replaceChildren(image);
      this.layers.forEach((layer,i)=>layer.classList.toggle('is-visible',i===this.slot));
      this.label.textContent=venue.tag;this.label.title=venue.name;
      this.host.parentElement.style.setProperty('--venue-accent',venue.accent);
      this.prefetch();
      return true;
    }
  };
})();
