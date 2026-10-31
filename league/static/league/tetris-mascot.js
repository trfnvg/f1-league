(function () {
  'use strict';
  const CELEBRATION_BEATS = [[170,2],[480,3],[650,4],[850,3],[1080,4],[1350,3]];
  // A decorative observer only: never changes the board, score or game timing.
  class PitStackMascot {
    constructor(element, reducedMotion = false) {
      this.element = element;
      this.reducedMotion = reducedMotion;
      this.reset();
    }
    reset() {
      this.serial = 0;
      this.anticipatedLock = -1;
      this.lockSerial = 0;
      this.remaining = 0;
      this.setState('idle', true);
      this.setPaused(false);
    }
    setState(state, restart = false) {
      if (this.state === state && !restart) return;
      this.state = state;
      this.clock = 0;
      if (this.element) this.element.dataset.state = state;
      this.updateFrame();
    }
    updateFrame() {
      let frame = 0;
      if (this.state === 'over') frame = 5;
      else if (this.state === 'anticipate') frame = 2;
      else if (this.state === 'celebrate') {
        // Surprise -> fists up -> thumbs up, with two short victory gestures.
        frame = this.reducedMotion ? 4 : (CELEBRATION_BEATS.find(([end]) => this.clock < end)?.[1] ?? 4);
      } else if (this.state === 'placing') {
        frame = this.reducedMotion ? 0 : (Math.floor(this.clock / 150) % 2 ? 0 : 1);
      } else if (!this.reducedMotion && this.clock >= 1800 && this.clock < 2100) frame = 1;
      if (this.frame === frame) return;
      this.frame = frame;
      if (this.element) this.element.dataset.frame = String(frame);
    }
    setPaused(paused) {
      if (this.element && this.element.dataset.paused !== String(paused))
        this.element.dataset.paused = String(paused);
    }
    observe(game) {
      this.setPaused(game.paused);
      if (game.phase === 'over') {
        this.remaining = 0;
        this.setState('over');
        return;
      }
      if (game.clearSerial < this.serial || game.phase === 'ready') this.reset();
      if (game.phase === 'clearing' && game.clearing?.length === 4 &&
          this.anticipatedLock !== game.lockSerial) {
        this.anticipatedLock = game.lockSerial;
        this.remaining = 0;
        this.setState('anticipate');
      }
      if (game.clearSerial !== this.serial) {
        this.serial = game.clearSerial;
        // Small clears acknowledge the build; four lines finish the little car.
        // A small clear during a celebration must not cut off the big reaction.
        if (game.lastClear !== 4 && this.state === 'celebrate') return;
        this.remaining = game.lastClear === 4 ? 3000 : 800;
        this.setState(game.lastClear === 4 ? 'celebrate' : 'placing', true);
        if (game.lastClear === 4) {
          // Consecutive Tetrises restart one bounded celebration, never queue it.
          for (const animation of this.element?.getAnimations?.({subtree: true}) || []) {
            animation.cancel();
            animation.play();
          }
        }
      }
      if (game.lockSerial !== this.lockSerial) {
        this.lockSerial = game.lockSerial;
        if (!this.remaining && game.phase === 'running') {
          this.remaining = 360;
          this.setState('placing');
        }
      }
    }
    step(ms, paused) {
      if (paused) return;
      const dt = Math.max(0, Math.min(50, ms));
      this.clock = this.state === 'idle' ? (this.clock + dt) % 2400 : this.clock + dt;
      if (this.remaining) {
        this.remaining = Math.max(0, this.remaining - dt);
        if (!this.remaining) this.setState('idle');
      }
      this.updateFrame();
    }
  }
  window.PitStackMascot = PitStackMascot;
})();
