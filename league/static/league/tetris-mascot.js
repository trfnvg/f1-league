(function () {
  'use strict';
  // A decorative observer only: never changes the board, score or game timing.
  class PitStackMascot {
    constructor(element) {
      this.element = element;
      this.reset();
    }
    reset() {
      this.serial = 0;
      this.anticipatedLock = -1;
      this.lockSerial = 0;
      this.remaining = 0;
      this.setState('idle');
      this.setPaused(false);
    }
    setState(state) {
      if (!this.element || this.element.dataset.state === state) return;
      this.element.dataset.state = state;
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
        if (game.lastClear !== 4 && this.element?.dataset.state === 'celebrate') return;
        this.remaining = game.lastClear === 4 ? 3000 : 800;
        this.setState(game.lastClear === 4 ? 'celebrate' : 'placing');
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
      if (paused || !this.remaining) return;
      this.remaining = Math.max(0, this.remaining - Math.max(0, Math.min(50, ms)));
      if (!this.remaining) this.setState('idle');
    }
  }
  window.PitStackMascot = PitStackMascot;
})();
