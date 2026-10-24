(function () {
  'use strict';
  const {Game, SHAPES, cells} = window.PitStack;
  const machine = document.getElementById('tetris-machine');
  if (!machine) return;
  const byId = id => document.getElementById(`tetris-${id}`);
  const canvas = byId('canvas'), ctx = canvas.getContext('2d', {alpha: false});
  const nextCanvas = byId('next'), nextCtx = nextCanvas.getContext('2d');
  const board = byId('board'), deck = byId('deck'), overlay = byId('overlay');
  const pauseButton = byId('pause'), startButton = byId('start'), fullscreenButton = byId('fullscreen');
  const game = new Game();
  const scenery = new window.PitStackScenery(byId('scenery'),byId('venue'));
  const soundtrack = new window.PitStackAudio(byId('soundtrack'),byId('sound'),byId('volume'));
  let shownPace=-1;
  const palette = {I:'#3ee6ed',J:'#4c84ff',L:'#ff9d3b',O:'#ffdf4a',S:'#69db6a',T:'#b783ff',Z:'#ff6268'};
  const blockCache = new Map();
  const held = new Map(), keys = new Map(), touchPointers = new Set();
  const gestures = new window.PitStackGestures(act);
  let request = 0, lastTime = 0, renderedRevision = -1, clearSerial = 0;
  let messageTimer = 0, startTimer = 0, countdown = false, fittedDpr = 0, shownOverlay = '';
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function block(type) {
    if (blockCache.has(type)) return blockCache.get(type);
    const tile = document.createElement('canvas'); tile.width = tile.height = 64;
    const t = tile.getContext('2d'), color = palette[type];
    // Simple saturated classic tiles: no rivets, textures or stripes inside
    // the shapes. A narrow bevel separates adjacent cells at small sizes.
    t.fillStyle = '#07090f'; t.fillRect(0,0,64,64);
    t.fillStyle = color; t.fillRect(2,2,60,60);
    t.fillStyle = '#ffffff55'; t.fillRect(2,2,60,4); t.fillRect(2,6,4,52);
    t.fillStyle = '#00000040'; t.fillRect(6,58,56,4); t.fillRect(58,6,4,52);
    t.strokeStyle = '#ffffff26'; t.lineWidth = 2; t.strokeRect(10,10,44,44);
    blockCache.set(type,tile); return tile;
  }
  function resize() {
    clearHeld();
    const rect = deck.getBoundingClientRect();
    const style = getComputedStyle(deck);
    const sidebar = machine.querySelector('.tetris-telemetry').getBoundingClientRect().width;
    const availableH = rect.height-parseFloat(style.paddingTop)-parseFloat(style.paddingBottom);
    const gap = parseFloat(style.columnGap)||16;
    const width = Math.floor(Math.min((availableH-4)/2, rect.width-sidebar-gap-10));
    if (width < 20) return;
    board.style.width = `${width+4}px`; board.style.height = `${width*2+4}px`;
    const dpr = Math.min(3,window.devicePixelRatio||1);
    const pixelWidth = Math.round(width*dpr), pixelHeight = pixelWidth*2;
    if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
      canvas.width = pixelWidth; canvas.height = pixelHeight;
      ctx.imageSmoothingEnabled = false;
    }
    nextCanvas.width = Math.round(128*dpr); nextCanvas.height = Math.round(112*dpr);
    nextCtx.imageSmoothingEnabled = false; fittedDpr = dpr;
    // Resizing clears Canvas synchronously. Repaint now, including while paused,
    // rather than leaving a black frame until the browser's next animation tick.
    renderedRevision = -1; draw(); schedule();
  }
  function drawNext() {
    nextCtx.setTransform(nextCanvas.width/128,0,0,nextCanvas.height/112,0,0);
    nextCtx.clearRect(0,0,128,112);
    if (!game.next) return;
    const matrix = SHAPES[game.next], occupied = [];
    matrix.forEach((row,y) => row.forEach((v,x) => { if(v) occupied.push({x,y}); }));
    const minX = Math.min(...occupied.map(p=>p.x)), maxX = Math.max(...occupied.map(p=>p.x));
    const minY = Math.min(...occupied.map(p=>p.y)), maxY = Math.max(...occupied.map(p=>p.y));
    const size = 25, startX = (128-(maxX-minX+1)*size)/2, startY = (112-(maxY-minY+1)*size)/2;
    for (const p of occupied) nextCtx.drawImage(block(game.next),startX+(p.x-minX)*size,startY+(p.y-minY)*size,size,size);
  }
  function draw() {
    ctx.setTransform(canvas.width/320,0,0,canvas.height/640,0,0);
    ctx.fillStyle = '#07090f'; ctx.fillRect(0,0,320,640);
    ctx.strokeStyle = '#161b25'; ctx.lineWidth = .5;
    ctx.beginPath();
    for (let x=1;x<10;x++) { ctx.moveTo(x*32,0); ctx.lineTo(x*32,640); }
    for (let y=1;y<20;y++) { ctx.moveTo(0,y*32); ctx.lineTo(320,y*32); }
    ctx.stroke();
    game.board.forEach((row,y) => row.forEach((type,x) => {
      if(type) ctx.drawImage(block(type),x*32,y*32,32,32);
    }));
    if (game.piece) for (const p of cells(game.piece)) {
      if (p.y >= 0) ctx.drawImage(block(game.piece.type),p.x*32,p.y*32,32,32);
    }
    if (game.clearing.length) {
      const progress = Math.min(1,game.clearClock/180);
      ctx.fillStyle = reduceMotion ? '#f0dfb8aa' : `rgba(240,223,184,${.85*(1-progress)})`;
      for(const y of game.clearing) ctx.fillRect(0,y*32,320,32);
    }
    byId('score').textContent = game.score.toLocaleString('ru-RU');
    byId('lines').textContent = game.lines;
    scenery.update(game.lines);
    byId('route-progress').style.width=`${(game.lines%10)*10}%`;
    updatePace();
    drawNext();
    const playable = ['running','clearing'].includes(game.phase);
    pauseButton.disabled = !playable || countdown;
    pauseButton.textContent = game.paused ? 'Продолжить' : 'Пауза';
    if (!countdown) {
      const mode = game.paused ? 'paused' : game.phase;
      overlay.hidden = playable && !game.paused;
      if (shownOverlay !== mode) {
        shownOverlay = mode;
        if(mode === 'over') {
          soundtrack.setPlaying(false);
          byId('overlay-caption').textContent = 'ЗАЕЗД ЗАВЕРШЁН';
          byId('overlay-title').textContent = 'Финиш!';
          byId('overlay-text').textContent = `${game.score.toLocaleString('ru-RU')} очков · ${game.lines} линий`;
          startButton.textContent = 'Новый заезд ↗';
          clearHeld();
        } else if(mode === 'paused') {
          soundtrack.setPlaying(false);
          byId('overlay-caption').textContent = 'КРАСНЫЙ ФЛАГ';
          byId('overlay-title').textContent = 'Пауза';
          byId('overlay-text').textContent = 'Передохни. Гараж подождёт.';
          startButton.textContent = 'Продолжить ↗';
        }
      }
    }
    if (clearSerial !== game.clearSerial) {
      clearSerial = game.clearSerial;
      const label = ['','ЛИНИЯ!','ДВОЙНАЯ!','ТРОЙНАЯ!','ПОУЛ-ПОЗИШЕН!'][game.lastClear];
      const message = byId('line-message'); message.textContent = label;
      message.classList.remove('is-visible');
      // Restart a single finite CSS animation only when a row clear completes.
      void message.offsetWidth; message.classList.add('is-visible');
      clearTimeout(messageTimer); messageTimer = setTimeout(()=>message.classList.remove('is-visible'),950);
    }
    renderedRevision = game.revision;
  }
  function act(action) {
    if (!game.active || countdown) return;
    if(action==='left') game.move(-1);
    if(action==='right') game.move(1);
    if(action==='rotate') game.turn();
    if(action==='rotateCCW') game.turn(-1);
    if(action==='down') game.down();
    if(action==='drop') game.drop();
    schedule();
  }
  function updatePace() {
    soundtrack.setPace(game.pace);
    const pace=Math.min(4,Math.floor(game.pace/3));
    if(shownPace===pace) return;
    shownPace=pace;
    byId('pace').textContent=['СТАРТ','РАЗГОН','АТАКА','НА ПРЕДЕЛЕ','МАКСИМУМ'][pace];
    machine.querySelectorAll('.tetris-pace i').forEach((bar,i)=>bar.classList.toggle('is-lit',i<=pace));
  }
  function press(token,action) {
    if(held.has(token) || !game.active || countdown) return;
    act(action);
    if (['left','right','down'].includes(action)) held.set(token,{action,wait:action==='down'?45:170});
  }
  function clearHeld() {
    held.clear(); keys.clear(); gestures.cancel();
    for (const id of touchPointers) {
      if (canvas.hasPointerCapture(id)) canvas.releasePointerCapture(id);
    }
    touchPointers.clear();
  }
  function updateHeld(ms) {
    for(const state of held.values()) {
      state.wait -= ms;
      if(state.wait <= 0) { act(state.action); state.wait += state.action==='down'?45:65; }
    }
  }
  function frame(time) {
    request = 0;
    const dt = lastTime ? Math.max(0,Math.min(50,time-lastTime)) : 0; lastTime = time;
    if(fittedDpr !== Math.min(3,window.devicePixelRatio||1)) resize();
    if(!countdown && !game.paused) { updateHeld(dt); game.update(dt); }
    updatePace();
    if(renderedRevision !== game.revision) draw();
    if(!game.paused && ['running','clearing'].includes(game.phase)) schedule();
    else lastTime = 0;
  }
  function schedule() { if(!request) request = window.requestAnimationFrame(frame); }
  function togglePause() {
    if(countdown) return;
    clearHeld();
    if(game.pause()) {
      soundtrack.setPlaying(!game.paused);
      lastTime=0; canvas.focus({preventScroll:true}); schedule();
    }
  }
  function start() {
    if(countdown) return;
    if(game.paused) { togglePause(); return; }
    // Disabling a focused start button emits focusout with no relatedTarget.
    // Move focus inside the board first, so countdown does not pause its music.
    canvas.focus({preventScroll:true});
    soundtrack.setPlaying(true,true);
    clearHeld(); game.reset(); clearSerial=0; shownOverlay=''; countdown=true;
    scenery.reset();
    startButton.disabled = true;
    byId('overlay-caption').textContent = 'ПЯТЬ КРАСНЫХ ОГНЕЙ';
    byId('overlay-title').textContent = 'На старт…';
    byId('overlay-text').textContent = 'Следи за следующей фигурой.';
    overlay.hidden = false; renderedRevision=-1; schedule();
    startTimer = setTimeout(() => {
      countdown=false; startButton.disabled=false; game.start();
      overlay.hidden=true; lastTime=0;
      canvas.focus({preventScroll:true}); schedule();
      if(document.hidden) { game.pause(); schedule(); }
    },reduceMotion?0:650);
  }
  startButton.addEventListener('click',start);
  pauseButton.addEventListener('click',togglePause);
  const sample = e => ({id:e.pointerId,x:e.clientX,y:e.clientY,time:e.timeStamp});
  const gesturePiece = () => game.active && !countdown ? game.spawnSerial : -1;
  canvas.addEventListener('contextmenu',e=>e.preventDefault());
  canvas.addEventListener('pointerdown',e=>{
    if(e.button!==0 || !game.active || countdown) return;
    e.preventDefault(); canvas.focus({preventScroll:true});
    canvas.setPointerCapture(e.pointerId); touchPointers.add(e.pointerId);
    // A second finger cancels the gesture; it must not rotate or drop a piece.
    if(touchPointers.size>1) { gestures.cancel(); return; }
    const rect=canvas.getBoundingClientRect();
    gestures.begin({...sample(e),cellSize:rect.width/10,piece:gesturePiece(),
      tapDirection:e.clientX<rect.left+rect.width/2?-1:1});
  });
  canvas.addEventListener('pointermove',e=>{
    if(!touchPointers.has(e.pointerId)) return;
    e.preventDefault(); gestures.move(sample(e),gesturePiece());
  });
  canvas.addEventListener('pointerup',e=>{
    if(!touchPointers.has(e.pointerId)) return;
    e.preventDefault(); touchPointers.delete(e.pointerId);
    gestures.end(sample(e),gesturePiece());
  });
  function cancelPointer(e) {
    touchPointers.delete(e.pointerId);
    if(gestures.state?.id===e.pointerId) gestures.cancel();
  }
  canvas.addEventListener('pointercancel',cancelPointer);
  canvas.addEventListener('lostpointercapture',cancelPointer);
  const bindings = {ArrowLeft:'left',KeyA:'left',ArrowRight:'right',KeyD:'right',ArrowUp:'rotate',KeyW:'rotate',KeyX:'rotate',KeyZ:'rotateCCW',ArrowDown:'down',KeyS:'down',Enter:'drop',NumpadEnter:'drop'};
  document.addEventListener('keydown',e=>{
    const focused=document.activeElement;
    // Range arrows and focused toolbar buttons keep native keyboard controls.
    if(focused?.matches('input,select,textarea,[contenteditable="true"]'))return;
    if(e.code==='Space') {
      if(focused?.closest('button,a,[role="button"]'))return;
      const pageFocus=!focused || focused===document.body || focused===document.documentElement;
      if(!pageFocus && !machine.contains(focused) && !machine.classList.contains('is-fullscreen'))return;
      e.preventDefault();
      if(e.repeat || countdown)return;
      if(['ready','over'].includes(game.phase))start();
      else togglePause();
      return;
    }
    if(!machine.contains(focused) && !machine.classList.contains('is-fullscreen')) return;
    if(['Enter','NumpadEnter'].includes(e.code) && focused?.closest('button,a,[role="button"]'))return;
    if(e.code==='Escape') {
      if(game.active) togglePause();
      if(machine.classList.contains('is-fullscreen') && !document.fullscreenElement) setFullscreen(false);
      return;
    }
    if(e.code==='KeyP') { e.preventDefault(); if(!e.repeat) togglePause(); return; }
    if(!bindings[e.code] || countdown) return;
    if(!game.active) return;
    e.preventDefault();
    if(e.repeat || keys.has(e.code)) return;
    keys.set(e.code,true); press(`key-${e.code}`,bindings[e.code]);
  });
  document.addEventListener('keyup',e=>{ keys.delete(e.code); held.delete(`key-${e.code}`); });
  function autoPause() {
    soundtrack.setPlaying(false);
    clearHeld();
    if(!game.paused && ['running','clearing'].includes(game.phase)) { game.pause(); schedule(); }
  }
  document.addEventListener('visibilitychange',()=>{ if(document.hidden) autoPause(); });
  window.addEventListener('blur',autoPause);
  machine.addEventListener('focusout',e=>{ if(!machine.contains(e.relatedTarget)) autoPause(); });
  function setFullscreen(on) {
    machine.classList.toggle('is-fullscreen',on);
    document.body.classList.toggle('tetris-fullscreen',on);
    fullscreenButton.textContent=on?'Выйти из экрана':'На весь экран';
    fullscreenButton.setAttribute('aria-pressed',String(on));
    resize();
  }
  fullscreenButton.addEventListener('click',async()=>{
    if(machine.classList.contains('is-fullscreen')) {
      if(document.fullscreenElement) await document.exitFullscreen().catch(()=>{});
      setFullscreen(false);
    } else {
      setFullscreen(true);
      // Fixed-viewport fallback also works on iPhones without element fullscreen.
      if(machine.requestFullscreen) await machine.requestFullscreen().catch(()=>{});
    }
    canvas.focus({preventScroll:true});
  });
  document.addEventListener('fullscreenchange',()=>{
    if(!document.fullscreenElement && machine.classList.contains('is-fullscreen')) { autoPause(); setFullscreen(false); }
  });
  const observer = new ResizeObserver(resize); observer.observe(deck);
  window.addEventListener('resize',resize);
  window.visualViewport?.addEventListener('resize',resize);
  window.addEventListener('pagehide',()=>{
    autoPause(); clearTimeout(startTimer);
    if(countdown) {
      countdown=false; startButton.disabled=false; game.reset(); shownOverlay='';
      byId('overlay-title').textContent='Готов к старту?'; startButton.textContent='Начать заезд ↗';
    }
  });
  // An unstarted/paused game paints once; no perpetual idle animation or timers.
  resize(); schedule();
})();
