(() => {
  // Pure planning: no DOM, timers, assets, score writes or changes to story physics.
  const worlds = Object.freeze({
    desert: {name:"Пыльный паддок",stage:null}, canyon:{name:"Каньон",stage:null},
    sky:{name:"Небесная трасса",stage:"sky"}, space:{name:"Космос",stage:"space"},
    garage:{name:"Забытый паддок",stage:"garage"}, winter:{name:"Антарктида",stage:"winter"},
    summit:{name:"Высокогорный паддок",stage:"summit"},
  });
  const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
  class Director {
    constructor(score,random=Math.random){
      this.random=random;this.world="desert";this.section=1;this.index=0;
      this.lastPattern=-1;this.pattern=0;this.direction=1;
      this.schedule(score);
    }
    difficulty(score){return clamp((score-18000)/7000,0,1);}
    schedule(score){
      this.nextAt=score+1500;
      const choices=Object.keys(worlds).filter(w=>w!==this.world);
      this.pendingWorld=choices[Math.floor(this.random()*choices.length)];
    }
    advance(score){
      const previous=this.world;this.world=this.pendingWorld;this.section++;
      // Keep the grid tied to the original run threshold, not overshoot from bonuses.
      this.schedule(this.nextAt);return previous;
    }
    // Descending intersection of y(t)=720t-620t². Discount acceleration/reversal
    // time and use the unboosted horizontal speed; springs/rockets are never required.
    reach(gap,width){
      const discriminant=720*720-2*1240*gap;
      if(discriminant<0)return 0;
      const t=(720+Math.sqrt(discriminant))/1240;
      return Math.min(width*.32,Math.min(440,width*.62)*Math.max(0,t-.24)*.72);
    }
    plan(previous,width,score){
      const d=this.difficulty(score),gap=122+this.random()*(26+d*12)+d*18;
      if(this.index%7===0){
        const choices=[0,1,2,3].filter(p=>p!==this.lastPattern);
        this.pattern=choices[Math.floor(this.random()*choices.length)];this.lastPattern=this.pattern;
      }
      this.index++;
      if(this.pattern===0||this.pattern===2)this.direction*=-1;
      if(previous.x>width*.72)this.direction=-1;
      if(previous.x<width*.28)this.direction=1;
      const roll=this.random();
      // Every third foothold is permanent. The others can require timing or
      // commitment, but the complete moving envelopes stay inside the jump arc.
      const kind=this.index%3===0?"normal":roll<.40+d*.15?"moving":roll<.65+d*.15?"break":"normal";
      const range=kind==="moving"?16+d*2:0,previousRange=previous.range||0;
      const reach=this.reach(gap,width),budget=Math.max(0,reach-range-previousRange);
      const step=budget*(this.pattern===2?.92:this.pattern===3?.52:.80);
      const x=clamp(previous.x+this.direction*step,width*.18,width*.82);
      const primary={x,y:previous.y+gap,kind,range,world:this.world,primary:true};
      let extra=null;
      if(this.random()<.10+d*.14){
        const roll=this.random(),kind=roll<.55?"moving":roll<.95?"break":"spring";
        const extraGap=gap*.5,offset=Math.min(64,reach*.4);
        const side=x>width/2?-1:1;
        const extraX=clamp(x+side*offset,width*.15,width*.85);
        // Both incoming and outgoing arcs tolerate the complete moving range.
        if(Math.abs(extraX-previous.x)+12+previousRange<=this.reach(extraGap,width)
          &&Math.abs(extraX-x)+12+range<=this.reach(extraGap,width))
          extra={x:extraX,y:previous.y+extraGap,kind,range:12,world:this.world,primary:false};
      }
      return {primary,extra,gap,difficulty:d};
    }
  }
  window.FastlapEndless=Object.freeze({Director,worlds});
})();
