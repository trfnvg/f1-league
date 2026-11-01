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
  const launchButton = byId('launch-start');
  const game = new Game();
  const session = new window.PitStackSession(machine);
  window.PitStackActiveSession=session;
  const scenery = new window.PitStackScenery(byId('scenery'),byId('venue'));
  const soundtrack = new window.PitStackAudio(byId('soundtrack'),byId('sound'),byId('volume'));
  let shownPace=-1;
  const palette = {I:'#3ee6ed',J:'#4c84ff',L:'#ff9d3b',O:'#ffdf4a',S:'#69db6a',T:'#b783ff',Z:'#ff6268'};
  const blockCache = new Map();
  const held = new Map(), keys = new Map(), touchPointers = new Set();
  const gestures = new window.PitStackGestures(act);
  let request = 0, lastTime = 0, renderedRevision = -1, clearSerial = 0;
  let messageTimer = 0, startTimer = 0, countdown = false, preparing = false, fittedDpr = 0, shownOverlay = '';
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fullscreenHome = document.createComment('Pit Stack inline position');
  let savedScroll = null, savedBodyStyles = null, lastGeometry = '', changingFullscreen = false;
  function syncViewport() {
    if (!machine.classList.contains('is-fullscreen')) return;
    const viewport = window.visualViewport;
    const native = document.fullscreenElement === machine;
    for (const [key,value] of Object.entries({
      width: native ? innerWidth : viewport?.width ?? innerWidth,
      height: native ? innerHeight : viewport?.height ?? innerHeight,
      top: native ? 0 : viewport?.offsetTop ?? 0,
      left: native ? 0 : viewport?.offsetLeft ?? 0,
    })) machine.style.setProperty(`--tetris-viewport-${key}`, `${value}px`);
  }
  const feedback = new window.PitStackFeedback(byId('feedback'),byId('track-lights'),palette,reduceMotion);

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
    const rect = deck.getBoundingClientRect();
    const style = getComputedStyle(deck);
    const sidebar = machine.querySelector('.tetris-telemetry').getBoundingClientRect().width;
    const availableH = rect.height-parseFloat(style.paddingTop)-parseFloat(style.paddingBottom);
    const gap = parseFloat(style.columnGap)||16;
    const dpr = Math.min(3,window.devicePixelRatio||1);
    const geometry = [rect.width,availableH,sidebar,gap,dpr].join(':');
    if (geometry === lastGeometry) return;
    lastGeometry = geometry;
    clearHeld();
    const width = Math.floor(Math.min((availableH-4)/2, rect.width-sidebar-gap-10));
    if (width < 20) return;
    board.style.width = `${width+4}px`; board.style.height = `${width*2+4}px`;
    const pixelWidth = Math.round(width*dpr), pixelHeight = pixelWidth*2;
    if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
      canvas.width = pixelWidth; canvas.height = pixelHeight;
      ctx.imageSmoothingEnabled = false;
    }
    nextCanvas.width = Math.round(128*dpr); nextCanvas.height = Math.round(112*dpr);
    nextCtx.imageSmoothingEnabled = false; fittedDpr = dpr;
    feedback.resize(pixelWidth,pixelHeight);
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
    feedback.observe(game);
    ctx.setTransform(canvas.width/320,0,0,canvas.height/640,0,0);
    ctx.fillStyle = '#07090f'; ctx.fillRect(0,0,320,640);
    ctx.strokeStyle = '#161b25'; ctx.lineWidth = .5;
    ctx.beginPath();
    for (let x=1;x<10;x++) { ctx.moveTo(x*32,0); ctx.lineTo(x*32,640); }
    for (let y=1;y<20;y++) { ctx.moveTo(0,y*32); ctx.lineTo(320,y*32); }
    ctx.stroke();
    if(game.piece) {
      const landing=game.landing();
      if(landing && landing.y!==game.piece.y) {
        const projected=cells(landing).filter(cell=>cell.y>=0);
        const occupied=new Set(projected.map(cell=>`${cell.x},${cell.y}`));
        ctx.save();ctx.fillStyle=palette[landing.type];ctx.globalAlpha=.035;
        for(const p of projected)ctx.fillRect(p.x*32+1,p.y*32+1,30,30);
        ctx.globalAlpha=.46;ctx.strokeStyle=palette[landing.type];ctx.lineWidth=1.4;
        ctx.beginPath();
        // Only the outside silhouette is outlined, so it cannot look like a stack.
        for(const {x,y} of projected) {
          if(!occupied.has(`${x},${y-1}`)){ctx.moveTo(x*32+.8,y*32+.8);ctx.lineTo((x+1)*32-.8,y*32+.8);}
          if(!occupied.has(`${x},${y+1}`)){ctx.moveTo(x*32+.8,(y+1)*32-.8);ctx.lineTo((x+1)*32-.8,(y+1)*32-.8);}
          if(!occupied.has(`${x-1},${y}`)){ctx.moveTo(x*32+.8,y*32+.8);ctx.lineTo(x*32+.8,(y+1)*32-.8);}
          if(!occupied.has(`${x+1},${y}`)){ctx.moveTo((x+1)*32-.8,y*32+.8);ctx.lineTo((x+1)*32-.8,(y+1)*32-.8);}
        }
        ctx.stroke();ctx.restore();
      }
    }
    game.board.forEach((row,y) => row.forEach((type,x) => {
      if(!type)return;
      const scale=feedback.squash(x,y);
      const p=game.clearing.includes(y)?Math.min(1,game.clearClock/180):0;
      // Keep the row readable during its light pass, then dissolve left→right.
      const dissolve=Math.max(0,(p-.42-x*.022)/(.58-x*.022));
      const inset=reduceMotion?0:dissolve*3;
      ctx.globalAlpha=reduceMotion?1:1-dissolve*dissolve;
      ctx.drawImage(block(type),x*32+inset,y*32+32*(1-scale)+inset,32-2*inset,32*scale-2*inset);
      ctx.globalAlpha=1;
    }));
    if (game.piece) for (const p of cells(game.piece)) {
      if (p.y >= 0) ctx.drawImage(block(game.piece.type),p.x*32,p.y*32,32,32);
    }
    if(renderedRevision!==game.revision) {
      const score=game.score.toLocaleString('ru-RU');
      byId('score').textContent = score;
      byId('score').style.setProperty('--score-chars',Math.max(1,score.length));
      byId('lines').textContent = game.lines;
      scenery.update(game.lines);
      byId('route-progress').style.width=`${(game.lines%10)*10}%`;
      updatePace();
      drawNext();
      const playable = ['running','clearing'].includes(game.phase);
      pauseButton.disabled = !playable || countdown;
      pauseButton.textContent = game.paused ? 'Продолжить' : 'Пауза';
      if (launchButton) {
        launchButton.textContent = game.paused ? 'Продолжить →' : game.phase === 'over' ? 'Играть снова →' : 'Играть →';
        launchButton.disabled = preparing || countdown;
      }
      if (!countdown) {
        const mode = game.paused ? 'paused' : game.phase;
        overlay.hidden = playable && !game.paused;
        if (shownOverlay !== mode) {
          shownOverlay = mode;
          if(mode === 'over') {
            session.finish();
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
            byId('overlay-text').textContent = 'Пробел или Enter — продолжить. P / Esc — пауза.';
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
    }
    feedback.paint();renderedRevision = game.revision;
  }
  function act(action) {
    if (!game.active || countdown) return;
    if(!session.record(action,game)){schedule();return;}
    if(action==='left') game.move(-1);
    if(action==='right') game.move(1);
    if(action==='rotate') game.turn();
    if(action==='rotateCCW') game.turn(-1);
    if(action==='down') game.down();
    if(action==='drop') {feedback.trace(game.piece,game.landing());game.drop();}
    feedback.observe(game);
    schedule();
  }
  function updatePace() {
    const pace=game.pace>=29?4:game.pace>=19?3:game.pace>=9?2:game.pace>=4?1:0;
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
    if(!countdown && !game.paused) { updateHeld(dt); session.advance(game,dt); }
    feedback.observe(game);
    feedback.step(dt,game.paused || countdown);
    updatePace();
    if(renderedRevision !== game.revision || feedback.dirty) draw();
    if(!game.paused && ['running','clearing'].includes(game.phase)) schedule();
    else lastTime = 0;
  }
  function schedule() { if(!request) request = window.requestAnimationFrame(frame); }
  function togglePause() {
    if(countdown) return;
    clearHeld();
    if(game.pause()) {
      feedback.observe(game);
      soundtrack.setPlaying(!game.paused);
      lastTime=0; canvas.focus({preventScroll:true}); schedule();
    }
  }
  async function start() {
    if(countdown || preparing) return;
    if (window.matchMedia('(pointer:coarse), (max-width:600px)').matches && !machine.classList.contains('is-fullscreen')) enterFullscreen();
    if(game.paused) { togglePause(); return; }
    // Disabling a focused start button emits focusout with no relatedTarget.
    // Move focus inside the board first, so countdown does not pause its music.
    canvas.focus({preventScroll:true});
    soundtrack.setPlaying(true,true);
    preparing=true;startButton.disabled=true;
    if (launchButton) launchButton.disabled = true;
    try {game.random=await session.begin();}
    catch(error){
      soundtrack.setPlaying(false);clearHeld();
      byId('overlay-text').textContent=error.message;overlay.hidden=false;
      preparing=false;startButton.disabled=false;
      if (launchButton) launchButton.disabled=false;
      return;
    }
    preparing=false;
    clearHeld(); game.reset(); clearSerial=0; shownOverlay=''; countdown=true;
    feedback.reset();
    scenery.reset();
    startButton.disabled = true;
    byId('overlay-caption').textContent = 'ПЯТЬ КРАСНЫХ ОГНЕЙ';
    byId('overlay-title').textContent = 'На старт…';
    byId('overlay-text').textContent = 'Следи за следующей фигурой.';
    overlay.hidden = false; renderedRevision=-1; schedule();
    startTimer = setTimeout(() => {
      countdown=false; startButton.disabled=false; game.start();
      if (launchButton) launchButton.disabled=false;
      overlay.hidden=true; lastTime=0;
      canvas.focus({preventScroll:true}); schedule();
      if(document.hidden || (window.matchMedia('(pointer:coarse), (max-width:600px)').matches && !machine.classList.contains('is-fullscreen'))) { game.pause(); schedule(); }
    },reduceMotion?0:650);
  }
  startButton.addEventListener('click',start);
  launchButton?.addEventListener('click',start);
  pauseButton.addEventListener('click',togglePause);
  const sample = e => ({id:e.pointerId,x:e.clientX,y:e.clientY,time:e.timeStamp});
  const gesturePiece = () => game.active && !countdown ? game.spawnSerial : -1;
  canvas.addEventListener('contextmenu',e=>e.preventDefault());
  for (const type of ['selectstart','dragstart','contextmenu']) machine.addEventListener(type,e=>e.preventDefault());
  machine.addEventListener('touchmove',e=>{
    if (machine.classList.contains('is-fullscreen') && !e.target.closest('input[type="range"]')) e.preventDefault();
  },{passive:false});
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
  const bindings = {ArrowLeft:'left',KeyA:'left',ArrowRight:'right',KeyD:'right',ArrowUp:'rotate',KeyW:'rotate',KeyX:'rotate',KeyZ:'rotateCCW',ArrowDown:'down',KeyS:'down'};
  document.addEventListener('keydown',e=>{
    const focused=document.activeElement;
    // Range arrows and focused toolbar buttons keep native keyboard controls.
    if(focused?.matches('input,select,textarea,[contenteditable="true"]'))return;
    if(['Space','Enter','NumpadEnter'].includes(e.code)) {
      if(focused?.closest('button,a,[role="button"]'))return;
      const pageFocus=!focused || focused===document.body || focused===document.documentElement;
      if(!pageFocus && !machine.contains(focused) && !machine.classList.contains('is-fullscreen'))return;
      e.preventDefault();
      if(e.repeat || keys.has(e.code) || countdown)return;
      keys.set(e.code,true);
      if(['ready','over'].includes(game.phase))start();
      else if(game.paused)togglePause();
      else act('drop');
      return;
    }
    if(!machine.contains(focused) && !machine.classList.contains('is-fullscreen')) return;
    if(e.code==='Escape') {
      if(!game.paused && ['running','clearing'].includes(game.phase)) togglePause();
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
    if(!game.paused && ['running','clearing'].includes(game.phase)) { game.pause(); feedback.observe(game); schedule(); }
  }
  document.addEventListener('visibilitychange',()=>{ if(document.hidden) autoPause(); });
  window.addEventListener('blur',autoPause);
  machine.addEventListener('focusout',e=>{
    if(!changingFullscreen && !machine.classList.contains('is-fullscreen') && !machine.contains(e.relatedTarget)) autoPause();
  });
  function setFullscreen(on) {
    if (on === machine.classList.contains('is-fullscreen')) return;
    if (!on) autoPause();
    changingFullscreen = true;
    if (on) {
      savedScroll = {x:window.scrollX,y:window.scrollY};
      savedBodyStyles = ['position','top','left','width'].map(key=>[key,document.body.style.getPropertyValue(key),document.body.style.getPropertyPriority(key)]);
      machine.before(fullscreenHome);
      // Escape transformed/clipped page ancestors and the site's stacking contexts.
      document.body.append(machine);
      Object.assign(document.body.style,{position:'fixed',top:`-${savedScroll.y}px`,left:'0px',width:'100%'});
      window.getSelection()?.removeAllRanges();
    }
    machine.classList.toggle('is-fullscreen',on);
    document.body.classList.toggle('tetris-fullscreen',on);
    fullscreenButton.textContent=on?'Выйти':'На весь экран';
    fullscreenButton.setAttribute('aria-pressed',String(on));
    if (!on) {
      fullscreenHome.replaceWith(machine);
      for (const [key,value,priority] of savedBodyStyles || []) {
        if (value) document.body.style.setProperty(key,value,priority);
        else document.body.style.removeProperty(key);
      }
      for (const key of ['top','left','width','height']) machine.style.removeProperty(`--tetris-viewport-${key}`);
      if (savedScroll) window.scrollTo({left:savedScroll.x,top:savedScroll.y,behavior:'instant'});
      savedScroll = null;
    }
    syncViewport();
    resize();
    changingFullscreen = false;
  }
  function enterFullscreen() {
    setFullscreen(true);
    // iPhone Safari uses the same viewport-filling fallback when the API is absent.
    if (machine.requestFullscreen) machine.requestFullscreen().catch(()=>{});
  }
  fullscreenButton.addEventListener('click',async()=>{
    if(machine.classList.contains('is-fullscreen')) {
      if(document.fullscreenElement) await document.exitFullscreen().catch(()=>{});
      setFullscreen(false);
    } else {
      enterFullscreen();
    }
    canvas.focus({preventScroll:true});
  });
  document.addEventListener('fullscreenchange',()=>{
    if(!document.fullscreenElement && machine.classList.contains('is-fullscreen')) { autoPause(); setFullscreen(false); }
  });
  const observer = new ResizeObserver(resize); observer.observe(deck);
  const viewportChanged = () => { syncViewport(); resize(); };
  window.addEventListener('resize',viewportChanged);
  window.visualViewport?.addEventListener('resize',viewportChanged);
  window.visualViewport?.addEventListener('scroll',viewportChanged);
  window.addEventListener('pagehide',()=>{
    autoPause(); clearTimeout(startTimer);
    if(countdown) {
      countdown=false; startButton.disabled=false; game.reset(); shownOverlay='';
      if (launchButton) launchButton.disabled=false;
      byId('overlay-title').textContent='Готов к старту?'; startButton.textContent='Начать заезд ↗';
    }
  });
  // An unstarted/paused game paints once; no perpetual idle animation or timers.
  resize(); schedule();
})();
