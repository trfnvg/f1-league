/* Pit Stack: deterministic, renderer-independent classic falling-block rules. */
(function (root) {
  'use strict';
  const COLS = 10, ROWS = 20;
  const SHAPES = {
    I: [[0,0,0,0],[1,1,1,1],[0,0,0,0],[0,0,0,0]],
    J: [[1,0,0],[1,1,1],[0,0,0]],
    L: [[0,0,1],[1,1,1],[0,0,0]],
    O: [[1,1],[1,1]],
    S: [[0,1,1],[1,1,0],[0,0,0]],
    T: [[0,1,0],[1,1,1],[0,0,0]],
    Z: [[1,1,0],[0,1,1],[0,0,0]],
  };
  const TYPES = Object.keys(SHAPES);
  const clone = matrix => matrix.map(row => row.slice());
  const rotate = matrix => matrix[0].map((_, x) => matrix.map(row => row[x]).reverse());
  function cells(piece) {
    const result = [];
    piece.matrix.forEach((row, y) => row.forEach((value, x) => {
      if (value) result.push({x: piece.x+x, y: piece.y+y});
    }));
    return result;
  }

  class Game {
    constructor(random = Math.random) {
      this.random = random;
      this.revision = 0;
      this.reset();
    }
    reset() {
      this.board = Array.from({length: ROWS}, () => Array(COLS).fill(null));
      this.score = 0; this.lines = 0; this.level = 1;
      this.elapsed = 0;
      this.phase = 'ready'; this.paused = false; this.piece = null; this.next = null;
      this.clearing = []; this.clearClock = 0; this.fallClock = 0;
      this.lockClock = 0; this.lockResets = 0; this.lastClear = 0; this.clearSerial = 0;
      this.spawnSerial = 0;
      this.revision++;
    }
    randomType() { return TYPES[Math.min(6, Math.max(0, Math.floor(this.random()*7)))]; }
    start() {
      this.reset(); this.next = this.randomType(); this.phase = 'running'; this.spawn();
    }
    spawn() {
      this.spawnSerial++;
      const type = this.next;
      this.next = this.randomType();
      const matrix = clone(SHAPES[type]);
      this.piece = {type, matrix, x: Math.floor((COLS-matrix.length)/2), y: -1};
      this.fallClock = 0; this.lockClock = 0; this.lockResets = 0;
      if (!this.fits(this.piece)) this.finish();
      this.revision++;
    }
    fits(piece) {
      return cells(piece).every(({x,y}) => x >= 0 && x < COLS && y < ROWS &&
        (y < 0 || this.board[y][x] === null));
    }
    get active() { return this.phase === 'running' && !this.paused; }
    get pace() { return Math.max(this.level-1, Math.floor(this.elapsed/45000)); }
    get gravity() { return Math.max(65, 800*Math.pow(.78, this.pace)); }
    get lockDelay() { return Math.max(220, 350-this.pace*8); }
    grounded() { return this.piece && !this.fits({...this.piece, y: this.piece.y+1}); }
    resetLock(wasGrounded) {
      if (wasGrounded && this.lockResets < 10) { this.lockClock = 0; this.lockResets++; }
    }
    move(direction) {
      if (!this.active || (direction !== -1 && direction !== 1)) return false;
      const moved = {...this.piece, x: this.piece.x+direction};
      if (!this.fits(moved)) return false;
      const wasGrounded = this.grounded();
      this.piece = moved; this.resetLock(wasGrounded); this.revision++;
      return true;
    }
    turn(direction = 1) {
      if (!this.active || this.piece.type === 'O' || ![-1,1].includes(direction)) return false;
      let matrix = rotate(this.piece.matrix);
      if (direction === -1) matrix = rotate(rotate(matrix));
      const wasGrounded = this.grounded();
      // Only horizontal wall adjustments. No upward kick/climbing exploits.
      for (const offset of [0,-1,1,-2,2]) {
        const turned = {...this.piece, matrix, x: this.piece.x+offset};
        if (this.fits(turned)) {
          this.piece = turned; this.resetLock(wasGrounded); this.revision++;
          return true;
        }
      }
      return false;
    }
    down(soft = true) {
      if (!this.active) return false;
      const moved = {...this.piece, y: this.piece.y+1};
      if (!this.fits(moved)) return false;
      this.piece = moved; this.fallClock = 0; this.lockClock = 0;
      if (soft) this.score++;
      this.revision++;
      return true;
    }
    drop() {
      if (!this.active) return false;
      let distance = 0;
      while (this.fits({...this.piece, y: this.piece.y+1})) { this.piece.y++; distance++; }
      this.score += distance*2; this.lock(); return true;
    }
    lock() {
      const occupied = cells(this.piece);
      if (occupied.some(({y}) => y < 0)) { this.finish(); return; }
      occupied.forEach(({x,y}) => { this.board[y][x] = this.piece.type; });
      this.piece = null;
      this.clearing = [];
      this.board.forEach((row,y) => { if (row.every(Boolean)) this.clearing.push(y); });
      if (this.clearing.length) { this.phase = 'clearing'; this.clearClock = 0; }
      else this.spawn();
      this.revision++;
    }
    resolveClear() {
      const count = this.clearing.length;
      this.board = this.board.filter((_,y) => !this.clearing.includes(y));
      while (this.board.length < ROWS) this.board.unshift(Array(COLS).fill(null));
      this.score += [0,40,100,300,1200][count]*this.level;
      this.lines += count; this.level = 1+Math.floor(this.lines/10);
      this.lastClear = count; this.clearSerial++;
      this.clearing = []; this.phase = 'running'; this.spawn();
    }
    update(ms) {
      if (this.paused || !['running','clearing'].includes(this.phase)) return;
      const dt = Math.min(100, Math.max(0, ms));
      this.elapsed += dt;
      if (this.phase === 'clearing') {
        this.clearClock += dt;
        if (this.clearClock >= 180) this.resolveClear();
        this.revision++;
        return;
      }
      if (this.grounded()) {
        this.lockClock += dt;
        if (this.lockClock >= this.lockDelay) this.lock();
        return;
      }
      this.lockClock = 0; this.fallClock += dt;
      // Preserve fractional time at high speeds, independently of frame rate.
      while (this.fallClock >= this.gravity && !this.grounded()) {
        const remainder = this.fallClock-this.gravity;
        this.down(false); this.fallClock = remainder;
      }
    }
    pause() {
      if (!['running','clearing'].includes(this.phase)) return false;
      this.paused = !this.paused; this.revision++; return true;
    }
    finish() { this.phase = 'over'; this.piece = null; this.revision++; }
  }
  root.PitStack = Object.freeze({Game, SHAPES, TYPES, COLS, ROWS, cells});
})(typeof window !== 'undefined' ? window : globalThis);
