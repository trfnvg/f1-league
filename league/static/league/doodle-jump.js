(() => {
  const canvas = document.getElementById("doodle-canvas");
  if (!canvas) return;

  const wrap = document.getElementById("doodle-board-wrap");
  const ctx = canvas.getContext("2d", { alpha: false });
  const overlay = document.getElementById("doodle-overlay");
  const title = document.getElementById("doodle-overlay-title");
  const copy = document.getElementById("doodle-overlay-copy");
  const kicker = document.getElementById("doodle-overlay-kicker");
  const startButton = document.getElementById("doodle-start");
  const scoreNode = document.getElementById("doodle-score");
  const fragsNode = document.getElementById("doodle-frags");
  const bestNode = document.getElementById("doodle-best");
  const bestStorageKey = "f1-doodle-gp-best-v1";
  const art = {};
  const held = { left: false, right: false };
  const sprites = [];
  const stars = [];

  let storedBest = "0";
  try { storedBest = localStorage.getItem(bestStorageKey) || "0"; } catch (error) { /* Private browsing can disable storage. */ }
  const numericBest = Number(storedBest);
  let best = Number.isFinite(numericBest) && numericBest > 0 ? numericBest : 0;
  let width = 1;
  let height = 1;
  let dpr = 1;
  let mode = "ready";
  let frame = 0;
  let previousTime = 0;
  let elapsed = 0;
  let player;
  let platforms = [];
  let enemies = [];
  let hazards = [];
  let bananas = [];
  let cameraY = 0;
  let worldTop = 0;
  let peakY = 0;
  let frags = 0;
  let bananaCount = 0;
  let finalScore = 0;
  let lastWasRecord = false;
  let touchOrigin = null;

  bestNode.textContent = String(best);

  const image = (src) => new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = src;
  });

  function cropSprites(atlas) {
    if (!atlas) return;
    const cellWidth = atlas.naturalWidth / 4;
    const cellHeight = atlas.naturalHeight / 2;

    for (let index = 0; index < 8; index += 1) {
      const sx = (index % 4) * cellWidth;
      const sy = Math.floor(index / 4) * cellHeight;
      const tile = document.createElement("canvas");
      tile.width = Math.ceil(cellWidth);
      tile.height = Math.ceil(cellHeight);
      const tileCtx = tile.getContext("2d", { willReadFrequently: true });
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

  function drawSprite(index, x, worldY, targetWidth, anchor = "center") {
    const sprite = sprites[index];
    if (!sprite) return false;
    const targetHeight = spriteSize(sprite, targetWidth);
    const screenY = height - (worldY - cameraY);
    const drawY = anchor === "bottom" ? screenY - targetHeight * .9 : screenY - targetHeight / 2;
    ctx.drawImage(sprite.image, sprite.sx, sprite.sy, sprite.sw, sprite.sh,
      x - targetWidth / 2, drawY, targetWidth, targetHeight);
    return true;
  }

  function drawBackdrop() {
    ctx.fillStyle = "#111a2c";
    ctx.fillRect(0, 0, width, height);

    if (art.background) {
      const tileHeight = width * art.background.naturalHeight / art.background.naturalWidth;
      const offset = (cameraY * .16) % tileHeight;
      for (let y = -offset - tileHeight; y < height + tileHeight; y += tileHeight) {
        ctx.drawImage(art.background, 0, y, width, tileHeight);
      }
      ctx.fillStyle = "rgba(8, 14, 25, .22)";
      ctx.fillRect(0, 0, width, height);
    }

    for (const star of stars) {
      const y = (star.y + cameraY * .08) % height;
      ctx.globalAlpha = star.alpha;
      ctx.fillStyle = star.color;
      ctx.beginPath();
      ctx.arc(star.x * width, y, star.radius, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  function worldToScreen(worldY) {
    return height - (worldY - cameraY);
  }

  function addPlatform(y, x, kind = "normal") {
    const spriteIndex = kind === "moving" ? 1 : kind === "break" ? 2 : kind === "spring" ? 3 : 0;
    const platformWidth = Math.max(88, Math.min(116, width * .23));
    platforms.push({
      x,
      originX: x,
      y,
      width: platformWidth,
      kind,
      spriteIndex,
      phase: Math.random() * Math.PI * 2,
      range: Math.min(42, width * .1),
      broken: false,
    });
  }

  function selectPlatformKind() {
    const roll = Math.random();
    if (roll < .12) return "break";
    if (roll < .29) return "moving";
    if (roll < .36) return "spring";
    return "normal";
  }

  function buildGame() {
    const heroHeight = Math.min(88, Math.max(70, width * .18));
    const heroWidth = heroHeight * (art.hero ? art.hero.naturalWidth / art.hero.naturalHeight : .67);
    const firstY = 86;
    platforms = [];
    enemies = [];
    hazards = [];
    bananas = [];
    cameraY = 0;
    worldTop = firstY;
    peakY = firstY + heroHeight / 2;
    frags = 0;
    bananaCount = 0;
    finalScore = 0;
    elapsed = 0;
    held.left = false;
    held.right = false;

    addPlatform(firstY, width * .5, "normal");
    let nextY = firstY;
    let lastX = width * .5;
    while (nextY < height + 320) {
      nextY += 82 + Math.random() * 39;
      const delta = (Math.random() * 2 - 1) * width * .4;
      lastX = Math.max(width * .12, Math.min(width * .88, lastX + delta));
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
      const y = worldTop + 82 + Math.random() * 40;
      const prior = platforms[platforms.length - 1];
      const lastX = prior ? prior.originX : width / 2;
      const nextX = Math.max(width * .12, Math.min(width * .88, lastX + (Math.random() * 2 - 1) * width * .4));
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
        size: Math.max(38, Math.min(52, width * .12)),
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
    fragsNode.textContent = String(frags);
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
      const enemyHeight = Math.max(46, Math.min(62, width * .145));
      const enemyTop = enemy.y + enemyHeight * .35;
      const closeX = Math.abs(player.x - enemy.x) < (player.width * .64 + 23);
      const crossedTop = previousFeet >= enemyTop && currentFeet <= enemyTop;
      if (player.vy < 0 && closeX && crossedTop) {
        enemy.dead = true;
        frags += 1;
        player.vy = 810;
        return true;
      }
      if (overlapRect(player.x, player.y, player.width * .62, player.height * .72, enemy.x, enemy.y, 45, enemyHeight * .68)) {
        endGame();
        return true;
      }
    }
    return false;
  }

  function update(dt) {
    elapsed += dt;
    const direction = Number(held.right) - Number(held.left);
    player.vx = direction * Math.min(425, width * .76);
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
        player.vy = platform.kind === "spring" ? 930 : 720;
        break;
      }
    }

    for (const banana of bananas) {
      if (banana.taken) continue;
      const bobY = banana.y + Math.sin(elapsed * 3 + banana.phase) * 7;
      if (overlapRect(player.x, player.y, player.width * .7, player.height * .72, banana.x, bobY, 32, 36)) {
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

    if (player.y > cameraY + height * .54) cameraY = player.y - height * .54;
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
      ctx.save();
      ctx.shadowColor = "rgba(255, 207, 73, .78)";
      ctx.shadowBlur = 18;
      drawSprite(7, banana.x, banana.y + bob, Math.max(34, width * .085));
      ctx.restore();
    }

    for (const platform of platforms) {
      if (platform.broken) continue;
      ctx.save();
      if (platform.kind === "spring") {
        ctx.shadowColor = "rgba(113, 222, 210, .58)";
        ctx.shadowBlur = 17;
      }
      drawSprite(platform.spriteIndex, platform.x, platform.y, platform.width, "bottom");
      ctx.restore();
    }

    for (const enemy of enemies) {
      if (enemy.dead) continue;
      const bobY = enemy.y + Math.sin(elapsed * 4 + enemy.phase) * 4;
      ctx.save();
      ctx.shadowColor = "rgba(240, 68, 72, .55)";
      ctx.shadowBlur = 13;
      drawSprite(4, enemy.x, bobY, Math.max(47, Math.min(61, width * .15)));
      ctx.restore();
    }

    for (const hazard of hazards) drawSprite(hazard.spriteIndex, hazard.x, hazard.y, hazard.size);

    if (player) {
      const screenY = worldToScreen(player.y);
      ctx.save();
      ctx.translate(player.x, screenY);
      if (player.vx < -5) ctx.scale(-1, 1);
      ctx.shadowColor = "rgba(255, 209, 60, .38)";
      ctx.shadowBlur = 17;
      if (art.hero) {
        ctx.drawImage(art.hero, -player.width / 2, -player.height / 2, player.width, player.height);
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
    dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    stars.length = 0;
    for (let i = 0; i < 62; i += 1) {
      stars.push({ x: Math.random(), y: Math.random() * height, radius: Math.random() * 1.2 + .35,
        alpha: Math.random() * .42 + .16, color: Math.random() < .3 ? "#ffd77d" : "#edf3ff" });
    }
    if (player && previousWidth > 1 && previousHeight > 1) {
      const scaleX = width / previousWidth;
      const scaleY = height / previousHeight;
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
    const button = document.querySelector(`[data-doodle-action="${direction}"]`);
    if (button) button.classList.toggle("is-pressed", value);
  }

  function clearDirections() {
    setDirection("left", false);
    setDirection("right", false);
  }

  document.addEventListener("keydown", (event) => {
    const key = event.key.toLowerCase();
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

  document.querySelectorAll("[data-doodle-action]").forEach((button) => {
    const direction = button.dataset.doodleAction;
    button.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      button.setPointerCapture?.(event.pointerId);
      setDirection(direction, true);
    });
    ["pointerup", "pointercancel", "lostpointercapture"].forEach((type) => {
      button.addEventListener(type, () => setDirection(direction, false));
    });
  });

  canvas.addEventListener("pointerdown", (event) => {
    touchOrigin = event.clientX;
    canvas.setPointerCapture?.(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (touchOrigin === null || event.pointerType === "mouse") return;
    const delta = event.clientX - touchOrigin;
    setDirection("left", delta < -10);
    setDirection("right", delta > 10);
  });
  ["pointerup", "pointercancel", "lostpointercapture"].forEach((type) => {
    canvas.addEventListener(type, () => { touchOrigin = null; clearDirections(); });
  });

  Promise.all([
    image(canvas.dataset.heroSrc),
    image(canvas.dataset.atlasSrc),
    image(canvas.dataset.backgroundSrc),
  ]).then(([hero, atlas, background]) => {
    art.hero = hero;
    art.background = background;
    cropSprites(atlas);
    resize();
    setOverlay("ready");
  });

  if ("ResizeObserver" in window) {
    new ResizeObserver(resize).observe(wrap);
  } else {
    window.addEventListener("resize", resize);
  }
})();
