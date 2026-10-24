/* Finite pixel feedback, independent from gravity/scoring/input. World: 320x640. */
(function () {
  'use strict';
  window.PitStackFeedback=class {
    constructor(canvas,lights,palette,reduced=false) {
      this.canvas=canvas;this.ctx=canvas.getContext('2d');
      this.lights=lights;this.palette=palette;this.reduced=reduced;
      this.reset();
    }
    reset() {
      this.lockSerial=0;this.clearSerial=0;this.lock=null;this.chips=[];
      this.celebration=1000;this.dirty=true;
      this.lights.classList.remove('is-celebrating');
    }
    resize(width,height) {
      if(this.canvas.width!==width || this.canvas.height!==height) {
        this.canvas.width=width;this.canvas.height=height;this.dirty=true;
      }
    }
    observe(game) {
      this.lights.classList.toggle('is-paused',game.paused);
      if(game.lockSerial<this.lockSerial || game.clearSerial<this.clearSerial)this.reset();
      if(game.phase==='over' || game.phase==='ready') {
        if(this.active)this.reset();
        return;
      }
      if(game.lockSerial!==this.lockSerial) {
        this.lockSerial=game.lockSerial;
        if(game.lastLock && !this.reduced)this.lock={...game.lastLock,age:0};
        this.dirty=true;
      }
      if(game.clearSerial!==this.clearSerial) {
        this.clearSerial=game.clearSerial;
        if(!this.reduced) {
          const chips=[];
          for(const [i,cell] of game.lastClearCells.entries()) {
            for(let half=0;half<2;half++) {
              chips.push({x:cell.x*32+8+half*16,y:cell.y*32+16,
                vx:(cell.x-4.5)*11+((i*37+half*17)%41-20)*3,vy:-30-(i*19+half*31)%85,
                age:0,life:260+(i%4)*25,size:half?5:7,color:this.palette[cell.type]});
            }
          }
          this.chips=this.chips.concat(chips).slice(-120);
        }
        if(game.lastClear===4) {
          this.celebration=0;
          this.lights.classList.remove('is-celebrating');
          // One finite sequence per four-line clear, never a permanent animation.
          void this.lights.offsetWidth;
          this.lights.classList.add('is-celebrating');
        }
        this.dirty=true;
      }
    }
    get active() {return !!this.lock || this.chips.length>0 || this.celebration<1000;}
    step(ms,paused=false) {
      if(paused || !this.active)return;
      const dt=Math.min(50,Math.max(0,ms));
      const changedPixels=!!this.lock || this.chips.length>0;
      if(this.lock) {this.lock.age+=dt;if(this.lock.age>=150)this.lock=null;}
      for(const chip of this.chips)chip.age+=dt;
      this.chips=this.chips.filter(chip=>chip.age<chip.life);
      if(this.celebration<1000) {
        this.celebration+=dt;
        if(this.celebration>=1000)this.lights.classList.remove('is-celebrating');
      }
      if(changedPixels)this.dirty=true;
    }
    squash(x,y) {
      if(!this.lock || !this.lock.cells.some(cell=>cell.x===x && cell.y===y))return 1;
      return 1-.055*Math.sin(Math.PI*this.lock.age/150);
    }
    paint() {
      const {ctx,canvas}=this;
      ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,canvas.width,canvas.height);
      ctx.setTransform(canvas.width/320,0,0,canvas.height/640,0,0);
      if(this.lock) {
        const p=this.lock.age/150;
        ctx.globalAlpha=.36*(1-p);ctx.fillStyle=this.palette[this.lock.type];
        // A short grounding glint along each bottom edge, not a screen shake.
        for(const cell of this.lock.cells) {
          if(!this.lock.cells.some(other=>other.x===cell.x && other.y===cell.y+1))
            ctx.fillRect(cell.x*32+3,Math.min(638,(cell.y+1)*32-2),26,1.5);
        }
      }
      for(const chip of this.chips) {
        const t=chip.age/1000,p=chip.age/chip.life,size=chip.size*(1-.5*p);
        ctx.globalAlpha=.55*(1-p)*(1-p);ctx.fillStyle=chip.color;
        ctx.fillRect(chip.x+chip.vx*t-size/2,chip.y+chip.vy*t+120*t*t-size/2,size,size);
      }
      ctx.globalAlpha=1;this.dirty=false;
    }
  };
})();
