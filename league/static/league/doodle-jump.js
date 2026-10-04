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
  const levelNode = document.getElementById("doodle-level");
  const levelNameNode = document.getElementById("doodle-level-name");
  const fullscreenButton = document.getElementById("doodle-fullscreen-toggle");
  const leaderboardNode = document.getElementById("doodle-leaderboard-list");
  const totalAttemptsNode = document.getElementById("doodle-total-attempts");
  const csrfToken = document.querySelector("#doodle-csrf-form [name=csrfmiddlewaretoken]")?.value || "";
  const bestStorageKey = "f1-doodle-gp-best-v1";
  const art = {};
  const held = { left: false, right: false };
  const sprites = [];
  let backgroundCaches = [];
  // The same portrait tile is repeated forever. Sector names change for flavour,
  // while the score and route never have a final platform.
  const levelWorldHeight = 2400;
  const backgroundOverscan = 1.08;
  const backgroundParallax = .34;
  const levels = [
    "Ворота завода",
    "Служебный холл",
    "Моторный цех",
    "Аэродинамический тоннель",
    "Цех карбона",
    "Сборочная линия",
    "Робототехника",
    "Крыша комплекса",
    "Симулятор",
    "Хранилище руля",
  ];

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
  let powerups = [];
  let villains = [];
  let villainShots = [];
  let effects = [];
  let cameraY = 0;
  let worldTop = 0;
  let startY = 86;
  let peakY = 0;
  let frags = 0;
  let finalScore = 0;
  let levelIndex = 0;
  let lastWasRecord = false;
  let trailTimer = 0;
  let touchDirection = null;
  let nativeFullscreenRequested = false;
  let facing = 1;
  let invulnerableTimer = 0;
  let rocketTimer = 0;
  let jetpackTimer = 0;
  let attemptId = null;
  let scoreSubmitted = false;
  let pendingFinish = false;

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

  function splitHeroSheet(sheet) {
    if (!sheet) return [];
    const frameWidth = Math.ceil(sheet.naturalWidth / 4);
    const frameHeight = sheet.naturalHeight;
    const frames = [];

    for (let frameIndex = 0; frameIndex < 4; frameIndex += 1) {
      const tile = document.createElement("canvas");
      tile.width = frameWidth;
      tile.height = frameHeight;
      const tileCtx = tile.getContext("2d", { willReadFrequently: true });
      tileCtx.imageSmoothingEnabled = false;
      tileCtx.drawImage(sheet, frameIndex * sheet.naturalWidth / 4, 0,
        sheet.naturalWidth / 4, frameHeight, 0, 0, frameWidth, frameHeight);

      // Keep only the largest connected alpha component in each panel. The
      // generated sheet has transparent gaps between poses, but this guard
      // prevents a stray edge pixel from the neighboring pose becoming a
      // black artifact in the game.
      const imageData = tileCtx.getImageData(0, 0, frameWidth, frameHeight);
      const pixels = imageData.data;
      const seen = new Uint8Array(frameWidth * frameHeight);
      let largestComponent = null;
      for (let y = 0; y < frameHeight; y += 1) {
        for (let x = 0; x < frameWidth; x += 1) {
          const start = y * frameWidth + x;
          if (seen[start] || pixels[start * 4 + 3] <= 18) continue;
          const stack = [start];
          const component = [];
          seen[start] = 1;
          while (stack.length) {
            const position = stack.pop();
            const pointX = position % frameWidth;
            const pointY = Math.floor(position / frameWidth);
            component.push(position);
            for (let offsetY = -1; offsetY <= 1; offsetY += 1) {
              for (let offsetX = -1; offsetX <= 1; offsetX += 1) {
                if (!offsetX && !offsetY) continue;
                const nextX = pointX + offsetX;
                const nextY = pointY + offsetY;
                if (nextX < 0 || nextX >= frameWidth || nextY < 0 || nextY >= frameHeight) continue;
                const next = nextY * frameWidth + nextX;
                if (seen[next] || pixels[next * 4 + 3] <= 18) continue;
                seen[next] = 1;
                stack.push(next);
              }
            }
          }
          if (!largestComponent || component.length > largestComponent.length) largestComponent = component;
        }
      }

      if (largestComponent) {
        const cleaned = tileCtx.createImageData(frameWidth, frameHeight);
        for (const position of largestComponent) {
          const sourceOffset = position * 4;
          cleaned.data[sourceOffset] = pixels[sourceOffset];
          cleaned.data[sourceOffset + 1] = pixels[sourceOffset + 1];
          cleaned.data[sourceOffset + 2] = pixels[sourceOffset + 2];
          cleaned.data[sourceOffset + 3] = pixels[sourceOffset + 3];
        }
        tileCtx.clearRect(0, 0, frameWidth, frameHeight);
        tileCtx.putImageData(cleaned, 0, 0);
      }
      frames.push({ image: tile, sx: 0, sy: 0, sw: frameWidth, sh: frameHeight });
    }
    return frames;
  }

  function splitSpriteSheet(sheet, columns) {
    if (!sheet || !columns) return [];
    const frameWidth = Math.ceil(sheet.naturalWidth / columns);
    const frameHeight = sheet.naturalHeight;
    const frames = [];
    for (let frameIndex = 0; frameIndex < columns; frameIndex += 1) {
      const tile = document.createElement("canvas");
      tile.width = frameWidth;
      tile.height = frameHeight;
      const tileCtx = tile.getContext("2d", { willReadFrequently: true });
      tileCtx.imageSmoothingEnabled = false;
      tileCtx.drawImage(sheet, frameIndex * sheet.naturalWidth / columns, 0,
        sheet.naturalWidth / columns, frameHeight, 0, 0, frameWidth, frameHeight);
      const pixels = tileCtx.getImageData(0, 0, frameWidth, frameHeight).data;
      let minX = frameWidth;
      let minY = frameHeight;
      let maxX = -1;
      let maxY = -1;
      for (let y = 0; y < frameHeight; y += 1) {
        for (let x = 0; x < frameWidth; x += 1) {
          if (pixels[(y * frameWidth + x) * 4 + 3] <= 18) continue;
          minX = Math.min(minX, x);
          minY = Math.min(minY, y);
          maxX = Math.max(maxX, x);
          maxY = Math.max(maxY, y);
        }
      }
      frames.push(maxX >= minX && maxY >= minY
        ? { image: tile, sx: minX, sy: minY, sw: maxX - minX + 1, sh: maxY - minY + 1 }
        : null);
    }
    return frames;
  }

  function spriteSize(sprite, targetWidth) {
    return sprite ? targetWidth * sprite.sh / sprite.sw : targetWidth;
  }

  function currentHeroSprite() {
    const frames = art.heroFrames;
    if (!frames || frames.length < 4 || !player) return frames && frames[1] ? frames[1] : null;

    // The generated sheet follows the jump arc: crouch, takeoff, peak, descent.
    // Mapping from velocity keeps the pose synced to the actual physics instead
    // of playing a separate animation that could drift away from a landing.
    const velocity = player.vy;
    const frameIndex = velocity > 560 ? 1 : velocity > 100 ? 2 : velocity > -180 ? 3 : 0;
    return frames[frameIndex] || frames[1];
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

  function drawFrame(frame, x, worldY, targetWidth, anchor = "center", targetHeight = null) {
    if (!frame) return false;
    const drawHeight = targetHeight || spriteSize(frame, targetWidth);
    const screenY = height - (worldY - cameraY);
    const drawY = anchor === "platform" ? screenY : screenY - drawHeight / 2;
    ctx.drawImage(frame.image, frame.sx, frame.sy, frame.sw, frame.sh,
      x - targetWidth / 2, drawY, targetWidth, drawHeight);
    return true;
  }

  function cacheBackground() {
    backgroundCaches = [];
    const sources = art.backgroundZones && art.backgroundZones.length
      ? art.backgroundZones
      : (art.background ? [art.background] : []);
    if (!sources.length || !width || !height) return;

    const pixelWidth = Math.max(1, Math.round(width * dpr));
    backgroundCaches = sources.map((source) => {
      const cache = document.createElement("canvas");
      cache.width = Math.ceil(pixelWidth * backgroundOverscan);
      const scale = Math.max(
        cache.width / source.naturalWidth,
        (height * dpr * 1.08) / source.naturalHeight,
      );
      cache.height = Math.ceil(source.naturalHeight * scale);
      const cacheCtx = cache.getContext("2d", { alpha: false });
      cacheCtx.imageSmoothingEnabled = false;
      const drawWidth = source.naturalWidth * scale;
      const drawHeight = source.naturalHeight * scale;
      cacheCtx.drawImage(source, (cache.width - drawWidth) / 2, 0, drawWidth, drawHeight);
      return { canvas: cache, width: cache.width / dpr, height: cache.height / dpr };
    });
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function storyProgress() {
    return Math.max(0, cameraY) / levelWorldHeight;
  }

  function drawBackgroundTile(tile, sceneIndex) {
    if (!tile || !tile.height) return;
    const swayX = Math.sin(elapsed * .2 + sceneIndex * .7) * width * .01;
    const scroll = (Math.max(0, cameraY) * backgroundParallax) % tile.height;
    let y = -scroll;

    // Draw a tile above and below the viewport so the architecture keeps
    // scrolling continuously while the camera follows the jumper upward.
    while (y < height + tile.height) {
      ctx.drawImage(tile.canvas, swayX, y, tile.width, tile.height);
      y += tile.height;
    }
  }

  function drawBackgroundScene(scene, sceneIndex, alpha = 1) {
    if (!scene) return;
    ctx.save();
    ctx.globalAlpha = alpha;
    drawBackgroundTile(scene, sceneIndex);
    ctx.restore();
  }

  function drawBackdrop() {
    if (backgroundCaches.length) {
      drawBackgroundScene(backgroundCaches[0], 0);
      ctx.fillStyle = "rgba(5, 12, 28, .16)";
      ctx.fillRect(0, 0, width, height);
    } else {
      ctx.fillStyle = "#78c8f5";
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

  function addPowerupBetween(lower, upper) {
    if (!lower || !upper || Math.random() > .085) return;
    const type = Math.random() < .55 ? "rocket" : "jetpack";
    const gap = upper.y - lower.y;
    const laneX = lower.x + (upper.x - lower.x) * (.35 + Math.random() * .3);
    powerups.push({
      type,
      x: clamp(laneX, width * .12, width * .88),
      y: lower.y + gap * (.42 + Math.random() * .16),
      size: Math.max(25, Math.min(34, width * .075)) * visualScale(),
      phase: Math.random() * Math.PI * 2,
      collected: false,
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
    const heroSprite = art.heroFrames && art.heroFrames[1];
    const heroHeight = Math.min(88, Math.max(70, width * .18)) * visualScale();
    const heroWidth = heroHeight * (heroSprite ? heroSprite.sw / heroSprite.sh : .67);
    const firstY = Math.max(86, Math.min(118, height * .14));
    platforms = [];
    enemies = [];
    hazards = [];
    powerups = [];
    villains = [];
    villainShots = [];
    effects = [];
    cameraY = 0;
    startY = firstY;
    worldTop = firstY;
    peakY = firstY + heroHeight / 2;
    frags = 0;
    finalScore = 0;
    levelIndex = 0;
    invulnerableTimer = 0;
    rocketTimer = 0;
    jetpackTimer = 0;
    attemptId = null;
    scoreSubmitted = false;
    pendingFinish = false;
    elapsed = 0;
    trailTimer = 0;
    held.left = false;
    held.right = false;
    facing = 1;

    addPlatform(firstY, width * .5, "normal");
    let nextY = firstY;
    let lastX = width * .5;
    let previousPlatform = platforms[0];
    while (nextY < height + 320) {
      const gap = platformGap();
      nextY += gap;
      lastX = choosePlatformX(lastX, gap);
      const nextPlatform = addPlatform(nextY, lastX, selectPlatformKind());
      addPowerupBetween(previousPlatform, nextPlatform);
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
    const targetWorldTop = cameraY + height + 420;
    while (worldTop < targetWorldTop) {
      const lastPlatform = platforms[platforms.length - 1];
      const lastX = lastPlatform ? lastPlatform.x : width / 2;
      const gap = platformGap();
      const y = worldTop + gap;
      const nextX = choosePlatformX(lastX, gap);
      const nextPlatform = addPlatform(y, nextX, selectPlatformKind());
      addPowerupBetween(lastPlatform, nextPlatform);
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
      const spriteIndex = Math.random() < .68 ? 5 : 6;
      const compoundRoll = Math.random();
      const compound = spriteIndex === 5
        ? (compoundRoll < .34 ? "soft" : compoundRoll < .67 ? "medium" : "hard")
        : null;
      hazards.push({
        x: width * (.13 + Math.random() * .74),
        y: worldTop + 90,
        speed: 100 + Math.random() * 48 + Math.min(75, cameraY * .012),
        spriteIndex,
        bouncy: spriteIndex === 5,
        // The atlas cells contain transparent padding and different silhouettes.
        // Keep a per-object hitbox instead of treating every falling object as
        // the same square.
        hitbox: spriteIndex === 5
          ? { width: .68, height: .58, offsetY: -.02 }
          : { width: .56, height: .72, offsetY: .06 },
        compound,
        wheelFrame: compound && art.wheelFrames ? art.wheelFrames[compound] : null,
        dead: false,
        size: Math.max(38, Math.min(52, width * .12)) * visualScale(),
      });
    }

    const lastVillain = villains[villains.length - 1];
    if ((!lastVillain || worldTop - lastVillain.y > 2500) && Math.random() < .4) {
      const villainX = width * (.22 + Math.random() * .56);
      villains.push({
        x: villainX,
        baseX: villainX,
        y: worldTop + 180,
        phase: Math.random() * Math.PI * 2,
        frame: 0,
        shotTimer: 2.2 + Math.random() * .9,
        dead: false,
      });
    }
  }

  function updateHud() {
    const heightPoints = Math.max(0, Math.floor((peakY - startY) / 11));
    const score = heightPoints + frags * 30;
    levelIndex = Math.floor(storyProgress()) % levels.length;
    scoreNode.textContent = String(mode === "over" ? finalScore : score);
    bestNode.textContent = String(Math.max(best, score));
    levelNode.textContent = String(Math.floor(storyProgress()) + 1).padStart(2, "0");
    levelNameNode.textContent = levels[levelIndex];
    levelNameNode.title = levels[levelIndex];
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
      copy.textContent = "Маршрут бесконечный: поднимайся выше, отталкивайся от платформ, собирай фраги и используй редкие бонусы. На телефоне касайся левой или правой половины поля.";
      startButton.innerHTML = 'Начать прыжок <span aria-hidden="true">↗</span>';
    } else {
      kicker.textContent = "ЗАБЕГ ЗАВЕРШЁН";
      title.textContent = "Прыжок окончен";
      copy.textContent = `Счёт — ${finalScore}, фрагов — ${frags}. ${lastWasRecord ? "Новый личный рекорд!" : "Попробуй забраться выше."}`;
      startButton.innerHTML = 'Ещё один прыжок <span aria-hidden="true">↗</span>';
    }
  }

  function postJSON(url, payload = {}) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload),
    }).then(async (response) => {
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "Не удалось сохранить результат.");
      return data;
    });
  }

  function renderLeaderboard(records) {
    if (!leaderboardNode) return;
    leaderboardNode.replaceChildren();
    if (!records || !records.length) {
      const empty = document.createElement("li");
      empty.className = "doodle-board-empty";
      empty.textContent = "Рейтинг пока пуст — первый рекорд можно поставить прямо сейчас.";
      leaderboardNode.appendChild(empty);
      return;
    }
    records.forEach((record) => {
      const row = document.createElement("li");
      if (record.is_current_user) row.classList.add("is-current-user");
      const rank = document.createElement("span");
      rank.className = "doodle-rank";
      rank.textContent = String(record.rank).padStart(2, "0");
      const name = document.createElement("strong");
      name.textContent = record.username;
      const score = document.createElement("span");
      score.className = "doodle-record-score";
      score.textContent = String(record.score);
      const attempts = document.createElement("small");
      attempts.textContent = `${record.attempts} попыток`;
      row.append(rank, name, score, attempts);
      leaderboardNode.appendChild(row);
    });
  }

  function applyLeaderboard(data) {
    if (!data) return;
    if (Array.isArray(data.records)) renderLeaderboard(data.records);
    if (totalAttemptsNode && Number.isFinite(data.total_attempts)) totalAttemptsNode.textContent = String(data.total_attempts);
  }

  function registerAttempt() {
    if (!canvas.dataset.startUrl || !csrfToken) return;
    postJSON(canvas.dataset.startUrl).then((data) => {
      attemptId = data.attempt_id || null;
      applyLeaderboard(data);
      if (pendingFinish) submitScore();
    }).catch(() => {
      // Guests can still play locally; only authenticated runs are ranked.
    });
  }

  function submitScore() {
    if (scoreSubmitted || !canvas.dataset.finishUrl) return;
    if (!attemptId) {
      pendingFinish = true;
      return;
    }
    pendingFinish = false;
    scoreSubmitted = true;
    postJSON(canvas.dataset.finishUrl, { attempt_id: attemptId, score: finalScore })
      .then(applyLeaderboard)
      .catch(() => { scoreSubmitted = false; });
  }

  function startGame() {
    if (!artReady) return;
    cancelAnimationFrame(frame);
    buildGame();
    mode = "running";
    player.vy = 720;
    registerAttempt();
    setOverlay("running");
    previousTime = performance.now();
    frame = requestAnimationFrame(loop);
    canvas.focus({ preventScroll: true });
  }

  function endGame() {
    if (mode !== "running") return;
    mode = "over";
    const heightPoints = Math.max(0, Math.floor((peakY - startY) / 11));
    finalScore = heightPoints + frags * 30;
    lastWasRecord = finalScore > best;
    if (finalScore > best) {
      best = finalScore;
      try { localStorage.setItem(bestStorageKey, String(best)); } catch (error) { /* Keep the run playable without storage. */ }
    }
    updateHud();
    setOverlay("over");
    submitScore();
    draw();
  }

  function overlapRect(ax, ay, aw, ah, bx, by, bw, bh) {
    return Math.abs(ax - bx) < (aw + bw) / 2 && Math.abs(ay - by) < (ah + bh) / 2;
  }

  function hazardHitbox(hazard) {
    const shape = hazard.hitbox || { width: .6, height: .68, offsetY: 0 };
    const width = hazard.size * shape.width;
    const visualHeight = spriteSize(hazard.wheelFrame || sprites[hazard.spriteIndex], hazard.size) || hazard.size;
    const height = visualHeight * shape.height;
    const y = hazard.y + visualHeight * shape.offsetY;
    return { x: hazard.x, y, width, height, top: y + height / 2 };
  }

  function powerupHitbox(powerup) {
    const size = powerup.size;
    return { x: powerup.x, y: powerup.y, width: size * .72, height: size * 1.2 };
  }

  function drawPowerup(powerup) {
    const screenY = worldToScreen(powerup.y + Math.sin(elapsed * 3 + powerup.phase) * 4);
    const size = powerup.size;
    const frame = art.powerupFrames && art.powerupFrames[powerup.type];
    if (frame) {
      ctx.save();
      ctx.globalAlpha = .95 + Math.sin(elapsed * 5 + powerup.phase) * .05;
      drawFrame(frame, powerup.x, powerup.y + Math.sin(elapsed * 3 + powerup.phase) * 4, size * 1.55);
      ctx.restore();
      return;
    }
    ctx.save();
    ctx.translate(Math.round(powerup.x), Math.round(screenY));
    ctx.imageSmoothingEnabled = false;
    ctx.shadowColor = powerup.type === "rocket" ? "rgba(255, 82, 103, .75)" : "rgba(142, 234, 255, .72)";
    ctx.shadowBlur = 12;
    if (powerup.type === "rocket") {
      ctx.fillStyle = "#e84e5e";
      ctx.beginPath();
      ctx.moveTo(0, -size * .62);
      ctx.lineTo(size * .38, size * .25);
      ctx.lineTo(size * .2, size * .5);
      ctx.lineTo(-size * .2, size * .5);
      ctx.lineTo(-size * .38, size * .25);
      ctx.closePath();
      ctx.fill();
      ctx.fillStyle = "#f7f0d2";
      ctx.fillRect(-size * .28, -size * .18, size * .56, size * .25);
      ctx.fillStyle = "#75e6ef";
      ctx.fillRect(-size * .14, -size * .12, size * .28, size * .12);
      ctx.fillStyle = "#ffbd4a";
      ctx.fillRect(-size * .15, size * .48, size * .3, size * .23);
      ctx.fillStyle = "#ffef9a";
      ctx.fillRect(-size * .08, size * .55, size * .16, size * .16);
    } else {
      ctx.fillStyle = "#263451";
      ctx.fillRect(-size * .35, -size * .42, size * .7, size * .84);
      ctx.fillStyle = "#8eeaff";
      ctx.fillRect(-size * .24, -size * .25, size * .48, size * .18);
      ctx.fillStyle = "#536985";
      ctx.fillRect(-size * .52, -size * .34, size * .14, size * .68);
      ctx.fillRect(size * .38, -size * .34, size * .14, size * .68);
      ctx.fillStyle = "#ffbd4a";
      ctx.fillRect(-size * .28, size * .42, size * .18, size * .25);
      ctx.fillRect(size * .1, size * .42, size * .18, size * .25);
      ctx.fillStyle = "#ff5267";
      ctx.fillRect(-size * .2, size * .64, size * .12, size * .14);
      ctx.fillRect(size * .08, size * .64, size * .12, size * .14);
    }
    ctx.restore();
  }

  function drawMountedPowerup(type) {
    const frame = art.powerupFrames && art.powerupFrames[type];
    if (!player || !frame) return;
    const targetWidth = type === "rocket" ? player.width * 1.08 : player.width * .82;
    const mountY = player.y - player.height * .52;
    ctx.save();
    ctx.globalAlpha = .98;
    drawFrame(frame, player.x, mountY, targetWidth);
    ctx.restore();
    // Add a second, phase-shifted flame layer so the generated sprite reads as
    // animated even though the sheet is a compact single-pose power-up.
    ctx.save();
    ctx.translate(Math.round(player.x), Math.round(worldToScreen(mountY - targetWidth * .46)));
    ctx.fillStyle = type === "rocket" ? "#fff29a" : "#8eeaff";
    const flicker = 2 + Math.round(Math.sin(elapsed * 22) * 2);
    if (type === "rocket") {
      ctx.fillRect(-3, 0, 6, 8 + flicker);
      ctx.fillStyle = "#ff7b3e";
      ctx.fillRect(-5, 6, 10, 4 + flicker);
    } else {
      ctx.fillRect(-targetWidth * .22, 0, 4, 8 + flicker);
      ctx.fillRect(targetWidth * .22 - 4, 0, 4, 8 + flicker);
    }
    ctx.restore();
  }

  function drawInvulnerabilityShield() {
    if (!player || invulnerableTimer <= 0) return;
    const screenY = worldToScreen(player.y);
    ctx.save();
    ctx.translate(player.x, screenY);
    ctx.strokeStyle = `rgba(142, 234, 255, ${.5 + Math.sin(elapsed * 8) * .18})`;
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.arc(0, 0, Math.max(player.width, player.height) * .62, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  function villainWidth() {
    return Math.max(54, Math.min(78, width * .17)) * visualScale();
  }

  function drawVillainShot(shot) {
    const screenY = worldToScreen(shot.y);
    const size = shot.size;
    const dirtyWheel = art.dirtyWheelFrame;
    if (dirtyWheel) {
      ctx.save();
      ctx.translate(Math.round(shot.x), Math.round(screenY));
      ctx.rotate(shot.spin);
      const dirtyHeight = spriteSize(dirtyWheel, size * 1.22);
      ctx.drawImage(dirtyWheel.image, dirtyWheel.sx, dirtyWheel.sy, dirtyWheel.sw, dirtyWheel.sh,
        -size * .61, -dirtyHeight / 2, size * 1.22, dirtyHeight);
      ctx.restore();
      return;
    }
    const wheelFrame = art.wheelFrames && art.wheelFrames.medium;
    ctx.save();
    ctx.translate(Math.round(shot.x), Math.round(screenY));
    ctx.rotate(shot.spin);
    if (wheelFrame) {
      const wheelHeight = spriteSize(wheelFrame, size);
      ctx.drawImage(wheelFrame.image, wheelFrame.sx, wheelFrame.sy, wheelFrame.sw, wheelFrame.sh,
        -size / 2, -wheelHeight / 2, size, wheelHeight);
    } else {
      ctx.restore();
      drawSprite(5, shot.x, shot.y, size);
      return;
    }
    ctx.fillStyle = "#7f4a31";
    ctx.fillRect(-size * .22, size * .18, size * .44, size * .2);
    ctx.fillStyle = "#b66a3d";
    ctx.fillRect(-size * .12, size * .34, size * .24, size * .14);
    ctx.restore();
  }

  function drawVillain(villain) {
    const frame = art.villainFrames && art.villainFrames[villain.frame];
    if (!frame) return;
    drawFrame(frame, villain.x, villain.y + Math.sin(elapsed * .85 + villain.phase) * 3, villainWidth());
  }

  function drawHazard(hazard) {
    if (hazard.compound && hazard.wheelFrame) {
      drawFrame(hazard.wheelFrame, hazard.x, hazard.y, hazard.size);
      return;
    }
    drawSprite(hazard.spriteIndex, hazard.x, hazard.y, hazard.size);
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
    invulnerableTimer = Math.max(0, invulnerableTimer - dt);
    rocketTimer = Math.max(0, rocketTimer - dt);
    jetpackTimer = Math.max(0, jetpackTimer - dt);
    const direction = Number(held.right) - Number(held.left);
    const targetVx = direction * Math.min(440, width * .62);
    player.vx += (targetVx - player.vx) * Math.min(1, 10 * dt);
    player.x += player.vx * dt;
    const halfPlayer = player.width / 2;
    if (player.x < -halfPlayer) player.x = width + halfPlayer;
    if (player.x > width + halfPlayer) player.x = -halfPlayer;

    const previousFeet = player.y - player.height / 2;
    player.vy -= 1240 * dt;
    if (rocketTimer > 0) player.vy = 1240;
    else if (jetpackTimer > 0) player.vy = Math.max(player.vy, 860);
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

    for (const villain of villains) {
      villain.x = Math.max(48, Math.min(width - 48,
        villain.baseX + Math.sin(elapsed * .55 + villain.phase) * Math.min(48, width * .12)));
      villain.frame = Math.floor(elapsed * 5 + villain.phase) % 4;
      villain.shotTimer -= dt;
      if (villain.shotTimer <= 0 && Math.abs(villain.y - cameraY) < height * 1.35) {
        const shotSize = Math.max(25, Math.min(34, width * .075)) * visualScale();
        villainShots.push({
          x: villain.x,
          y: villain.y - villainWidth() * .34,
          vx: (player.x - villain.x) * .16,
          vy: -270,
          size: shotSize,
          spin: 0,
          dead: false,
        });
        villain.shotTimer = 2.15 + Math.random() * .95;
      }
    }

    if (invulnerableTimer <= 0) collideWithEnemy(previousFeet, currentFeet);
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
    if (mode !== "running") return;

    for (const powerup of powerups) {
      if (powerup.collected) continue;
      const hitbox = powerupHitbox(powerup);
      if (!overlapRect(player.x, player.y, player.width * .66, player.height * .78,
        hitbox.x, hitbox.y, hitbox.width, hitbox.height)) continue;
      powerup.collected = true;
      if (powerup.type === "rocket") {
        rocketTimer = 1.8;
        invulnerableTimer = Math.max(invulnerableTimer, rocketTimer);
        player.vy = 1240;
        effects.push({ index: 11, x: player.x, y: player.y - player.height * .42, age: 0, duration: .55, size: 66 * visualScale() });
      } else {
        jetpackTimer = 5;
        invulnerableTimer = Math.max(invulnerableTimer, 5);
        player.vy = Math.max(player.vy, 860);
        effects.push({ index: 10, x: player.x, y: player.y, age: 0, duration: .65, size: 70 * visualScale() });
      }
    }

    for (const shot of villainShots) {
      if (shot.dead) continue;
      shot.x += shot.vx * dt;
      shot.y += shot.vy * dt;
      shot.vy -= 75 * dt;
      shot.spin += dt * 8;
      if (invulnerableTimer <= 0 && overlapRect(
        player.x, player.y, player.width * .54, player.height * .68,
        shot.x, shot.y, shot.size * .7, shot.size * .7,
      )) {
        endGame();
        return;
      }
    }

    for (const hazard of hazards) {
      if (hazard.dead) continue;
      hazard.y -= hazard.speed * dt;
      const hitbox = hazardHitbox(hazard);
      const closeX = Math.abs(player.x - hitbox.x) < (player.width * .58 + hitbox.width / 2);
      const crossedTop = previousFeet >= hitbox.top && currentFeet <= hitbox.top;
      if (hazard.bouncy && player.vy < 0 && closeX && crossedTop) {
        hazard.dead = true;
        player.y = hitbox.top + player.height / 2;
        player.vy = 880;
        effects.push({ index: 10, x: hazard.x, y: hitbox.top, age: 0, duration: .34, size: 48 * visualScale() });
        continue;
      }
      if (invulnerableTimer > 0) continue;
      if (overlapRect(player.x, player.y, player.width * .57, player.height * .66,
        hitbox.x, hitbox.y, hitbox.width, hitbox.height)) {
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
    hazards = hazards.filter((hazard) => hazard.y > cameraY - 180 && !hazard.dead);
    powerups = powerups.filter((powerup) => powerup.y > cameraY - 180 && !powerup.collected);
    villains = villains.filter((villain) => villain.y > cameraY - 300 && !villain.dead);
    villainShots = villainShots.filter((shot) => shot.y > cameraY - 260 && !shot.dead);

    if (player.y + player.height / 2 < cameraY - 6) {
      endGame();
      return;
    }
    updateHud();
  }

  function draw() {
    if (!ctx) return;
    drawBackdrop();

    for (const platform of platforms) {
      if (platform.broken) continue;
      drawSprite(platform.spriteIndex, platform.x, platform.y, platform.width, "platform", platform.height);
    }
    for (const enemy of enemies) {
      if (enemy.dead) continue;
      const bobY = enemy.y + Math.sin(elapsed * 4 + enemy.phase) * 4;
      drawSprite(4, enemy.x, bobY, enemyWidth());
    }

    for (const hazard of hazards) {
      if (!hazard.dead) drawHazard(hazard);
    }

    for (const villain of villains) {
      if (!villain.dead) drawVillain(villain);
    }
    for (const shot of villainShots) {
      if (!shot.dead) drawVillainShot(shot);
    }

    for (const powerup of powerups) {
      if (!powerup.collected) drawPowerup(powerup);
    }

    for (const effect of effects) {
      ctx.save();
      ctx.globalAlpha = Math.max(0, 1 - effect.age / effect.duration);
      drawSprite(effect.index, effect.x, effect.y, effect.size);
      ctx.restore();
    }

    if (player) {
      if (rocketTimer > 0) drawMountedPowerup("rocket");
      else if (jetpackTimer > 0) drawMountedPowerup("jetpack");
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
      drawInvulnerabilityShield();
    }

    if (mode === "running") {
      const progress = Math.max(0, Math.floor((peakY - 86) / 11));
      ctx.save();
      ctx.fillStyle = "rgba(249, 251, 255, .72)";
      ctx.font = "800 11px system-ui, sans-serif";
      ctx.textAlign = "right";
      ctx.fillText(`${progress} м`, width - 14, 22);
      if (rocketTimer > 0 || jetpackTimer > 0) {
        const activeType = rocketTimer > 0 ? "РАКЕТА" : "РЕАКТИВНЫЙ РАНЕЦ";
        const activeTime = rocketTimer > 0 ? rocketTimer : jetpackTimer;
        ctx.textAlign = "left";
        ctx.fillStyle = "rgba(8, 18, 38, .86)";
        ctx.fillRect(12, 88, Math.min(width * .45, 170), 22);
        ctx.fillStyle = rocketTimer > 0 ? "#ffbd4a" : "#8eeaff";
        ctx.font = "900 10px 'Courier New', monospace";
        ctx.fillText(`${activeType}  ${activeTime.toFixed(1)}с`, 20, 103);
      }
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
      powerups.forEach((powerup) => { powerup.x *= scaleX; powerup.y *= scaleY; powerup.size *= scaleX; });
      villains.forEach((villain) => { villain.x *= scaleX; villain.baseX *= scaleX; villain.y *= scaleY; });
      villainShots.forEach((shot) => { shot.x *= scaleX; shot.y *= scaleY; shot.vx *= scaleX; shot.vy *= scaleY; shot.size *= scaleX; });
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
    image(canvas.dataset.heroSheetSrc),
    image(canvas.dataset.backgroundSrc),
    image(canvas.dataset.powerupsSrc),
    image(canvas.dataset.wheelCompoundsSrc),
    image(canvas.dataset.villainSheetSrc),
    image(canvas.dataset.dirtyWheelSrc),
  ]).then(([atlas, heroSheet, background, powerupSheet, wheelSheet, villainSheet, dirtyWheel]) => {
    art.background = background;
    art.backgroundZones = background ? [background] : [];
    art.heroFrames = splitHeroSheet(heroSheet);
    const powerupFrames = splitSpriteSheet(powerupSheet, 2);
    const wheelFrames = splitSpriteSheet(wheelSheet, 3);
    const villainFrames = splitSpriteSheet(villainSheet, 4);
    art.powerupFrames = {
      rocket: powerupFrames[0] || null,
      jetpack: powerupFrames[1] || null,
    };
    art.wheelFrames = {
      soft: wheelFrames[0] || null,
      medium: wheelFrames[1] || null,
      hard: wheelFrames[2] || null,
    };
    art.villainFrames = villainFrames;
    art.dirtyWheelFrame = splitSpriteSheet(dirtyWheel, 1)[0] || null;
    if (art.heroFrames.length !== 4) {
      copy.textContent = "Не удалось загрузить анимацию персонажа. Обновите страницу и попробуйте ещё раз.";
      startButton.disabled = true;
      return;
    }
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
