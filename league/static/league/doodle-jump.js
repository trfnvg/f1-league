(() => {
  const canvas = document.getElementById("doodle-canvas");
  if (!canvas) return;

  const machine = canvas.closest(".doodle-machine");
  const wrap = document.getElementById("doodle-board-wrap");
  const ctx = canvas.getContext("2d", { alpha: false });
  const overlay = document.getElementById("doodle-overlay");
  const title = document.getElementById("doodle-overlay-title");
  const copy = document.getElementById("doodle-overlay-copy");
  const kicker = document.getElementById("doodle-overlay-kicker");
  const startButton = document.getElementById("doodle-start");
  const scoreNode = document.getElementById("doodle-score");
  const bestNode = document.getElementById("doodle-best");
  const fullscreenButton = document.getElementById("doodle-fullscreen-toggle");
  const bestStorageKey = "f1-doodle-gp-best-v1";
  const art = {};
  const held = { left: false, right: false };
  const sprites = [];
  let backgroundCache = null;
  let backgroundTileHeight = 0;

  let storedBest = "0";
  try { storedBest = localStorage.getItem(bestStorageKey) || "0"; } catch (error) { /* Private browsing can disable storage. */ }
  const numericBest = Number(storedBest);
  let best = Number.isFinite(numericBest) && numericBest > 0 ? numericBest : 0;
  let width = 1;
  let height = 1;
  let dpr = 1;
  let mode = "ready";
  let artReady = false;
  let frame = 0;
  let previousTime = 0;
  let elapsed = 0;
  let player;
  let platforms = [];
  let enemies = [];
  let hazards = [];
  let bananas = [];
  let effects = [];
  let cameraY = 0;
  let worldTop = 0;
  let peakY = 0;
  let frags = 0;
  let bananaCount = 0;
  let finalScore = 0;
  let lastWasRecord = false;
  let trailTimer = 0;
  let touchDirection = null;
  let nativeFullscreenRequested = false;

  bestNode.textContent = String(best);
  startButton.disabled = true;

  const image = (src) => new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = src;
  });

  function cropSprites(atlas) {
    if (!atlas) return;
    const cellWidth = atlas.naturalWidth / 4;
    const cellHeight = atlas.naturalHeight / 3;

    for (let index = 0; index < 12; index += 1) {
      const sx = (index % 4) * cellWidth;
      const sy = Math.floor(index / 4) * cellHeight;
      const tile = document.createElement("canvas");
      tile.width = Math.ceil(cellWidth);
      tile.height = Math.ceil(cellHeight);
      const tileCtx = tile.getContext("2d", { willReadFrequently: true });
      tileCtx.imageSmoothingEnabled = false;
      tileCtx.drawImage(atlas, sx, sy, cellWidth, cellHeight, 0, 0, tile.width, tile.height);
      const pixels = tileCtx.getImageData(0, 0, tile.width, tile.height).data;
      let minX = tile.width;
      let minY = tile.height;
      let maxX = -1;
      let maxY = -1;

      for (let y = 0; y < tile.height; y += 1) {
        for (let x = 0; x < tile.width; x += 1) {
          if (pixels[(y * tile.width + x) * 4 + 3] > 18) {
            minX = Math.min(minX, x);
            minY = Math.min(minY, y);
            maxX = Math.max(maxX, x);
            maxY = Math.max(maxY, y);
          }
        }
      }

      sprites[index] = maxX >= minX && maxY >= minY
        ? { image: atlas, sx: sx + minX, sy: sy + minY, sw: maxX - minX + 1, sh: maxY - minY + 1 }
        : null;
    }
  }

  function spriteSize(sprite, targetWidth) {
    return sprite ? targetWidth * sprite.sh / sprite.sw : targetWidth;
  }

  function drawSprite(index, x, worldY, targetWidth, anchor = "center", targetHeight = null) {
    const sprite = sprites[index];
    if (!sprite) return false;
    const drawHeight = targetHeight || spriteSize(sprite, targetWidth);
    const screenY = height - (worldY - cameraY);
    const drawY = anchor === "platform" ? screenY : screenY - drawHeight / 2;
    ctx.drawImage(sprite.image, sprite.sx, sprite.sy, sprite.sw, sprite.sh,
      x - targetWidth / 2, drawY, targetWidth, drawHeight);
    return true;
  }

  function cacheBackground() {
    backgroundCache = null;
    backgroundTileHeight = 0;
    if (!art.background || !width || !height) return;

    const pixelWidth = Math.max(1, Math.round(width * dpr));
    const pixelHeight = Math.max(1, Math.round(width * art.background.naturalHeight
      / art.background.naturalWidth * dpr));
    const cache = document.createElement("canvas");
    cache.width = pixelWidth;
    cache.height = pixelHeight;
    const cacheCtx = cache.getContext("2d", { alpha: false });
    cacheCtx.imageSmoothingEnabled = false;
    cacheCtx.drawImage(art.background, 0, 0, pixelWidth, pixelHeight);
    backgroundCache = cache;
    backgroundTileHeight = pixelHeight / dpr;
  }

  function drawBackdrop() {
    if (backgroundCache) {
      const offset = (cameraY * .16) % backgroundTileHeight;
      for (let y = -offset; y < height; y += backgroundTileHeight) {
        ctx.drawImage(backgroundCache, 0, y, width, backgroundTileHeight);
      }
      ctx.fillStyle = "rgba(8, 14, 25, .1)";
      ctx.fillRect(0, 0, width, height);
    } else {
      ctx.fillStyle = "#111a2c";
      ctx.fillRect(0, 0, width, height);
    }

    ctx.globalAlpha = 1;
  }

  function worldToScreen(worldY) {
    return height - (worldY - cameraY);
  }

  function visualScale() {
    return width <= 520 ? .68 : 1;
  }

  function bananaScale() {
    return width <= 520 ? .82 : 1;
  }

  function enemyWidth() {
    return Math.max(47, Math.min(61, width * .15)) * visualScale();
  }

  function addPlatform(y, x, kind = "normal") {
    const spriteIndex = kind === "moving" ? 1 : kind === "break" ? 2 : kind === "spring" ? 3 : 0;
    const platformWidth = Math.max(88, Math.min(116, width * .23)) * visualScale();
    platforms.push({
      x,
      originX: x,
      y,
      width: platformWidth,
      height: Math.max(18, platformWidth * .32),
      kind,
      spriteIndex,
      phase: Math.random() * Math.PI * 2,
      range: Math.min(42, width * .1),
      broken: false,
    });
  }

  function platformGap() {
    // Keep the vertical rhythm inside one jump arc, with enough breathing room
    // that the next platform is never hidden directly behind the previous one.
    return 108 + Math.random() * 38;
  }

  function choosePlatformX(previousX, gap) {
    const minX = width * .14;
    const maxX = width * .86;
    const jumpSpeed = 720;
    const gravity = 1240;
    const discriminant = Math.max(0, jumpSpeed * jumpSpeed - 2 * gravity * gap);
    const landingTime = (jumpSpeed + Math.sqrt(discriminant)) / gravity;
    const horizontalSpeed = Math.min(440, width * .62);
    const maxOffset = Math.max(52, Math.min(width * .35, horizontalSpeed * landingTime * .72));
    const minOffset = Math.min(maxOffset * .58, Math.max(28, width * .08));
    const candidates = [];

    for (let attempt = 0; attempt < 18; attempt += 1) {
      const direction = Math.random() < .5 ? -1 : 1;
      const offset = minOffset + Math.random() * Math.max(0, maxOffset - minOffset);
      const candidate = previousX + direction * offset;
      if (candidate >= minX && candidate <= maxX) candidates.push(candidate);
    }

    if (candidates.length) return candidates[Math.floor(Math.random() * candidates.length)];

    // Near an edge, keep the move reachable while still changing lanes.
    let direction = previousX > (minX + maxX) / 2 ? -1 : 1;
    let available = direction < 0 ? previousX - minX : maxX - previousX;
    if (available < minOffset) {
      direction *= -1;
      available = direction < 0 ? previousX - minX : maxX - previousX;
    }
    const offset = Math.min(maxOffset, Math.max(0, available));
    return Math.max(minX, Math.min(maxX, previousX + direction * offset));
  }

  function selectPlatformKind() {
    const roll = Math.random();
    if (roll < .12) return "break";
    if (roll < .29) return "moving";
    if (roll < .36) return "spring";
    return "normal";
  }

  function buildGame() {
    const heroSprite = art.hero || sprites[8];
    const heroHeight = Math.min(88, Math.max(70, width * .18)) * visualScale();
    const heroWidth = heroHeight * (heroSprite ? heroSprite.sw / heroSprite.sh : .67);
    const firstY = 86;
    platforms = [];
    enemies = [];
    hazards = [];
    bananas = [];
    effects = [];
    cameraY = 0;
    worldTop = firstY;
    peakY = firstY + heroHeight / 2;
    frags = 0;
    bananaCount = 0;
    finalScore = 0;
    elapsed = 0;
    trailTimer = 0;
    held.left = false;
    held.right = false;

    addPlatform(firstY, width * .5, "normal");
    let nextY = firstY;
    let lastX = width * .5;
    while (nextY < height + 320) {
      const gap = platformGap();
      nextY += gap;
      lastX = choosePlatformX(lastX, gap);
      addPlatform(nextY, lastX, selectPlatformKind());
      worldTop = nextY;
    }
    player = {
      x: width * .5,
      y: firstY + heroHeight / 2,
      vx: 0,
      vy: 0,
      width: heroWidth,
      height: heroHeight,
    };

    enemies.push({ x: width * .73, baseX: width * .73, y: 440, phase: Math.random() * 6, dead: false });
    bananas.push({ x: width * .37, y: 320, taken: false, phase: Math.random() * 6 });
    extendWorld();
    updateHud();
    draw();
  }

  function extendWorld() {
    while (worldTop < cameraY + height + 280) {
      const gap = platformGap();
      const y = worldTop + gap;
      const prior = platforms[platforms.length - 1];
      const lastX = prior ? prior.x : width / 2;
      const nextX = choosePlatformX(lastX, gap);
      addPlatform(y, nextX, selectPlatformKind());
      worldTop = y;
    }

    if (!enemies.length || worldTop - enemies[enemies.length - 1].y > 490) {
      const enemyX = width * (.18 + Math.random() * .64);
      enemies.push({
        x: enemyX,
        baseX: enemyX,
        y: worldTop - 100,
        phase: Math.random() * Math.PI * 2,
        dead: false,
      });
    }
    if (!hazards.length || worldTop - hazards[hazards.length - 1].y > 430) {
      hazards.push({
        x: width * (.13 + Math.random() * .74),
        y: worldTop + 90,
        speed: 100 + Math.random() * 48 + Math.min(75, cameraY * .012),
        spriteIndex: Math.random() < .68 ? 5 : 6,
        size: Math.max(38, Math.min(52, width * .12)) * visualScale(),
      });
    }
    if (!bananas.length || worldTop - bananas[bananas.length - 1].y > 385) {
      bananas.push({ x: width * (.15 + Math.random() * .7), y: worldTop - 45, taken: false, phase: Math.random() * Math.PI * 2 });
    }
  }

  function updateHud() {
    const heightPoints = Math.max(0, Math.floor((peakY - 86) / 11));
    const score = heightPoints + frags * 30 + bananaCount * 12;
    scoreNode.textContent = String(mode === "over" ? finalScore : score);
    bestNode.textContent = String(Math.max(best, score));
  }

  function setOverlay(state) {
    if (state === "running") {
      overlay.classList.add("is-hidden");
      return;
    }
    overlay.classList.remove("is-hidden");
    if (state === "ready") {
      kicker.textContent = "СЕССИЯ ТОЛЬКО ДЛЯ АДМИНА";
      title.textContent = "На старт, прыгун!";
      copy.textContent = "Лови платформы и набирай высоту. Приземляйся на шинных гремлинов сверху, чтобы получить фраг. Одно столкновение — и заезд окончен.";
      startButton.innerHTML = 'Начать прыжок <span aria-hidden="true">↗</span>';
    } else {
      kicker.textContent = "ФИНИШНЫЙ ФЛАГ";
      title.textContent = "Прыжок окончен";
      copy.textContent = `Счёт — ${finalScore}, фрагов — ${frags}. ${lastWasRecord ? "Новый личный рекорд!" : "Попробуй забраться выше."}`;
      startButton.innerHTML = 'Ещё один прыжок <span aria-hidden="true">↗</span>';
    }
  }

  function startGame() {
    if (!artReady) return;
    cancelAnimationFrame(frame);
    buildGame();
    mode = "running";
    player.vy = 720;
    setOverlay("running");
    previousTime = performance.now();
    frame = requestAnimationFrame(loop);
    canvas.focus({ preventScroll: true });
  }

  function endGame() {
    if (mode !== "running") return;
    mode = "over";
    const heightPoints = Math.max(0, Math.floor((peakY - 86) / 11));
    finalScore = heightPoints + frags * 30 + bananaCount * 12;
    lastWasRecord = finalScore > best;
    if (finalScore > best) {
      best = finalScore;
      try { localStorage.setItem(bestStorageKey, String(best)); } catch (error) { /* Keep the run playable without storage. */ }
    }
    updateHud();
    setOverlay("over");
    draw();
  }

  function overlapRect(ax, ay, aw, ah, bx, by, bw, bh) {
    return Math.abs(ax - bx) < (aw + bw) / 2 && Math.abs(ay - by) < (ah + bh) / 2;
  }

  function collideWithEnemy(previousFeet, currentFeet) {
    for (const enemy of enemies) {
      if (enemy.dead) continue;
      const targetEnemyWidth = enemyWidth();
      const enemyHeight = spriteSize(sprites[4], targetEnemyWidth);
      const enemyY = enemy.y + Math.sin(elapsed * 4 + enemy.phase) * 4;
      const enemyTop = enemyY + enemyHeight / 2;
      const closeX = Math.abs(player.x - enemy.x) < (player.width * .64 + 23 * visualScale());
      const crossedTop = previousFeet >= enemyTop && currentFeet <= enemyTop;
      if (player.vy < 0 && closeX && crossedTop) {
        enemy.dead = true;
        frags += 1;
        player.y = enemyTop + player.height / 2;
        player.vy = 810;
        effects.push({ index: 9, x: enemy.x, y: enemyTop, age: 0, duration: .42, size: 56 * visualScale() });
        effects.push({ index: 10, x: enemy.x, y: enemyTop, age: 0, duration: .28, size: 42 * visualScale() });
        return true;
      }
      if (overlapRect(player.x, player.y, player.width * .62, player.height * .72, enemy.x, enemyY, targetEnemyWidth * .82, enemyHeight * .72)) {
        endGame();
        return true;
      }
    }
    return false;
  }

  function update(dt) {
    elapsed += dt;
    const direction = Number(held.right) - Number(held.left);
    const targetVx = direction * Math.min(440, width * .62);
    player.vx += (targetVx - player.vx) * Math.min(1, 10 * dt);
    player.x += player.vx * dt;
    const halfPlayer = player.width / 2;
    if (player.x < -halfPlayer) player.x = width + halfPlayer;
    if (player.x > width + halfPlayer) player.x = -halfPlayer;

    const previousFeet = player.y - player.height / 2;
    player.vy -= 1240 * dt;
    player.y += player.vy * dt;
    const currentFeet = player.y - player.height / 2;
    peakY = Math.max(peakY, player.y);

    for (const platform of platforms) {
      if (platform.kind === "moving" && !platform.broken) {
        platform.x = Math.max(platform.width * .55, Math.min(width - platform.width * .55,
          platform.originX + Math.sin(elapsed * 1.65 + platform.phase) * platform.range));
      }
    }

    for (const enemy of enemies) {
      enemy.x = Math.max(34, Math.min(width - 34,
        enemy.baseX + Math.sin(elapsed * 1.25 + enemy.phase) * Math.min(54, width * .14)));
    }

    collideWithEnemy(previousFeet, currentFeet);
    if (mode !== "running") return;

    if (player.vy < 0) {
      for (const platform of platforms) {
        if (platform.broken || previousFeet < platform.y || currentFeet > platform.y) continue;
        if (Math.abs(player.x - platform.x) > platform.width * .48 + player.width * .32) continue;
        if (platform.kind === "break") platform.broken = true;
        // Snap the sprite's feet to the exact contact plane; otherwise one frame of
        // downward travel makes the character visibly sink into the platform.
        player.y = platform.y + player.height / 2;
        player.vy = platform.kind === "spring" ? 930 : 720;
        if (platform.kind === "spring") {
          effects.push({ index: 10, x: player.x, y: platform.y, age: 0, duration: .3, size: 46 * visualScale() });
        }
        break;
      }
    }

    for (const banana of bananas) {
      if (banana.taken) continue;
      const bobY = banana.y + Math.sin(elapsed * 3 + banana.phase) * 7;
      if (overlapRect(player.x, player.y, player.width * .7, player.height * .72, banana.x, bobY,
        28 * bananaScale(), 30 * bananaScale())) {
        banana.taken = true;
        bananaCount += 1;
      }
    }

    for (const hazard of hazards) {
      hazard.y -= hazard.speed * dt;
      if (overlapRect(player.x, player.y, player.width * .57, player.height * .66,
        hazard.x, hazard.y, hazard.size * .72, hazard.size * .72)) {
        endGame();
        return;
      }
    }

    effects.forEach((effect) => { effect.age += dt; });
    effects = effects.filter((effect) => effect.age < effect.duration && effect.y > cameraY - 140);
    if (player.vy > 260 && elapsed - trailTimer > .13) {
      effects.push({ index: 11, x: player.x, y: player.y - player.height * .38, age: 0, duration: .2, size: 46 * visualScale() });
      trailTimer = elapsed;
    }

    if (player.y > cameraY + height * .27) cameraY = player.y - height * .27;
    extendWorld();
    platforms = platforms.filter((platform) => platform.y > cameraY - 160);
    enemies = enemies.filter((enemy) => enemy.y > cameraY - 130 && !enemy.dead);
    hazards = hazards.filter((hazard) => hazard.y > cameraY - 180);
    bananas = bananas.filter((banana) => banana.y > cameraY - 120 && !banana.taken);

    if (player.y < cameraY - player.height) {
      endGame();
      return;
    }
    updateHud();
  }

  function draw() {
    if (!ctx) return;
    drawBackdrop();

    for (const banana of bananas) {
      if (banana.taken) continue;
      const bob = Math.sin(elapsed * 3 + banana.phase) * 7;
      drawSprite(7, banana.x, banana.y + bob, Math.max(29, width * .055) * bananaScale());
    }

    for (const platform of platforms) {
      if (platform.broken) continue;
      drawSprite(platform.spriteIndex, platform.x, platform.y, platform.width, "platform", platform.height);
    }

    for (const enemy of enemies) {
      if (enemy.dead) continue;
      const bobY = enemy.y + Math.sin(elapsed * 4 + enemy.phase) * 4;
      drawSprite(4, enemy.x, bobY, enemyWidth());
    }

    for (const hazard of hazards) drawSprite(hazard.spriteIndex, hazard.x, hazard.y, hazard.size);

    for (const effect of effects) {
      ctx.save();
      ctx.globalAlpha = Math.max(0, 1 - effect.age / effect.duration);
      drawSprite(effect.index, effect.x, effect.y, effect.size);
      ctx.restore();
    }

    if (player) {
      const screenY = worldToScreen(player.y);
      ctx.save();
      ctx.translate(player.x, screenY);
      ctx.rotate(Math.max(-.08, Math.min(.08, -player.vx / Math.max(1, width) * .1)));
      const heroSprite = art.hero || sprites[8];
      if (heroSprite) {
        ctx.drawImage(heroSprite.image, heroSprite.sx, heroSprite.sy, heroSprite.sw, heroSprite.sh,
          -player.width / 2, -player.height / 2, player.width, player.height);
      } else {
        ctx.fillStyle = "#f4d43e";
        ctx.beginPath();
        ctx.ellipse(0, 0, player.width * .43, player.height * .47, 0, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    }

    if (mode === "running") {
      const progress = Math.max(0, Math.floor((peakY - 86) / 11));
      ctx.save();
      ctx.fillStyle = "rgba(249, 251, 255, .72)";
      ctx.font = "800 11px system-ui, sans-serif";
      ctx.textAlign = "right";
      ctx.fillText(`${progress} м`, width - 14, 22);
      ctx.restore();
    }
  }

  function loop(now) {
    if (mode !== "running") return;
    const dt = Math.min(.034, Math.max(.001, (now - previousTime) / 1000));
    previousTime = now;
    update(dt);
    draw();
    if (mode === "running") frame = requestAnimationFrame(loop);
  }

  function resize() {
    const bounds = wrap.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const previousWidth = width;
    const previousHeight = height;
    width = bounds.width;
    height = bounds.height;
    dpr = Math.min(1.5, window.devicePixelRatio || 1);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.imageSmoothingEnabled = false;
    if (!artReady) {
      drawBackdrop();
      return;
    }
    cacheBackground();
    if (player && previousWidth > 1 && previousHeight > 1) {
      const scaleX = width / previousWidth;
      // Keep the playfield's world geometry proportional when its visible height
      // changes (e.g. entering fullscreen). The taller viewport simply reveals
      // more of the level instead of stretching sprites and platforms vertically.
      const scaleY = scaleX;
      player.x *= scaleX;
      player.y *= scaleY;
      player.vx *= scaleX;
      player.vy *= scaleY;
      player.width *= scaleX;
      player.height *= scaleY;
      cameraY *= scaleY;
      peakY *= scaleY;
      worldTop *= scaleY;
      platforms.forEach((platform) => {
        platform.x *= scaleX;
        platform.originX *= scaleX;
        platform.y *= scaleY;
        platform.width *= scaleX;
        platform.height *= scaleY;
        platform.range *= scaleX;
      });
      enemies.forEach((enemy) => { enemy.x *= scaleX; enemy.baseX *= scaleX; enemy.y *= scaleY; });
      hazards.forEach((hazard) => { hazard.x *= scaleX; hazard.y *= scaleY; hazard.size *= scaleX; hazard.speed *= scaleY; });
      bananas.forEach((banana) => { banana.x *= scaleX; banana.y *= scaleY; });
      draw();
    } else {
      buildGame();
    }
  }

  function setDirection(direction, value) {
    held[direction] = value;
  }

  function clearDirections() {
    setDirection("left", false);
    setDirection("right", false);
  }

  function isGameFullscreen() {
    return machine.classList.contains("is-fullscreen")
      || document.fullscreenElement === machine
      || document.webkitFullscreenElement === machine;
  }

  function updateFullscreenButton() {
    const active = isGameFullscreen();
    fullscreenButton.setAttribute("aria-pressed", String(active));
    fullscreenButton.setAttribute("aria-label", active ? "Выйти из полноэкранного режима" : "На весь экран");
    fullscreenButton.title = active ? "Выйти из полноэкранного режима (Esc)" : "На весь экран";
  }

  function handleFullscreenChange() {
    const nativeActive = document.fullscreenElement === machine
      || document.webkitFullscreenElement === machine;
    if (nativeActive) {
      machine.classList.add("is-fullscreen");
      document.body.classList.add("doodle-fullscreen-active");
    } else if (nativeFullscreenRequested) {
      nativeFullscreenRequested = false;
      machine.classList.remove("is-fullscreen");
      document.body.classList.remove("doodle-fullscreen-active");
    }
    updateFullscreenButton();
    requestAnimationFrame(resize);
  }

  async function toggleFullscreen() {
    if (isGameFullscreen()) {
      const exit = document.exitFullscreen || document.webkitExitFullscreen;
      machine.classList.remove("is-fullscreen");
      document.body.classList.remove("doodle-fullscreen-active");
      nativeFullscreenRequested = false;
      if (exit && (document.fullscreenElement === machine || document.webkitFullscreenElement === machine)) {
        try { await exit.call(document); } catch (error) { /* The CSS fullscreen fallback is already closed. */ }
      }
      updateFullscreenButton();
      requestAnimationFrame(resize);
      return;
    }

    machine.classList.add("is-fullscreen");
    document.body.classList.add("doodle-fullscreen-active");
    updateFullscreenButton();
    resize();

    const request = machine.requestFullscreen || machine.webkitRequestFullscreen;
    if (request) {
      nativeFullscreenRequested = true;
      try {
        await request.call(machine);
      } catch (error) {
        // Keep the fixed-position fallback for browsers that deny native fullscreen.
        nativeFullscreenRequested = false;
      }
    }
    requestAnimationFrame(resize);
  }

  document.addEventListener("keydown", (event) => {
    const key = event.key.toLowerCase();
    if (key === "escape" && isGameFullscreen() && !document.fullscreenElement && !document.webkitFullscreenElement) {
      event.preventDefault();
      toggleFullscreen();
      return;
    }
    if (["arrowleft", "arrowright", " "].includes(key)) event.preventDefault();
    if (key === "arrowleft" || key === "a") setDirection("left", true);
    if (key === "arrowright" || key === "d") setDirection("right", true);
    if (key === " " && mode !== "running") startGame();
  });
  document.addEventListener("keyup", (event) => {
    const key = event.key.toLowerCase();
    if (key === "arrowleft" || key === "a") setDirection("left", false);
    if (key === "arrowright" || key === "d") setDirection("right", false);
  });
  window.addEventListener("blur", clearDirections);
  startButton.addEventListener("click", startGame);
  fullscreenButton.addEventListener("click", toggleFullscreen);
  document.addEventListener("fullscreenchange", handleFullscreenChange);
  document.addEventListener("webkitfullscreenchange", handleFullscreenChange);

  canvas.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse") return;
    event.preventDefault();
    const bounds = canvas.getBoundingClientRect();
    touchDirection = event.clientX < bounds.left + bounds.width / 2 ? "left" : "right";
    setDirection(touchDirection, true);
    canvas.setPointerCapture?.(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (touchDirection === null || event.pointerType === "mouse") return;
    const bounds = canvas.getBoundingClientRect();
    const direction = event.clientX < bounds.left + bounds.width / 2 ? "left" : "right";
    if (direction === touchDirection) return;
    setDirection(touchDirection, false);
    touchDirection = direction;
    setDirection(touchDirection, true);
  });
  ["pointerup", "pointercancel", "lostpointercapture"].forEach((type) => {
    canvas.addEventListener(type, () => { touchDirection = null; clearDirections(); });
  });

  Promise.all([
    image(canvas.dataset.atlasSrc),
    image(canvas.dataset.heroSrc),
    image(canvas.dataset.backgroundSrc),
  ]).then(([atlas, hero, background]) => {
    art.background = background;
    art.hero = hero
      ? { image: hero, sx: 0, sy: 0, sw: hero.naturalWidth, sh: hero.naturalHeight }
      : null;
    cropSprites(atlas);
    artReady = true;
    startButton.disabled = false;
    resize();
    setOverlay("ready");
  });

  if ("ResizeObserver" in window) {
    new ResizeObserver(resize).observe(wrap);
  } else {
    window.addEventListener("resize", resize);
  }
})();
