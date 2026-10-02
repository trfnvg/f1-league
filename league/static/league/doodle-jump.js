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
  let startY = 86;
  let peakY = 0;
  let frags = 0;
  let bananaCount = 0;
  let finalScore = 0;
  let lastWasRecord = false;
  let trailTimer = 0;
  let touchDirection = null;
  let nativeFullscreenRequested = false;
  let facing = 1;

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

  function currentHeroSprite() {
    const frames = art.heroFrames;
    const fallback = (frames && frames[1]) || sprites[8];
    if (!frames || frames.length < 4 || !player) return fallback;

    // The generated sheet follows the jump arc: crouch, takeoff, peak, descent.
    // Mapping from velocity keeps the pose synced to the actual physics instead
    // of playing a separate animation that could drift away from a landing.
    const velocity = player.vy;
    const frameIndex = velocity > 560 ? 1 : velocity > 100 ? 2 : velocity > -180 ? 3 : 0;
    return frames[frameIndex] || fallback;
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

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function drawCloud(worldY, x, scale = 1, alpha = 1) {
    const screenY = height - (worldY - cameraY);
    if (screenY < -90 || screenY > height + 90) return;
    const drift = Math.sin(elapsed * .18 + worldY * .002) * 12;
    const cloudWidth = Math.max(86, width * .2) * scale;
    const cloudHeight = Math.max(22, height * .045) * scale;
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.fillStyle = "#eff8ff";
    ctx.beginPath();
    ctx.ellipse(x + drift - cloudWidth * .24, screenY + cloudHeight * .12, cloudWidth * .25, cloudHeight * .32, 0, 0, Math.PI * 2);
    ctx.ellipse(x + drift, screenY - cloudHeight * .12, cloudWidth * .34, cloudHeight * .48, 0, 0, Math.PI * 2);
    ctx.ellipse(x + drift + cloudWidth * .26, screenY + cloudHeight * .08, cloudWidth * .28, cloudHeight * .36, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillRect(x + drift - cloudWidth * .42, screenY + cloudHeight * .02, cloudWidth * .84, cloudHeight * .34);
    ctx.restore();
  }

  function drawBackdrop() {
    // The world climbs through a single background journey instead of looping
    // the city texture: pit lane at the start, then clouds, then open sky.
    const skyProgress = clamp(cameraY / 1650, 0, 1);
    const sky = ctx.createLinearGradient(0, 0, 0, height);
    const topRed = Math.round(22 + (137 - 22) * skyProgress);
    const topGreen = Math.round(53 + (204 - 53) * skyProgress);
    const topBlue = Math.round(91 + (247 - 91) * skyProgress);
    const bottomRed = Math.round(72 + (220 - 72) * skyProgress);
    const bottomGreen = Math.round(139 + (241 - 139) * skyProgress);
    const bottomBlue = Math.round(190 + (255 - 190) * skyProgress);
    sky.addColorStop(0, `rgb(${topRed}, ${topGreen}, ${topBlue})`);
    sky.addColorStop(1, `rgb(${bottomRed}, ${bottomGreen}, ${bottomBlue})`);
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, width, height);

    if (backgroundCache && backgroundTileHeight) {
      const cityY = height + cameraY * .86 - backgroundTileHeight;
      const cityFade = clamp(1 - Math.max(0, cameraY - 180) / 760, 0, 1);
      ctx.save();
      ctx.globalAlpha = cityFade;
      ctx.drawImage(backgroundCache, 0, cityY, width, backgroundTileHeight);
      ctx.restore();
    }

    // Clouds are anchored to world heights, so they naturally enter the
    // viewport as the player climbs rather than sliding in a repeating loop.
    drawCloud(760, width * .2, .9, .82);
    drawCloud(930, width * .76, 1.15, .9);
    drawCloud(1160, width * .42, .72, .72);
    drawCloud(1410, width * .82, 1.35, .86);
    drawCloud(1690, width * .16, 1.05, .92);

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
    const platform = {
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
    };
    platforms.push(platform);
    return platform;
  }

  function addBananaBetween(lower, upper) {
    if (!lower || !upper) return;

    // Keep collectibles in the middle of the jump corridor. The gap is always
    // larger than the banana hitbox, so it can never be rendered inside either
    // platform (even while it bobs up and down).
    const gap = upper.y - lower.y;
    const laneCenter = lower.x + (upper.x - lower.x) * .5;
    const drift = (Math.random() - .5) * Math.min(34, width * .07);
    bananas.push({
      x: Math.max(width * .16, Math.min(width * .84, laneCenter + drift)),
      y: lower.y + gap * (.46 + Math.random() * .08),
      taken: false,
      phase: Math.random() * Math.PI * 2,
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
    const heroSprite = (art.heroFrames && art.heroFrames[1]) || sprites[8];
    const heroHeight = Math.min(88, Math.max(70, width * .18)) * visualScale();
    const heroWidth = heroHeight * (heroSprite ? heroSprite.sw / heroSprite.sh : .67);
    const firstY = Math.max(86, Math.min(118, height * .14));
    platforms = [];
    enemies = [];
    hazards = [];
    bananas = [];
    effects = [];
    cameraY = 0;
    startY = firstY;
    worldTop = firstY;
    peakY = firstY + heroHeight / 2;
    frags = 0;
    bananaCount = 0;
    finalScore = 0;
    elapsed = 0;
    trailTimer = 0;
    held.left = false;
    held.right = false;
    facing = 1;

    let previousPlatform = addPlatform(firstY, width * .5, "normal");
    let nextY = firstY;
    let lastX = width * .5;
    while (nextY < height + 320) {
      const gap = platformGap();
      nextY += gap;
      lastX = choosePlatformX(lastX, gap);
      const nextPlatform = addPlatform(nextY, lastX, selectPlatformKind());
      addBananaBetween(previousPlatform, nextPlatform);
      previousPlatform = nextPlatform;
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
      const nextPlatform = addPlatform(y, nextX, selectPlatformKind());
      addBananaBetween(prior, nextPlatform);
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
  }

  function updateHud() {
    const heightPoints = Math.max(0, Math.floor((peakY - startY) / 11));
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
    const heightPoints = Math.max(0, Math.floor((peakY - startY) / 11));
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
        // A platform that has already slipped below the visible playfield must
        // not catch the player off-screen. This prevents invisible landings at
        // the bottom edge after the camera has moved upward.
        if (platform.y < cameraY + 4) continue;
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

    // Keep the racer in the lower-middle band: enough space remains above for
    // incoming platforms, while the player never hugs the bottom edge.
    if (player.y > cameraY + height * .42) cameraY = player.y - height * .42;
    extendWorld();
    platforms = platforms.filter((platform) => platform.y > cameraY - 160);
    enemies = enemies.filter((enemy) => enemy.y > cameraY - 130 && !enemy.dead);
    hazards = hazards.filter((hazard) => hazard.y > cameraY - 180);
    bananas = bananas.filter((banana) => banana.y > cameraY - 120 && !banana.taken);

    if (player.y + player.height / 2 < cameraY - 6) {
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
      ctx.scale(facing, 1);
      const heroSprite = currentHeroSprite();
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
    if (value) facing = direction === "left" ? -1 : 1;
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
    if (["arrowleft", "arrowright", " ", "a", "d", "ф", "в"].includes(key)) event.preventDefault();
    if (key === "arrowleft" || key === "a" || key === "ф") setDirection("left", true);
    if (key === "arrowright" || key === "d" || key === "в") setDirection("right", true);
    if (key === " " && mode !== "running") startGame();
  });
  document.addEventListener("keyup", (event) => {
    const key = event.key.toLowerCase();
    if (key === "arrowleft" || key === "a" || key === "ф") setDirection("left", false);
    if (key === "arrowright" || key === "d" || key === "в") setDirection("right", false);
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
    image(canvas.dataset.heroFrame1Src),
    image(canvas.dataset.heroFrame2Src),
    image(canvas.dataset.heroFrame3Src),
    image(canvas.dataset.heroFrame4Src),
    image(canvas.dataset.backgroundSrc),
  ]).then(([atlas, frame1, frame2, frame3, frame4, background]) => {
    art.background = background;
    const heroFrames = [frame1, frame2, frame3, frame4];
    art.heroFrames = heroFrames.every(Boolean)
      ? heroFrames.map((imageAsset) => ({
        image: imageAsset,
        sx: 0,
        sy: 0,
        sw: imageAsset.naturalWidth,
        sh: imageAsset.naturalHeight,
      }))
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
