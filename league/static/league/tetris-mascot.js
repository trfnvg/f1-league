(function () {
  'use strict';
  // A decorative observer only: never changes the board, score or game timing.
  class PitStackMascot {
    constructor(element) {
      this.element = element;
      this.caption = element?.querySelector('figcaption');
      this.reset();
    }
    reset() {
      this.serial = 0;
      this.remaining = 0;
      this.setState('idle');
      this.setPaused(false);
    }
    setState(state) {
      if (!this.element || this.element.dataset.state === state) return;
      this.element.dataset.state = state;
      if (this.caption) this.caption.textContent = {
        idle: 'АЛОНСО · СБОРКА', placing: 'ДЕТАЛЬ НА МЕСТЕ',
        celebrate: 'БОЛИД ГОТОВ!', over: 'ЕЩЁ ОДНА ПОПЫТКА?',
      }[state];
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
      if (game.clearSerial !== this.serial) {
        this.serial = game.clearSerial;
        // Small clears acknowledge the build; four lines finish the little car.
        this.remaining = game.lastClear === 4 ? 2400 : 800;
        this.setState(game.lastClear === 4 ? 'celebrate' : 'placing');
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
