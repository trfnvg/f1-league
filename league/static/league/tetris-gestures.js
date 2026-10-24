/* Relative swipe controls. No DOM or timers: one gesture owns one falling piece. */
(function (root) {
  'use strict';
  class Gestures {
    constructor(action) { this.action = action; this.state = null; }
    begin({id,x,y,time,cellSize,piece,tapDirection=1}) {
      if (this.state) { this.cancel(); return false; }
      const step = Math.max(12,Math.min(32,cellSize*.85));
      this.state = {id,x,y,time,piece,tapDirection,step,anchorX:x,anchorY:y,
        slop:Math.max(6,Math.min(10,cellSize*.35)),axis:null,maxDistance:0,soft:false};
      return true;
    }
    cancel() { this.state = null; }
    valid(sample,piece) {
      const s = this.state;
      if (!s || sample.id !== s.id) return false;
      if (piece !== s.piece) { this.cancel(); return false; }
      return true;
    }
    softDrop(sample) {
      const s = this.state;
      const steps = Math.max(0,Math.trunc((sample.y-s.anchorY)/s.step));
      if (!steps) return;
      s.soft = true; s.anchorY += steps*s.step;
      for (let i=0;i<Math.min(20,steps);i++) this.action('down');
    }
    move(sample,piece) {
      if (!this.valid(sample,piece)) return;
      const s = this.state, dx = sample.x-s.x, dy = sample.y-s.y;
      s.maxDistance = Math.max(s.maxDistance,Math.hypot(dx,dy));
      if (!s.axis) {
        if (Math.abs(dx)>s.slop && Math.abs(dx)>Math.abs(dy)*1.15) s.axis='x';
        else if (Math.abs(dy)>s.slop && Math.abs(dy)>Math.abs(dx)*1.15) s.axis='y';
      }
      if (s.axis === 'x') {
        const steps = Math.trunc((sample.x-s.anchorX)/s.step);
        s.anchorX += steps*s.step;
        for(let i=0;i<Math.min(10,Math.abs(steps));i++) this.action(steps<0?'left':'right');
      } else if (s.axis === 'y' && sample.time-s.time>=170 &&
          !(sample.time-s.time<=320 && dy>0 && dy/(sample.time-s.time)>=.45)) {
        // Wait briefly to distinguish an intentional flick from a slow drag.
        // Once soft dropping starts, release can never become a hard drop.
        this.softDrop(sample);
      }
    }
    end(sample,piece) {
      if (!this.valid(sample,piece)) return;
      // Include the release position when no intermediate event was delivered.
      this.move(sample,piece);
      const s = this.state, dx = sample.x-s.x, dy = sample.y-s.y;
      const duration = Math.max(1,sample.time-s.time);
      if (s.axis === 'y') {
        if (!s.soft && duration<=320 && dy>=Math.max(28,s.step*1.8) &&
            dy>Math.abs(dx)*1.35 && dy/duration>=.45) this.action('drop');
        else this.softDrop(sample);
      } else if (!s.axis && s.maxDistance<=s.slop && duration<=350) {
        this.action(s.tapDirection<0?'rotateCCW':'rotate');
      }
      this.cancel();
    }
  }
  root.PitStackGestures = Gestures;
})(typeof window !== 'undefined' ? window : globalThis);
