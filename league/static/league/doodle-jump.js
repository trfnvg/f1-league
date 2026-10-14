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
  const adminSandbox = canvas.dataset.adminFlight === "1";
  const flightButton = document.getElementById("doodle-flight-toggle");
  let freeFlight = false;
  const logicalViewportWidth = window.matchMedia("(max-width: 760px), (hover: none) and (pointer: coarse)").matches ? 390 : 600;
  let rasterCache = new WeakMap();
  let viewportKey = "";
  const held = { left: false, right: false };
  const sprites = [];
  let skyGradient = null;
  let cloudCache = null;
  let journeyCache = null;
  let spacePatternCache = null;
  let lastRenderTime = 0;
  let nextHudUpdate = 0;
  const touchPointers = new Map();
  let touchBounds = null;
  // One continuous painting climbs from paddock to canyon to sky; only the
  // upper atmosphere fades into an infinite layer of individual cloud sprites.
  const levelWorldHeight = 2400;
  const paddockEnd = 1450;
  const skyFade = { start: 4600, end: 6200 };
  const spaceFade = { start: 10500, end: 12900 };
  const backgroundZoneNames = ["Паддок Рассела", "Подъём по каньону", "Над облаками", "Космос"];

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
  let updateAccumulator = 0;
  let elapsed = 0;
  let player;
  let platforms = [];
  let enemies = [];
  let hazards = [];
  let spaceBoss = null;
  let bossShots = [];
  let marshals = [];
  let nextMarshalY = 1800;
  let marshalBonus = 0;
  let bonusNoticeUntil = 0;
  let bossWait = 90 + Math.random() * 60;
  let powerups = [];
  let effects = [];
  let cameraY = 0;
  let worldTop = 0;
  let startY = 86;
  let peakY = 0;
  let frags = 0;
  let finalScore = 0;
  let lastWasRecord = false;
  let trailTimer = 0;
  let touchDirection = null;
  let nativeFullscreenRequested = false;
  let facing = 1;
  let invulnerableTimer = 0;
  let rocketTimer = 0;
  let lastPowerupSpawnY = -Infinity;
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
      if (index === 8 || index === 9) continue;
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

      const sw = maxX - minX + 1;
      const sh = maxY - minY + 1;
      sprites[index] = maxX >= minX && maxY >= minY
        ? {
          image: atlas,
          sx: sx + minX,
          sy: sy + minY,
          sw,
          sh,
          mask: alphaMask(pixels, tile.width, minX, minY, sw, sh),
        }
        : null;
    }
  }

  // Read sprite alpha once at load and retain a compact silhouette. Runtime
  // collision checks touch only these 18x18 bits after a cheap bounds check.
  function alphaMask(pixels, stride, x, y, spriteWidth, spriteHeight, columns = 18, rows = 18) {
    const bits = new Uint8Array(columns * rows);
    const topRows = new Uint8Array(columns);
    topRows.fill(rows);
    const xEnd = x + spriteWidth;
    const yEnd = y + spriteHeight;
    for (let py = y; py < yEnd; py += 1) {
      for (let px = x; px < xEnd; px += 1) {
        if (pixels[(py * stride + px) * 4 + 3] <= 18) continue;
        const column = Math.min(columns - 1, Math.floor((px - x) * columns / spriteWidth));
        const row = Math.min(rows - 1, Math.floor((py - y) * rows / spriteHeight));
        bits[row * columns + column] = 1;
        if (row < topRows[column]) topRows[column] = row;
      }
    }
    return { bits, columns, rows, topRows };
  }

  function splitHeroSheet(sheet) {
    if (!sheet) return [];
    // The generated poses have unequal widths. Cut at verified transparent
    // gutters, then place them in identical cells with a common boot baseline.
    const poses = splitSpriteSheet(sheet, 4, [0, .251, .486, .787, 1]);
    if (poses.some((pose) => !pose)) return [];
    const frameWidth = Math.max(...poses.map((pose) => pose.sw));
    const frameHeight = Math.max(...poses.map((pose) => pose.sh));
    const frames = [];
    for (const pose of poses) {
      const tile = document.createElement("canvas");
      tile.width = frameWidth;
      tile.height = frameHeight;
      const tileCtx = tile.getContext("2d");
      tileCtx.imageSmoothingEnabled = false;
      tileCtx.drawImage(pose.image, pose.sx, pose.sy, pose.sw, pose.sh,
        Math.round((frameWidth - pose.sw) / 2), frameHeight - pose.sh, pose.sw, pose.sh);
      frames.push({ image: tile, sx: 0, sy: 0, sw: frameWidth, sh: frameHeight });
    }
    return frames;
  }

  function splitSpriteSheet(sheet, columns, boundaries = null) {
    if (!sheet || !columns) return [];
    const frameHeight = sheet.naturalHeight;
    const frames = [];
    for (let frameIndex = 0; frameIndex < columns; frameIndex += 1) {
      const startX = (boundaries ? boundaries[frameIndex] : frameIndex / columns) * sheet.naturalWidth;
      const endX = (boundaries ? boundaries[frameIndex + 1] : (frameIndex + 1) / columns) * sheet.naturalWidth;
      const frameWidth = Math.ceil(endX - startX);
      const tile = document.createElement("canvas");
      tile.width = frameWidth;
      tile.height = frameHeight;
      const tileCtx = tile.getContext("2d", { willReadFrequently: true });
      tileCtx.imageSmoothingEnabled = false;
      tileCtx.drawImage(sheet, startX, 0,
        endX - startX, frameHeight, 0, 0, frameWidth, frameHeight);
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
      const sw = maxX - minX + 1;
      const sh = maxY - minY + 1;
      frames.push(maxX >= minX && maxY >= minY
        ? { image: tile, sx: minX, sy: minY, sw, sh, mask: alphaMask(pixels, frameWidth, minX, minY, sw, sh) }
        : null);
    }
    return frames;
  }

  function spriteSize(sprite, targetWidth) {
    return sprite ? targetWidth * sprite.sh / sprite.sw : targetWidth;
  }

  function bakeSprite(sprite, maxDimension = 192, smooth = false) {
    if (!sprite) return null;
    const scale = Math.min(1, maxDimension / Math.max(sprite.sw, sprite.sh));
    const texture = document.createElement("canvas");
    texture.width = Math.max(1, Math.round(sprite.sw * scale));
    texture.height = Math.max(1, Math.round(sprite.sh * scale));
    const textureCtx = texture.getContext("2d");
    textureCtx.imageSmoothingEnabled = smooth;
    if (smooth) textureCtx.imageSmoothingQuality = "high";
    textureCtx.drawImage(sprite.image, sprite.sx, sprite.sy, sprite.sw, sprite.sh,
      0, 0, texture.width, texture.height);
    return { ...sprite, image: texture, sx: 0, sy: 0, sw: texture.width, sh: texture.height };
  }

  function currentHeroSprite() {
    const frames = art.heroFrames;
    if (!frames || frames.length < 4 || !player) return frames && frames[1] ? frames[1] : null;

    // The western sheet follows the jump arc: compact, takeoff, arms-wide peak,
    // and descent. Mapping from velocity keeps poses aligned with landings.
    const velocity = player.vy;
    const frameIndex = velocity < -100 ? 3 : velocity < 100 ? 2 : velocity < 600 ? 1 : 0;
    return frames[frameIndex] || frames[1];
  }

  // Rasterize each stable sprite size once at the display's resolution.
  // Preserve source artwork; the frame loop only composites cached textures.
  function rasterSprite(sprite, targetWidth, targetHeight) {
    let sizes = rasterCache.get(sprite);
    if (!sizes) { sizes = new Map(); rasterCache.set(sprite, sizes); }
    const pixelWidth = Math.max(1, Math.round(targetWidth * dpr));
    const pixelHeight = Math.max(1, Math.round(targetHeight * dpr));
    const key = `${pixelWidth}:${pixelHeight}`;
    if (sizes.has(key)) return sizes.get(key);
    const texture = document.createElement("canvas");
    texture.width = pixelWidth;
    texture.height = pixelHeight;
    const painter = texture.getContext("2d");
    painter.imageSmoothingEnabled = true;
    painter.imageSmoothingQuality = "high";
    painter.drawImage(sprite.image, sprite.sx, sprite.sy, sprite.sw, sprite.sh,
      0, 0, pixelWidth, pixelHeight);
    // Bound caches for variable-size effects and pickups.
    if (sizes.size >= 24) sizes.delete(sizes.keys().next().value);
    sizes.set(key, texture);
    return texture;
  }

  function drawSprite(index, x, worldY, targetWidth, anchor = "center", targetHeight = null) {
    const sprite = sprites[index];
    if (!sprite) return false;
    const drawHeight = targetHeight || spriteSize(sprite, targetWidth);
    const screenY = height - (worldY - cameraY);
    const drawY = anchor === "platform" ? screenY : screenY - drawHeight / 2;
    if (drawY > height || drawY + drawHeight < 0) return false;
    ctx.drawImage(rasterSprite(sprite, targetWidth, drawHeight),
      x - targetWidth / 2, drawY, targetWidth, drawHeight);
    return true;
  }

  function drawFrame(frame, x, worldY, targetWidth, anchor = "center", targetHeight = null) {
    if (!frame) return false;
    const drawHeight = targetHeight || spriteSize(frame, targetWidth);
    const screenY = height - (worldY - cameraY);
    const drawY = anchor === "platform" ? screenY : screenY - drawHeight / 2;
    if (drawY > height || drawY + drawHeight < 0) return false;
    ctx.drawImage(rasterSprite(frame, targetWidth, drawHeight),
      x - targetWidth / 2, drawY, targetWidth, drawHeight);
    return true;
  }

  function cacheBackground() {
    skyGradient = ctx.createLinearGradient(0, 0, 0, height);
    skyGradient.addColorStop(0, "#498bc9");
    skyGradient.addColorStop(1, "#89bddc");
    // Bound source texture sizes once instead of resampling the full artwork
    // for every frame, especially on high-DPI mobile devices.
    const journeyWidth = Math.min(640, Math.ceil(width));
    if (art.journey && (!journeyCache || journeyCache.width !== journeyWidth)) {
      journeyCache = document.createElement("canvas");
      journeyCache.width = journeyWidth;
      journeyCache.height = Math.round(journeyWidth * art.journey.naturalHeight / art.journey.naturalWidth);
      const backgroundCtx = journeyCache.getContext("2d", { alpha: false });
      backgroundCtx.imageSmoothingEnabled = false;
      backgroundCtx.drawImage(art.journey, 0, 0, journeyCache.width, journeyCache.height);
    }
    if (art.cloud && !cloudCache) {
      cloudCache = document.createElement("canvas");
      cloudCache.width = 512;
      cloudCache.height = Math.round(512 * art.cloud.naturalHeight / art.cloud.naturalWidth);
      cloudCache.getContext("2d").drawImage(art.cloud, 0, 0, cloudCache.width, cloudCache.height);
    }
    const spaceWidth = Math.min(1536, Math.ceil(width * dpr));
    if (art.space && (!spacePatternCache || spacePatternCache.width !== spaceWidth)) {
      const tile = document.createElement("canvas");
      tile.width = spaceWidth;
      tile.height = Math.round(spaceWidth * art.space.naturalHeight / art.space.naturalWidth);
      const tileContext = tile.getContext("2d");
      tileContext.imageSmoothingEnabled = false;
      tileContext.drawImage(art.space, 0, 0, tile.width, tile.height);

      // Pair a tile with its vertical mirror. Matching top/bottom edges make
      // the repeated pattern seamless while the artwork remains varied.
      spacePatternCache = document.createElement("canvas");
      spacePatternCache.width = tile.width;
      spacePatternCache.height = tile.height * 2;
      const patternContext = spacePatternCache.getContext("2d");
      patternContext.imageSmoothingEnabled = false;
      patternContext.drawImage(tile, 0, 0);
      patternContext.save();
      patternContext.translate(0, spacePatternCache.height);
      patternContext.scale(1, -1);
      patternContext.drawImage(tile, 0, 0);
      patternContext.restore();
    }
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function storyProgress() {
    return Math.max(0, cameraY) / levelWorldHeight;
  }

  function backgroundView(climb, sourceWidth, sourceHeight, viewportWidth, viewportHeight) {
    const viewHeight = Math.min(sourceHeight, sourceWidth * viewportHeight / viewportWidth);
    const progress = clamp(climb / skyFade.end, 0, 1);
    const ascent = progress * (2 - progress);
    // Decreasing source Y moves every landmark DOWN as the camera climbs UP.
    // This is a single finite painting: never repeat or mirror the paddock.
    return { y: (sourceHeight - viewHeight) * (1 - ascent), height: viewHeight };
  }

  function backgroundFade(climb, start, end) {
    const value = clamp((climb - start) / (end - start), 0, 1);
    return value * value * (3 - 2 * value);
  }

  function decorRandom(index, salt) {
    const value = Math.sin((index + 1) * 127.1 + (salt + 1) * 311.7) * 43758.5453;
    return value - Math.floor(value);
  }

  function drawSpaceBackdrop(climb, alpha) {
    if (!spacePatternCache || alpha <= 0) return;
    const tileHeight = spacePatternCache.height / dpr;
    if (!tileHeight) return;
    const cycle = tileHeight;
    // The scenery drifts DOWN as the player climbs, at a slower parallax rate.
    const offset = Math.max(0, climb - spaceFade.start) * .045 % cycle;
    ctx.globalAlpha = alpha;
    for (let y = offset - cycle; y < height; y += cycle) {
      // Align to physical pixels and overlap one pixel: fractional canvas
      // sampling must never expose the bright sky underneath adjacent tiles.
      const top = Math.floor(y * dpr) / dpr;
      const bottom = Math.ceil((y + cycle) * dpr) / dpr;
      ctx.drawImage(spacePatternCache, 0, top, width, bottom - top + 1 / dpr);
    }
    ctx.globalAlpha = 1;
  }

  function drawSpacePlanet(x, y, radius, variant, alpha) {
    const colors = variant % 3 === 0
      ? { base: "#686580", shade: "#37374d", light: "#a4a1b5", ring: "#818a9c" }
      : variant % 3 === 1
        ? { base: "#807580", shade: "#494251", light: "#b6a8b4", ring: "#848299" }
        : { base: "#64758b", shade: "#333e55", light: "#9faebc", ring: "#9590a6" };
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.translate(x, y);
    ctx.rotate(-.18 + (variant % 2) * .25 + elapsed * .045);
    ctx.beginPath();
    ctx.ellipse(0, 2, radius * 1.15, radius * .3, 0, 0, Math.PI * 2);
    ctx.strokeStyle = colors.ring;
    ctx.lineWidth = Math.max(2, radius * .07);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(0, 0, radius * .72, 0, Math.PI * 2);
    const surface = ctx.createLinearGradient(-radius, -radius, radius, radius);
    surface.addColorStop(0, colors.light);
    surface.addColorStop(.48, colors.base);
    surface.addColorStop(1, colors.shade);
    ctx.fillStyle = surface;
    ctx.fill();
    // Small blocky craters keep the celestial props in the game's pixel-art language.
    ctx.fillStyle = colors.shade;
    ctx.globalAlpha = alpha * .7;
    ctx.fillRect(-radius * .28, -radius * .16, radius * .17, radius * .1);
    ctx.fillRect(radius * .18, radius * .2, radius * .13, radius * .09);
    ctx.fillRect(-radius * .02, radius * .4, radius * .2, radius * .08);
    ctx.restore();
  }

  function drawSpaceDecor(climb, alpha) {
    if (alpha <= 0) return;
    const ascent = Math.max(0, climb - spaceFade.start);
    const planetScroll = ascent * .19;
    const planetSpacing = 2200;
    const planetRadius = clamp(width * .075, 27, 78);
    const firstPlanet = Math.max(0, Math.floor((planetScroll - height * 1.4) / planetSpacing));
    const lastPlanet = Math.floor((planetScroll + height * 1.4) / planetSpacing) + 1;
    for (let index = firstPlanet; index <= lastPlanet; index += 1) {
      const worldY = 680 + index * planetSpacing + decorRandom(index, 4) * planetSpacing * .42;
      const y = height - (worldY - planetScroll);
      if (y < -planetRadius * 2 || y > height + planetRadius * 2) continue;
      const side = decorRandom(index, 5) < .5 ? 1 : -1;
      const x = width * (.5 + side * (.22 + decorRandom(index, 6) * .24));
      drawSpacePlanet(x, y, planetRadius * (.72 + decorRandom(index, 7) * .35), index, alpha * .78);
    }

    // One brief, decorative meteor every 19 seconds, never a collision object.
    const cometPhase = elapsed % 19;
    if (cometPhase < 2.4) {
      const index = Math.floor(elapsed / 19);
      const tail = clamp(width * .105, 38, 96);
      const travel = cometPhase / 2.4;
      const x = -tail + travel * (width + tail * 2);
      const y = height * (.12 + decorRandom(index, 9) * .42) + travel * 90;
      ctx.save();
      ctx.globalAlpha = alpha * .65 * Math.sin(travel * Math.PI);
      ctx.strokeStyle = "rgba(171, 210, 255, .68)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x - tail, y - tail * .48);
      ctx.stroke();
      ctx.fillStyle = "#f5f1ff";
      ctx.fillRect(x - 3, y - 3, 6, 6);
      ctx.fillStyle = "#9695ae";
      ctx.fillRect(x - tail * .45, y - tail * .25, 4, 4);
      ctx.restore();
    }
  }

  function drawBackdrop() {
    const climb = Math.max(0, cameraY);
    const intoSky = backgroundFade(climb, skyFade.start, skyFade.end);
    const intoSpace = backgroundFade(climb, spaceFade.start, spaceFade.end);
    ctx.fillStyle = skyGradient || "#6ba5d3";
    ctx.fillRect(0, 0, width, height);
    if (journeyCache && intoSky < 1) {
      const source = journeyCache;
      const view = backgroundView(climb, source.width, source.height, width, height);
      ctx.globalAlpha = 1 - intoSky;
      ctx.drawImage(source, 0, view.y, source.width, view.height, 0, 0, width, height);
    }
    drawSpaceBackdrop(climb, intoSpace);
    // Separate cloud sprites cross the screen downward. Their wrap happens
    // entirely outside the viewport, so infinite sky has no image seam. They
    // gradually give way to space rather than ending at a hard level boundary.
    const cloudsAlpha = backgroundFade(climb, 2800, skyFade.end) * (1 - intoSpace);
    if (cloudCache && cloudsAlpha > 0) {
      for (let i = 0; i < 6; i += 1) {
        const cloudWidth = width * (.38 + (i % 3) * .12);
        const cloudHeight = cloudWidth * cloudCache.height / cloudCache.width;
        const cycle = height + 2 * cloudHeight + 40;
        const y = ((i / 6 * cycle + climb * (.09 + (i % 3) * .025)) % cycle) - cloudHeight - 20;
        const x = (i % 2 ? width - cloudWidth * .72 : -cloudWidth * .28)
          + Math.sin(elapsed * .12 + i) * width * .015;
        ctx.globalAlpha = cloudsAlpha * (.3 + (i % 3) * .12);
        ctx.drawImage(cloudCache, x, y, cloudWidth, cloudHeight);
      }
    }
    drawSpaceDecor(climb, intoSpace);
    ctx.globalAlpha = 1;
  }

  function worldToScreen(worldY) {
    return height - (worldY - cameraY);
  }

  function visualScale() {
    return .68;
  }

  function enemyWidth() {
    return 58.5 * visualScale();
  }

  function addPlatform(y, x, kind = "normal") {
    const spriteIndex = kind === "moving" ? 1 : kind === "break" ? 2 : kind === "spring" ? 3 : 0;
    const platformWidth = 89.7 * visualScale();
    const spriteWidth = kind === "spring"
      ? Math.min(72 * visualScale(), platformWidth * .82)
      : platformWidth;
    const spriteHeight = spriteSize(sprites[spriteIndex], spriteWidth);
    const platform = {
      x,
      originX: x,
      y,
      width: platformWidth,
      hitboxWidth: kind === "spring" ? spriteWidth * .72 : platformWidth,
      spriteWidth,
      height: spriteHeight,
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
    if (!lower || !upper) return;
    const gap = upper.y - lower.y;
    const powerupY = lower.y + gap * (.42 + Math.random() * .16);
    // Power-ups are deliberately rare and separated in world space so that a
    // lucky run can never chain several rockets back-to-back.
    if (powerupY - lastPowerupSpawnY < 2200 || Math.random() > .025) return;
    lastPowerupSpawnY = powerupY;
    const laneX = lower.x + (upper.x - lower.x) * (.35 + Math.random() * .3);
    powerups.push({
      type: "rocket",
      x: clamp(laneX, width * .12, width * .88),
      y: powerupY,
      size: 29.25 * visualScale(),
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
    const heroHeight = 70 * visualScale();
    // Preserve the previous gameplay hitbox independently of the new hat/arms.
    const heroWidth = heroHeight * .75;
    const firstY = Math.max(86, Math.min(118, height * .14));
    platforms = [];
    enemies = [];
    hazards = [];
    spaceBoss = null;
    bossShots = [];
    marshals = [];
    nextMarshalY = 1800;
    marshalBonus = 0;
    bonusNoticeUntil = 0;
    bossWait = 90 + Math.random() * 60;
    powerups = [];
    effects = [];
    cameraY = 0;
    startY = firstY;
    worldTop = firstY;
    peakY = firstY + heroHeight / 2;
    frags = 0;
    finalScore = 0;
    invulnerableTimer = 0;
    rocketTimer = 0;
    lastPowerupSpawnY = -Infinity;
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
      if (y >= nextMarshalY && nextPlatform.kind === "normal") {
        marshals.push({ platform: nextPlatform, collected: false });
        nextMarshalY = y + 1800 + Math.random() * 1000;
      }
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
        // Sprite alpha masks are used for collision, not a generic bounding box.
        compound,
        wheelFrame: compound && art.wheelFrames ? art.wheelFrames[compound] : null,
        dead: false,
        size: 46.8 * visualScale(),
      });
    }

  }

  function updateHud() {
    const heightPoints = Math.max(0, Math.floor((peakY - startY) / 11));
    const score = heightPoints + frags * 30 + marshalBonus;
    const levelNumber = Math.floor(storyProgress());
    const displayScore = mode === "over" ? finalScore : score;
    if (scoreNode.dataset.value !== String(displayScore)) {
      scoreNode.dataset.value = String(displayScore);
      scoreNode.textContent = String(displayScore);
    }
    const displayBest = String(Math.max(best, score));
    if (bestNode.dataset.value !== displayBest) {
      bestNode.dataset.value = displayBest;
      bestNode.textContent = displayBest;
    }
    const displayLevel = String(levelNumber + 1).padStart(2, "0");
    if (levelNode.dataset.value !== displayLevel) {
      levelNode.dataset.value = displayLevel;
      levelNode.textContent = displayLevel;
    }
    const zoneIndex = cameraY < paddockEnd ? 0
      : cameraY < skyFade.end ? 1
        : cameraY < spaceFade.start ? 2 : 3;
    const displayName = backgroundZoneNames[zoneIndex];
    if (levelNameNode.dataset.value !== displayName) {
      levelNameNode.dataset.value = displayName;
      levelNameNode.textContent = displayName;
      levelNameNode.title = displayName;
    }
  }

  function setOverlay(state) {
    if (state === "running") {
      overlay.classList.add("is-hidden");
      return;
    }
    overlay.classList.remove("is-hidden");
    if (state === "ready") {
      kicker.textContent = "СЕССИЯ ТОЛЬКО ДЛЯ АДМИНА";
      title.textContent = "Седлай платформу!";
      copy.textContent = "Дикий Запад не заканчивается: прыгай всё выше, сбивай шинных гремлинов и бей рекорд. На телефоне касайся левой или правой половины поля.";
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
    if (adminSandbox) return;
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
    if (adminSandbox) return;
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
    updateAccumulator = 0;
    nextHudUpdate = 0;
    registerAttempt();
    setOverlay("running");
    previousTime = performance.now();
    lastRenderTime = previousTime;
    frame = requestAnimationFrame(loop);
    canvas.focus({ preventScroll: true });
  }

  function endGame() {
    if (mode !== "running") return;
    mode = "over";
    const heightPoints = Math.max(0, Math.floor((peakY - startY) / 11));
    finalScore = heightPoints + frags * 30 + marshalBonus;
    lastWasRecord = finalScore > best;
    if (!adminSandbox && finalScore > best) {
      best = finalScore;
      try { localStorage.setItem(bestStorageKey, String(best)); } catch (error) { /* Keep the run playable without storage. */ }
    }
    updateHud();
    setOverlay("over");
    submitScore();
    draw();
  }

  function spriteOverlapsEllipse(sprite, x, y, objectWidth, objectHeight, targetX, targetY, targetRadiusX, targetRadiusY) {
    const objectRadiusX = objectWidth / 2;
    const objectRadiusY = objectHeight / 2;
    if (Math.abs(targetX - x) > objectRadiusX + targetRadiusX
      || Math.abs(targetY - y) > objectRadiusY + targetRadiusY) return false;
    const mask = sprite && sprite.mask;
    if (!mask || !objectWidth || !objectHeight) {
      const dx = (targetX - x) / Math.max(1, objectRadiusX + targetRadiusX);
      const dy = (targetY - y) / Math.max(1, objectRadiusY + targetRadiusY);
      return dx * dx + dy * dy < 1;
    }
    const cellWidth = objectWidth / mask.columns;
    const cellHeight = objectHeight / mask.rows;
    const left = x - objectRadiusX;
    const top = y + objectRadiusY;
    // Inspect only mask cells near the player's ellipse, not the entire sprite.
    // One-cell margins preserve contacts exactly on cell boundaries.
    const minColumn = clamp(Math.floor((targetX - targetRadiusX - left) / cellWidth) - 1, 0, mask.columns - 1);
    const maxColumn = clamp(Math.floor((targetX + targetRadiusX - left) / cellWidth) + 1, 0, mask.columns - 1);
    const minRow = clamp(Math.floor((top - targetY - targetRadiusY) / cellHeight) - 1, 0, mask.rows - 1);
    const maxRow = clamp(Math.floor((top - targetY + targetRadiusY) / cellHeight) + 1, 0, mask.rows - 1);
    const radiusX = Math.max(1, targetRadiusX);
    const radiusY = Math.max(1, targetRadiusY);
    for (let row = minRow; row <= maxRow; row += 1) {
      for (let column = minColumn; column <= maxColumn; column += 1) {
        if (!mask.bits[row * mask.columns + column]) continue;
        const cellX = left + (column + .5) * cellWidth;
        const cellY = top - (row + .5) * cellHeight;
        const dx = Math.max(0, Math.abs(cellX - targetX) - cellWidth * .5) / radiusX;
        const dy = Math.max(0, Math.abs(cellY - targetY) - cellHeight * .5) / radiusY;
        if (dx * dx + dy * dy <= 1) return true;
      }
    }
    return false;
  }

  function spriteTopAtX(sprite, x, y, objectWidth, objectHeight, targetX) {
    const mask = sprite && sprite.mask;
    if (!mask || !objectWidth || !objectHeight) return y + objectHeight / 2;
    const left = x - objectWidth / 2;
    const halfPlayerWidth = player ? player.width * .22 : 0;
    const firstColumn = clamp(Math.floor((targetX - halfPlayerWidth - left) / objectWidth * mask.columns), 0, mask.columns - 1);
    const lastColumn = clamp(Math.floor((targetX + halfPlayerWidth - left) / objectWidth * mask.columns), 0, mask.columns - 1);
    let topRow = mask.rows;
    for (let column = firstColumn; column <= lastColumn; column += 1) {
      const columnTop = mask.topRows ? mask.topRows[column] : mask.rows;
      if (columnTop < topRow) topRow = columnTop;
    }
    return y + objectHeight / 2 - topRow / mask.rows * objectHeight;
  }

  function pruneWorldObjects(items, cameraMargin, inactiveFlag = null) {
    const lowestY = cameraY - cameraMargin;
    let kept = 0;
    for (let index = 0; index < items.length; index += 1) {
      const item = items[index];
      if (item.y > lowestY && (!inactiveFlag || !item[inactiveFlag])) items[kept++] = item;
    }
    items.length = kept;
  }

  function hazardHitbox(hazard) {
    const sprite = hazard.wheelFrame || sprites[hazard.spriteIndex];
    const width = hazard.size;
    const height = spriteSize(sprite, width) || width;
    return { sprite, x: hazard.x, y: hazard.y, width, height };
  }

  function powerupHitbox(powerup) {
    const sprite = art.powerupFrames && art.powerupFrames.rocket;
    const width = powerup.size * 1.55;
    return { sprite, x: powerup.x, y: powerup.y, width, height: spriteSize(sprite, width) };
  }

  function drawPowerup(powerup) {
    const screenY = worldToScreen(powerup.y + Math.sin(elapsed * 3 + powerup.phase) * 4);
    const size = powerup.size;
    const frame = art.powerupFrames && art.powerupFrames.rocket;
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
    ctx.shadowColor = "rgba(255, 82, 103, .75)";
    ctx.shadowBlur = 12;
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
    ctx.restore();
  }

  function drawRocketRide() {
    const frame = art.rocketRide;
    if (!player || !frame) return false;
    const rocketHeight = player.height * 1.55;
    const rocketWidth = rocketHeight * frame.sw / frame.sh;
    const screenY = worldToScreen(player.y + Math.sin(elapsed * 8) * 1.5);
    ctx.save();
    ctx.translate(Math.round(player.x), Math.round(screenY));
    ctx.rotate(Math.sin(elapsed * 5) * .025);
    ctx.drawImage(frame.image, frame.sx, frame.sy, frame.sw, frame.sh,
      -rocketWidth / 2, -rocketHeight / 2, rocketWidth, rocketHeight);
    // A small amber pulse brightens the exhaust so the ride reads as motion.
    const flamePulse = .82 + Math.sin(elapsed * 24) * .18;
    ctx.globalAlpha = flamePulse;
    ctx.fillStyle = "#fff29a";
    ctx.fillRect(-rocketWidth * .025, rocketHeight * .43, rocketWidth * .05, rocketHeight * .08);
    ctx.restore();
    return true;
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

  function drawHazard(hazard) {
    if (hazard.compound && hazard.wheelFrame) {
      drawFrame(hazard.wheelFrame, hazard.x, hazard.y, hazard.size);
      return;
    }
    drawSprite(hazard.spriteIndex, hazard.x, hazard.y, hazard.size);
  }

  function updateSpaceBoss(dt) {
    if (cameraY < spaceFade.end || !art.spaceBoss || !art.bossWheel) return;
    if (!spaceBoss) {
      bossWait -= dt;
      if (bossWait <= 0) {
        spaceBoss = { age: 0, x: width / 2, screenY: 145, nextShot: 3, shots: 0,
          shotLimit: 7 + Math.floor(Math.random() * 3), targetX: width * (.15 + Math.random() * .7),
          retargetAt: 0, leaveAt: Infinity };
      }
    }
    if (spaceBoss) {
      const boss = spaceBoss;
      boss.age += dt;
      if (boss.age >= boss.retargetAt || Math.abs(boss.x - boss.targetX) < 8) {
        boss.targetX = width * (.15 + Math.random() * .7);
        boss.retargetAt = boss.age + 1.5 + Math.random() * 2;
      }
      boss.x += clamp(boss.targetX - boss.x, -48 * dt, 48 * dt);
      boss.screenY = 145 + Math.sin(boss.age * 2) * 5;
      if (boss.age >= boss.nextShot && boss.shots < boss.shotLimit) {
        const screenY = boss.screenY + 40;
        bossShots.push({ x: boss.x, screenY, y: cameraY + height - screenY,
          vx: (Math.random() - .5) * 80, speed: 85 + Math.random() * 20 });
        boss.shots += 1;
        boss.nextShot = boss.age + 2.2 + Math.random() * 1.1;
        if (boss.shots === boss.shotLimit) boss.leaveAt = boss.age + 1.5;
      }
      if (boss.age >= boss.leaveAt) {
        spaceBoss = null;
        bossWait = 120 + Math.random() * 60;
      }
    }
    const shotWidth = 48;
    const shotHeight = spriteSize(art.bossWheel, shotWidth);
    let kept = 0;
    for (const shot of bossShots) {
      const previousY = shot.y;
      const previousX = shot.x;
      shot.x += shot.vx * dt;
      shot.screenY += shot.speed * dt;
      shot.y = cameraY + height - shot.screenY;
      // Sweep relative motion so fast rocket travel cannot skip a collision.
      const steps = Math.max(1, Math.ceil((Math.abs(player.vy) * dt + Math.abs(shot.y - previousY)) / 10));
      let hit = false;
      for (let step = 0; step <= steps; step += 1) {
        const t = step / steps;
        if (spriteOverlapsEllipse(art.bossWheel, previousX + (shot.x - previousX) * t, previousY + (shot.y - previousY) * t,
          shotWidth, shotHeight, player.x - player.vx * dt * (1 - t),
          player.y - player.vy * dt * (1 - t), player.width * .29, player.height * .34)) {
          hit = true;
          break;
        }
      }
      if (hit && invulnerableTimer <= 0) { endGame(); return; }
      if (!hit && shot.screenY < height + 60 && shot.x > -60 && shot.x < width + 60) bossShots[kept++] = shot;
    }
    bossShots.length = kept;
  }

  function drawSpaceBoss() {
    for (const shot of bossShots) drawFrame(art.bossWheel, shot.x, shot.y, 48);
    if (!spaceBoss || !art.spaceBoss) return;
    const boss = spaceBoss;
    const bossWidth = 90;
    const bossHeight = spriteSize(art.spaceBoss, bossWidth);
    ctx.save();
    ctx.globalAlpha = Math.max(0, Math.min(1, boss.age / .8, (boss.leaveAt - boss.age) / .8));
    ctx.drawImage(rasterSprite(art.spaceBoss, bossWidth, bossHeight),
      boss.x - bossWidth / 2, boss.screenY - bossHeight / 2, bossWidth, bossHeight);
    if (boss.shots < boss.shotLimit && boss.nextShot - boss.age < .7) {
      ctx.fillStyle = Math.sin(boss.age * 25) > 0 ? "#ffc779" : "#b75f50";
      ctx.fillRect(boss.x - 3, boss.screenY + bossHeight / 2, 6, 18);
    }
    ctx.restore();
  }

  function updateMarshals() {
    let kept = 0;
    for (const marshal of marshals) {
      const platform = marshal.platform;
      if (platform.y < cameraY - 80) continue;
      if (art.marshal && !marshal.collected && Math.abs(player.x - platform.x) < 45
        && Math.abs(player.y - (platform.y + 26)) < 48) {
        marshal.collected = true;
        marshalBonus += 50;
        bonusNoticeUntil = elapsed + 2;
      }
      if (!marshal.collected) marshals[kept++] = marshal;
    }
    marshals.length = kept;
  }

  function crossedLandingSurface(previousFeet, currentFeet, previousTop, currentTop, feetX, targetX, targetWidth, feetWidth) {
    const before = previousFeet - previousTop;
    const after = currentFeet - currentTop;
    return before >= 0 && after <= 0 && after < before
      && Math.abs(feetX - targetX) <= (targetWidth + feetWidth) / 2;
  }

  function collideWithEnemy(previousFeet, currentFeet, dt) {
    for (const enemy of enemies) {
      if (enemy.dead) continue;
      const targetEnemyWidth = enemyWidth();
      const enemyHeight = spriteSize(sprites[4], targetEnemyWidth);
      const enemyY = enemy.y + Math.sin(elapsed * 4 + enemy.phase) * 4;
      const horizontalReach = targetEnemyWidth / 2 + player.width * .31;
      const verticalReach = enemyHeight / 2 + player.height / 2 + Math.abs(player.vy) * dt + 4;
      if (Math.abs(player.x - enemy.x) > horizontalReach || Math.abs(player.y - enemyY) > verticalReach) continue;

      let enemyTop = enemyY + enemyHeight / 2;
      let crossedTop = false;
      if (player.vy < 0) {
        enemyTop = spriteTopAtX(sprites[4], enemy.x, enemyY, targetEnemyWidth, enemyHeight, player.x);
        const previousEnemyY = enemy.y + Math.sin((elapsed - dt) * 4 + enemy.phase) * 4;
        const previousTop = spriteTopAtX(sprites[4], enemy.x, previousEnemyY, targetEnemyWidth, enemyHeight, player.x);
        crossedTop = crossedLandingSurface(previousFeet, currentFeet, previousTop, enemyTop,
          player.x, enemy.x, targetEnemyWidth, player.width * .44);
      }
      const targetRx = player.width * .31;
      const targetRy = player.height * .37;
      const overlaps = spriteOverlapsEllipse(sprites[4], enemy.x, enemyY, targetEnemyWidth, enemyHeight,
        player.x, player.y, targetRx, targetRy);
      if (player.vy < 0 && crossedTop) {
        enemy.dead = true;
        frags += 1;
        player.y = enemyTop + player.height / 2;
        player.vy = 810;
        effects.push({ index: 7, x: enemy.x, y: enemyTop, age: 0, duration: .42, size: 42 * visualScale() });
        effects.push({ index: 10, x: enemy.x, y: enemyTop, age: 0, duration: .42, size: 56 * visualScale() });
        effects.push({ index: 10, x: enemy.x, y: enemyTop, age: 0, duration: .28, size: 42 * visualScale() });
        return true;
      }
      if (overlaps && invulnerableTimer <= 0) {
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
    const direction = Number(held.right) - Number(held.left);
    const targetVx = direction * Math.min(440, width * .62);
    player.vx += (targetVx - player.vx) * Math.min(1, 10 * dt);
    player.x += player.vx * dt;
    const halfPlayer = player.width / 2;
    if (player.x < -halfPlayer) player.x = width + halfPlayer;
    if (player.x > width + halfPlayer) player.x = -halfPlayer;

    const previousFeet = player.y - player.height / 2;
    player.vy -= 1240 * dt;
    if (adminSandbox && freeFlight) {
      invulnerableTimer = Math.max(invulnerableTimer, .1);
      if (player.vy <= 0) player.vy = 720;
    }
    if (rocketTimer > 0) player.vy = 1240;
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

    collideWithEnemy(previousFeet, currentFeet, dt);
    if (mode !== "running") return;

    if (player.vy < 0) {
      for (const platform of platforms) {
        // A platform that has already slipped below the visible playfield must
        // not catch the player off-screen. This prevents invisible landings at
        // the bottom edge after the camera has moved upward.
        if (platform.y < cameraY + 4) continue;
        if (platform.broken || previousFeet < platform.y || currentFeet > platform.y) continue;
        if (Math.abs(player.x - platform.x) > platform.hitboxWidth * .5 + player.width * .3) continue;
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
      if (!spriteOverlapsEllipse(hitbox.sprite, hitbox.x, hitbox.y, hitbox.width, hitbox.height,
        player.x, player.y, player.width * .32, player.height * .36)) continue;
      powerup.collected = true;
      if (powerup.type === "rocket") {
        rocketTimer = 1.8;
        invulnerableTimer = Math.max(invulnerableTimer, rocketTimer + 2);
        player.vy = 1240;
        effects.push({ index: 11, x: player.x, y: player.y - player.height * .42, age: 0, duration: .55, size: 66 * visualScale() });
      }
    }

    for (const hazard of hazards) {
      if (hazard.dead) continue;
      const previousHazardY = hazard.y;
      hazard.y -= hazard.speed * dt;
      const hitbox = hazardHitbox(hazard);
      const horizontalReach = Math.max(
        (hitbox.width + player.width * .44) / 2,
        hitbox.width / 2 + player.width * .29,
      );
      const verticalReach = hitbox.height / 2 + player.height / 2
        + (Math.abs(player.vy) + hazard.speed) * dt + 4;
      if (Math.abs(player.x - hitbox.x) > horizontalReach || Math.abs(player.y - hitbox.y) > verticalReach) continue;

      // Feet crossing the surface is sufficient: requiring torso overlap as
      // well misses shallow landings and lets a fast descent tunnel through.
      if (hazard.bouncy && player.vy < 0) {
        const hazardTop = spriteTopAtX(hitbox.sprite, hitbox.x, hitbox.y, hitbox.width, hitbox.height, player.x);
        const previousHazardTop = spriteTopAtX(hitbox.sprite, hitbox.x, previousHazardY, hitbox.width, hitbox.height, player.x);
        const crossedTop = crossedLandingSurface(previousFeet, currentFeet, previousHazardTop, hazardTop,
          player.x, hitbox.x, hitbox.width, player.width * .44);
        if (crossedTop) {
          hazard.dead = true;
          player.y = hazardTop + player.height / 2;
          player.vy = 880;
          effects.push({ index: 10, x: player.x, y: hazardTop, age: 0, duration: .34, size: 48 * visualScale() });
          continue;
        }
      }
      if (invulnerableTimer > 0) continue;
      const overlaps = spriteOverlapsEllipse(hitbox.sprite, hitbox.x, hitbox.y, hitbox.width, hitbox.height,
        player.x, player.y, player.width * .29, player.height * .34);
      if (overlaps) {
        endGame();
        return;
      }
    }

    let activeEffects = 0;
    for (let index = 0; index < effects.length; index += 1) {
      const effect = effects[index];
      effect.age += dt;
      if (effect.age < effect.duration && effect.y > cameraY - 140) effects[activeEffects++] = effect;
    }
    effects.length = activeEffects;
    if (player.vy > 260 && elapsed - trailTimer > .13) {
      effects.push({ index: 11, x: player.x, y: player.y - player.height * .38, age: 0, duration: .2, size: 46 * visualScale() });
      trailTimer = elapsed;
    }

    // Keep the racer in the lower-middle band: enough space remains above for
    // incoming platforms, while the player never hugs the bottom edge.
    if (player.y > cameraY + height * .42) cameraY = player.y - height * .42;
    updateSpaceBoss(dt);
    if (mode !== "running") return;
    updateMarshals();
    extendWorld();
    pruneWorldObjects(platforms, 160, "broken");
    pruneWorldObjects(enemies, 130, "dead");
    pruneWorldObjects(hazards, 180, "dead");
    pruneWorldObjects(powerups, 180, "collected");

    if (player.y + player.height / 2 < cameraY - 6) {
      endGame();
      return;
    }
    if (elapsed >= nextHudUpdate) {
      updateHud();
      nextHudUpdate = elapsed + .1;
    }
  }

  function draw() {
    if (!ctx) return;
    drawBackdrop();

    for (const platform of platforms) {
      if (platform.broken) continue;
      drawSprite(platform.spriteIndex, platform.x, platform.y, platform.spriteWidth, "platform", platform.height);
    }
    for (const enemy of enemies) {
      if (enemy.dead) continue;
      const bobY = enemy.y + Math.sin(elapsed * 4 + enemy.phase) * 4;
      drawSprite(4, enemy.x, bobY, enemyWidth());
    }

    for (const hazard of hazards) {
      if (!hazard.dead) drawHazard(hazard);
    }
    drawSpaceBoss();
    if (art.marshal) {
      for (const marshal of marshals) {
        const h = 58;
        drawFrame(art.marshal, marshal.platform.x, marshal.platform.y + h / 2,
          h * art.marshal.sw / art.marshal.sh, "center", h);
      }
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
      if (rocketTimer > 0 && drawRocketRide()) {
        drawInvulnerabilityShield();
      } else {
        const screenY = worldToScreen(player.y);
        ctx.save();
        ctx.translate(player.x, screenY);
        ctx.rotate(Math.max(-.08, Math.min(.08, -player.vx / Math.max(1, width) * .1)));
        ctx.scale(facing, 1);
        const heroSprite = currentHeroSprite();
        if (heroSprite) {
          const heroDrawWidth = player.height * heroSprite.sw / heroSprite.sh;
          ctx.drawImage(rasterSprite(heroSprite, heroDrawWidth, player.height),
            -heroDrawWidth / 2, -player.height / 2, heroDrawWidth, player.height);
        } else {
          ctx.fillStyle = "#f4d43e";
          ctx.beginPath();
          ctx.ellipse(0, 0, player.width * .43, player.height * .47, 0, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.restore();
        drawInvulnerabilityShield();
      }
    }

    if (mode === "running") {
      if (elapsed < bonusNoticeUntil) {
        ctx.save();
        ctx.fillStyle = "#fff0b4";
        ctx.font = "bold 14px system-ui";
        ctx.textAlign = "center";
        ctx.fillText("КЛЕТЧАТЫЙ ФЛАГ  +50", width / 2, height * .34);
        ctx.restore();
      }
      const progress = Math.max(0, Math.floor((peakY - 86) / 11));
      ctx.save();
      ctx.fillStyle = "rgba(249, 251, 255, .72)";
      ctx.font = "800 11px system-ui, sans-serif";
      ctx.textAlign = "right";
      ctx.fillText(`${progress} м`, width - 14, 22);
      if (rocketTimer > 0) {
        ctx.textAlign = "left";
        ctx.fillStyle = "rgba(8, 18, 38, .86)";
        ctx.fillRect(12, 88, Math.min(width * .45, 170), 22);
        ctx.fillStyle = "#ffbd4a";
        ctx.font = "900 10px 'Courier New', monospace";
        ctx.fillText(`РАКЕТА  ${rocketTimer.toFixed(1)}с`, 20, 103);
      }
      ctx.restore();
    }
  }

  function loop(now) {
    if (mode !== "running") return;
    if (document.hidden) {
      previousTime = now;
      updateAccumulator = 0;
      frame = requestAnimationFrame(loop);
      return;
    }
    const dt = Math.min(.05, Math.max(.001, (now - previousTime) / 1000));
    previousTime = now;
    updateAccumulator = Math.min(.1, updateAccumulator + dt);
    const fixedStep = 1 / 60;
    while (updateAccumulator >= fixedStep && mode === "running") {
      update(fixedStep);
      updateAccumulator -= fixedStep;
    }
    const renderInterval = 1000 / 60;
    if (now - lastRenderTime >= renderInterval - .5 || mode !== "running") {
      draw();
      lastRenderTime += renderInterval * Math.max(1,
        Math.floor((now - lastRenderTime + .5) / renderInterval));
    }
    if (mode === "running") frame = requestAnimationFrame(loop);
  }

  function resize() {
    const bounds = wrap.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const nextViewportKey = `${bounds.width}:${bounds.height}:${window.devicePixelRatio}:${artReady}`;
    if (nextViewportKey === viewportKey) return;
    viewportKey = nextViewportKey;
    const previousWidth = width;
    const previousHeight = height;
    // Keep horizontal world geometry stable; reveal more/less vertical scenery
    // to fill the viewport with one uniform scale, never stretching sprites.
    width = logicalViewportWidth;
    height = width * bounds.height / bounds.width;
    // Render above CSS resolution on high-density screens while keeping fill
    // rate bounded: mobile gets extra sprite detail, desktop stays economical.
    const maxDpr = logicalViewportWidth === 390 ? 3 : 2;
    dpr = bounds.width / width * Math.min(maxDpr, Math.max(1, window.devicePixelRatio || 1));
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.imageSmoothingEnabled = false;
    rasterCache = new WeakMap();
    if (!artReady) {
      drawBackdrop();
      return;
    }
    touchBounds = null;
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
        platform.hitboxWidth *= scaleX;
        platform.spriteWidth *= scaleX;
        platform.height *= scaleY;
        platform.range *= scaleX;
      });
      enemies.forEach((enemy) => { enemy.x *= scaleX; enemy.baseX *= scaleX; enemy.y *= scaleY; });
      hazards.forEach((hazard) => { hazard.x *= scaleX; hazard.y *= scaleY; hazard.size *= scaleX; hazard.speed *= scaleY; });
      powerups.forEach((powerup) => { powerup.x *= scaleX; powerup.y *= scaleY; powerup.size *= scaleX; });
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
  function releaseTouchControls() {
    touchPointers.clear();
    touchDirection = null;
    clearDirections();
  }
  window.addEventListener("blur", releaseTouchControls);
  document.addEventListener("visibilitychange", () => {
    releaseTouchControls();
    previousTime = performance.now();
    lastRenderTime = previousTime;
    updateAccumulator = 0;
  });
  startButton.addEventListener("click", startGame);
  if (adminSandbox && flightButton) {
    flightButton.addEventListener("click", () => {
      freeFlight = !freeFlight;
      flightButton.setAttribute("aria-pressed", String(freeFlight));
      flightButton.textContent = `Свободный полёт: ${freeFlight ? "вкл." : "выкл."}`;
      if (freeFlight && mode !== "running") startGame();
      if (freeFlight && player) player.vy = 720;
      canvas.focus({ preventScroll: true });
    });
  }
  fullscreenButton.addEventListener("click", toggleFullscreen);
  document.addEventListener("fullscreenchange", handleFullscreenChange);
  document.addEventListener("webkitfullscreenchange", handleFullscreenChange);

  function syncTouchControls() {
    let direction = null;
    for (const value of touchPointers.values()) direction = value;
    clearDirections();
    touchDirection = direction;
    if (direction) setDirection(direction, true);
  }

  // Restrict Safari's copy/callout suppression to the game, leaving the rest
  // of the page and normal buttons accessible.
  wrap.addEventListener("contextmenu", (event) => event.preventDefault());
  wrap.addEventListener("selectstart", (event) => event.preventDefault());
  canvas.addEventListener("touchstart", (event) => event.preventDefault(), { passive: false });
  canvas.addEventListener("touchmove", (event) => event.preventDefault(), { passive: false });
  canvas.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse") return;
    event.preventDefault();
    const bounds = touchBounds = canvas.getBoundingClientRect();
    touchDirection = event.clientX < bounds.left + bounds.width / 2 ? "left" : "right";
    touchPointers.set(event.pointerId, touchDirection);
    syncTouchControls();
    canvas.setPointerCapture?.(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!touchPointers.has(event.pointerId) || event.pointerType === "mouse") return;
    event.preventDefault();
    const bounds = touchBounds || (touchBounds = canvas.getBoundingClientRect());
    const direction = event.clientX < bounds.left + bounds.width / 2 ? "left" : "right";
    if (direction === touchPointers.get(event.pointerId)) return;
    touchPointers.set(event.pointerId, direction);
    syncTouchControls();
  });
  ["pointerup", "pointercancel", "lostpointercapture"].forEach((type) => {
    canvas.addEventListener(type, (event) => {
      if (!touchPointers.has(event.pointerId)) return;
      touchPointers.delete(event.pointerId);
      syncTouchControls();
    });
  });

  Promise.all([
    image(canvas.dataset.atlasSrc),
    image(canvas.dataset.heroSheetSrc),
    image(canvas.dataset.backgroundJourneySrc),
    image(canvas.dataset.backgroundCloudSrc),
    image(canvas.dataset.backgroundSpaceSrc),
    image(canvas.dataset.rocketSrc),
    image(canvas.dataset.rocketEmptySrc),
    image(canvas.dataset.wheelCompoundsSrc),
    image(canvas.dataset.platformSheetSrc),
    image(canvas.dataset.spaceBossSrc),
    image(canvas.dataset.bossWheelSrc),
    image(canvas.dataset.marshalSrc),
  ]).then(([atlas, heroSheet, journey, cloud, space, rocketRide, rocketEmpty, wheelSheet, platformSheet, spaceBossImage, bossWheelImage, marshalImage]) => {
    art.marshal = splitSpriteSheet(marshalImage, 1)[0] || null;
    art.spaceBoss = splitSpriteSheet(spaceBossImage, 1)[0] || null;
    art.bossWheel = splitSpriteSheet(bossWheelImage, 1)[0] || null;
    art.journey = journey;
    art.cloud = cloud;
    art.space = space;
    art.heroFrames = splitHeroSheet(heroSheet);
    const wheelFrames = splitSpriteSheet(wheelSheet, 3);
    art.wheelFrames = {
      soft: wheelFrames[0] || null,
      medium: wheelFrames[1] || null,
      hard: wheelFrames[2] || null,
    };
    art.rocketRide = bakeSprite(splitSpriteSheet(rocketRide, 1)[0], 768);
    if (art.heroFrames.length !== 4) {
      copy.textContent = "Не удалось загрузить анимацию персонажа. Обновите страницу и попробуйте ещё раз.";
      startButton.disabled = true;
      return;
    }
    cropSprites(atlas);
    // Cut in the transparent gutters, not through the generated artwork.
    const platformFrames = splitSpriteSheet(platformSheet, 4, [0, .26, .536, .806, 1]);
    platformFrames.forEach((sprite, index) => { if (sprite) sprites[index] = sprite; });
    for (let index = 0; index < sprites.length; index += 1) sprites[index] = bakeSprite(sprites[index]);
    // Keep more source detail for the hero; the other game sprites stay small
    // to keep the per-frame draw workload light on mobile.
    // Retain full-resolution hero poses; rasterSprite prepares display-sized
    // textures directly, avoiding the former intermediate 384px reduction.
    for (const compound of ["soft", "medium", "hard"]) {
      art.wheelFrames[compound] = bakeSprite(art.wheelFrames[compound]);
    }
    art.powerupFrames = { rocket: bakeSprite(splitSpriteSheet(rocketEmpty, 1)[0], 384) };
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
