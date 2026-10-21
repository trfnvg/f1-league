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
      this.nextAt=score+1500+Math.floor(this.random()*1001);
      const choices=Object.keys(worlds).filter(w=>w!==this.world);
      this.pendingWorld=choices[Math.floor(this.random()*choices.length)];
    }
    advance(score){
      const previous=this.world;this.world=this.pendingWorld;this.section++;
      this.schedule(score);return previous;
    }
    // Descending intersection of y(t)=720t-620t². Discount acceleration/reversal
    // time and use the unboosted horizontal speed; springs/rockets are never required.
    reach(gap,width){
      const discriminant=720*720-2*1240*gap;
      if(discriminant<0)return 0;
      const t=(720+Math.sqrt(discriminant))/1240;
      return Math.min(width*.30,Math.min(440,width*.62)*Math.max(0,t-.24)*.66);
    }
    plan(previous,width,score){
      const d=this.difficulty(score),gap=94+this.random()*(26+d*20)+d*12;
      if(this.index%7===0){
        const choices=[0,1,2,3].filter(p=>p!==this.lastPattern);
        this.pattern=choices[Math.floor(this.random()*choices.length)];this.lastPattern=this.pattern;
      }
      this.index++;
      if(this.pattern===0||this.pattern===2)this.direction*=-1;
      if(previous.x>width*.72)this.direction=-1;
      if(previous.x<width*.28)this.direction=1;
      const reach=this.reach(gap,width),step=reach*(this.pattern===2?.82:this.pattern===3?.38:.62);
      const x=clamp(previous.x+this.direction*step,width*.18,width*.82);
      const primary={x,y:previous.y+gap,kind:"normal",world:this.world,primary:true};
      let extra=null;
      if(this.random()<.16+d*.34){
        const roll=this.random(),kind=roll<.45?"moving":roll<.8?"break":"spring";
        const extraGap=gap*.5,offset=Math.min(64,reach*.4);
        const side=x>width/2?-1:1;
        const extraX=clamp(x+side*offset,width*.15,width*.85);
        // Both incoming and outgoing arcs tolerate the complete moving range.
        if(Math.abs(extraX-previous.x)+12<=this.reach(extraGap,width)
          &&Math.abs(extraX-x)+12<=this.reach(extraGap,width))
          extra={x:extraX,y:previous.y+extraGap,kind,world:this.world,primary:false};
      }
      return {primary,extra,gap,difficulty:d};
    }
  }
  window.FastlapEndless=Object.freeze({Director,worlds});
})();
