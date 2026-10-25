/* Finite pixel feedback, independent from gravity/scoring/input. World: 320x640. */
(function () {
  'use strict';
  window.PitStackFeedback=class {
    constructor(canvas,lights,palette,reduced=false) {
      this.canvas=canvas;this.ctx=canvas.getContext('2d');
      this.lights=lights;this.palette=palette;this.reduced=reduced;
      // Reuse a tiny light ramp: no per-frame blur, image filters or textures.
      this.sheen=this.ctx.createLinearGradient(0,0,96,0);
      this.sheen.addColorStop(0,'#d5faff00');
      this.sheen.addColorStop(.67,'#c5f4ff30');
      this.sheen.addColorStop(.84,'#f0fcffc0');
      this.sheen.addColorStop(1,'#d5faff00');
      this.reset();
    }
    reset() {
      this.lockSerial=0;this.clearSerial=0;this.lock=null;this.chips=[];
      this.charge=null;this.echoes=[];this.trail=null;
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
      // Follow the engine's existing 180 ms clear clock, including pause. No
      // extra waiting, independent timers or changes to next-piece spawning.
      if(game.phase==='clearing') {
        if(!this.charge || this.charge.serial!==game.lockSerial)
          this.charge={serial:game.lockSerial,rows:game.clearing.slice(),age:0};
        this.charge.age=game.clearClock;this.dirty=true;
      } else if(this.charge) {this.charge=null;this.dirty=true;}
      if(game.clearSerial!==this.clearSerial) {
        this.clearSerial=game.clearSerial;
        if(!this.reduced) {
          const chips=[];
          for(const [i,cell] of game.lastClearCells.entries()) {
            for(let half=0;half<2;half++) {
              chips.push({x:cell.x*32+8+half*16,y:cell.y*32+16,
                vx:(cell.x-4.5)*13+((i*37+half*17)%41-20)*3,vy:-35-(i*19+half*31)%90,
                age:0,life:320+(i%4)*35,size:half?6:9,color:this.palette[cell.type],
                spin:((i+half)%2?1:-1)*(2+i%3),angle:(i%4)*Math.PI/2});
            }
          }
          this.chips=this.chips.concat(chips).slice(-120);
          const rows=[...new Set(game.lastClearCells.map(cell=>cell.y))];
          this.echoes=this.echoes.concat(rows.map(row=>({row,age:0,gold:game.lastClear===4}))).slice(-8);
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
    trace(piece,landing) {
      if(this.reduced || !piece || !landing || landing.y-piece.y<2)return;
      const columns=[];
      piece.matrix.forEach((row,y)=>row.forEach((v,x)=>{
        if(!v)return;
        const column=columns.find(column=>column.x===piece.x+x);
        if(column)column.bottom=Math.max(column.bottom,landing.y+y+1);
        else columns.push({x:piece.x+x,top:Math.max(0,piece.y+y),bottom:landing.y+y+1});
      }));
      this.trail={columns,color:this.palette[piece.type],age:0};this.dirty=true;
    }
    get active() {return !!this.lock || !!this.charge || !!this.trail || this.echoes.length>0 || this.chips.length>0 || this.celebration<1000;}
    step(ms,paused=false) {
      if(paused || !this.active)return;
      const dt=Math.min(50,Math.max(0,ms));
      const changedPixels=!!this.lock || !!this.trail || this.echoes.length>0 || this.chips.length>0;
      if(this.lock) {this.lock.age+=dt;if(this.lock.age>=150)this.lock=null;}
      if(this.trail) {this.trail.age+=dt;if(this.trail.age>=150)this.trail=null;}
      for(const chip of this.chips)chip.age+=dt;
      this.chips=this.chips.filter(chip=>chip.age<chip.life);
      for(const echo of this.echoes)echo.age+=dt;
      this.echoes=this.echoes.filter(echo=>echo.age<300);
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
      if(this.trail) {
        const p=this.trail.age/150;
        ctx.fillStyle=this.trail.color;
        for(const column of this.trail.columns) {
          const bottom=column.bottom*32,top=Math.max(column.top*32,bottom-224);
          // Four short fading strips instead of a solid shaft over the board.
          for(let i=0;i<4;i++) {
            const height=(bottom-top)/4;
            ctx.globalAlpha=(.025+i*.016)*(1-p)*(1-p);
            ctx.fillRect(column.x*32+12+i,top+i*height,8-i*2,height);
          }
        }
      }
      if(this.charge) {
        const p=Math.min(1,this.charge.age/180),strong=this.charge.rows.length===4;
        for(const row of this.charge.rows) {
          const y=row*32;
          ctx.fillStyle=strong?'#ffdc92':'#c9f6ff';
          ctx.globalAlpha=this.reduced ? .1 : .1+.1*Math.sin(p*Math.PI);
          ctx.fillRect(1,y+1,318,30);
          ctx.globalAlpha=this.reduced ? .35 : .4*(1-p);
          ctx.fillRect(1,y+1,318,1);ctx.fillRect(1,y+30,318,1);
          if(!this.reduced) {
            ctx.save();ctx.beginPath();ctx.rect(0,y,320,32);ctx.clip();
            ctx.translate(-96+p*450,y);ctx.globalAlpha=.8;
            ctx.fillStyle=this.sheen;ctx.fillRect(0,1,96,30);
            ctx.fillStyle=strong?'#ffe9ac':'#edfbff';ctx.globalAlpha=.7*Math.sin(p*Math.PI);
            ctx.fillRect(80,3,2,26);ctx.restore();
          }
        }
      }
      if(this.lock) {
        const p=this.lock.age/150;
        ctx.globalAlpha=.36*(1-p);ctx.fillStyle=this.palette[this.lock.type];
        // A short grounding glint along each bottom edge, not a screen shake.
        for(const cell of this.lock.cells) {
          if(!this.lock.cells.some(other=>other.x===cell.x && other.y===cell.y+1))
            ctx.fillRect(cell.x*32+3,Math.min(638,(cell.y+1)*32-2),26,1.5);
        }
      }
      for(const echo of this.echoes) {
        const p=echo.age/300,y=echo.row*32+16;
        ctx.fillStyle=echo.gold?'#ffda8a':'#bdefff';
        ctx.globalAlpha=.12*(1-p)*(1-p);ctx.fillRect(0,y-6-p*5,320,12+p*10);
        ctx.globalAlpha=.6*(1-p)*(1-p);ctx.fillRect(0,y-.75,320,1.5);
        // An expanding pair of small edge brackets finishes the light pass.
        ctx.globalAlpha=.4*(1-p);const x=160*p;
        ctx.fillRect(158-x,y-4,2,8);ctx.fillRect(160+x,y-4,2,8);
      }
      for(const chip of this.chips) {
        const t=chip.age/1000,p=chip.age/chip.life,size=chip.size*(1-.45*p);
        ctx.save();ctx.translate(chip.x+chip.vx*t,chip.y+chip.vy*t+170*t*t);
        ctx.rotate(chip.angle+chip.spin*t);ctx.globalAlpha=.8*(1-p)*(1-p);
        ctx.fillStyle=chip.color;ctx.fillRect(-size/2,-size*.3,size,size*.6);
        ctx.fillStyle='#f4fbff';ctx.globalAlpha=.5*(1-p)*(1-p);
        ctx.fillRect(-size/2,-size*.3,size,1);ctx.restore();
      }
      ctx.globalAlpha=1;this.dirty=false;
    }
  };
})();
