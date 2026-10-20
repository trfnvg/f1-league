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
  const introSkipButton = document.getElementById("doodle-intro-skip");
  const introPreferenceButton = document.getElementById("doodle-intro-preference");
  const introPreferenceState = document.getElementById("doodle-intro-preference-state");
  const introCaption = document.getElementById("doodle-intro-caption");
  const scoreNode = document.getElementById("doodle-score");
  const bestNode = document.getElementById("doodle-best");
  const levelNode = document.getElementById("doodle-level");
  const levelNameNode = document.getElementById("doodle-level-name");
  const fullscreenButton = document.getElementById("doodle-fullscreen-toggle");
  const leaderboardNode = document.getElementById("doodle-leaderboard-list");
  const totalAttemptsNode = document.getElementById("doodle-total-attempts");
  const csrfToken = document.querySelector("#doodle-csrf-form [name=csrfmiddlewaretoken]")?.value || "";
  const bestStorageKey = "f1-doodle-gp-best-v1";
  const introStorageKey = "f1-cowboy-skip-intro-v1";
  let alwaysSkipIntro = false;
  try { alwaysSkipIntro = localStorage.getItem(introStorageKey) === "1"; } catch (error) { /* Session-only preference if storage is disabled. */ }
  function syncIntroPreference() {
    introPreferenceButton?.setAttribute("aria-pressed", String(alwaysSkipIntro));
    if (introPreferenceState) introPreferenceState.textContent = alwaysSkipIntro ? "Вкл." : "Выкл.";
  }
  syncIntroPreference();
  const art = {};
  const adminSandbox = canvas.dataset.adminFlight === "1";
  const flightButton = document.getElementById("doodle-flight-toggle");
  const bossTestButton = document.getElementById("doodle-boss-test");
  const bossTestStatus = document.getElementById("doodle-boss-test-status");
  let adminBossTestMode = false;
  let freeFlight = false;
  const logicalViewportWidth = window.matchMedia("(max-width: 760px), (hover: none) and (pointer: coarse)").matches ? 390 : 600;
  // Physical screen geometry is independent of page/pinch zoom. Keep the
  // mobile world viewport stable, and cover CSS bounds with the same uniform scale.
  const mobileWorldAspect = clamp((window.screen?.height || 844) / (window.screen?.width || 390), 1.4, 2.5);
  let rasterCache = new WeakMap();
  let sceneryCache = new WeakMap();
  let viewportKey = "";
  const held = { left: false, right: false };
  const sprites = [];
  let skyGradient = null;
  let garageCache = null;
  let winterSeamCache = null;
  let waitingForStage = null;
  let forgottenPaddock = false;
  let antarctica = false;
  let antarcticaScene = null;
  let antarcticaArrival = null;
  const controlSceneDuration = 11.2;
  const caveSceneDuration = 9.8;
  let antarcticaEntryY = 0;
  let antarcticaEntryScore = 0;
  let winterMemoryStartedAt = null;
  let winterEncounter = null;
  let winterProjectiles = [];
  let winterEncounterWait = 8;
  let winterEnemyIndex = -1;
  let winterSlide = 0;
  let winterWind = 0;
  let winterWindDirection = 0;
  let sidBoss = null;
  let sidBossCleared = false;
  let summit = false;
  let summitEntryY = 0;
  let summitCommentator = null;
  let summitCommentatorNextY = 0;
  let summitPlatformIndex = 0;
  let summitGoatNextY = 0;
  let summitRareLastY = -Infinity;
  let summitEncounter = null;
  let summitShots = [];
  let summitEnemyNextY = 0;
  let summitEnemyLastType = "drone";
  const winterMemoryQuote = "Whenever anything is not going his way, he lashes out with unnecessary anger and borderline violence";
  let winterQuoteLayout = null;
  let portalTransition = null;
  let arrivalUntil = 0;
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
  let visibleWorldHeight = 1;
  let dpr = 1;
  let mode = "ready";
  let intro = null;
  const introDuration = 5.3;
  let artReady = false;
  let assetLoadFailed = false;
  let frame = 0;
  let previousTime = 0;
  let updateAccumulator = 0;
  let elapsed = 0;
  let player;
  let platforms = [];
  let enemies = [];
  let hazards = [];
  let hawks = [];
  let skyFlock = null;
  let totoCloud = null;
  let skyFlockWait = 4;
  let totoCloudWait = 7;
  let hawkSpawnWait = 2 + Math.random() * 2;
  let spaceBoss = null;
  let spaceEncounter = null;
  let spaceEncounterWait = 7;
  let spaceEncounterIndex = -1;
  let spacePitHold = null;
  let softBootJumps = 0;
  let bossShots = [];
  let guaranteedSpaceBossSpawned = false;
  let bossBonus = 0;
  let bossVictoryUntil = 0;
  let marshals = [];
  let nextMarshalY = 1800;
  let marshalBonus = 0;
  let bonusNoticeUntil = 0;
  let bossWait = 90 + Math.random() * 60;
  let powerups = [];
  let effects = [];
  let cameraY = 0;
  let openingJump = true;
  let somersault = null;
  let nextSomersaultAt = 2;
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
  let babyKimi = null;
  let kimiWait = 15;
  let kimiBoost = 0;
  let lastEnemyVariant = -1;
  let lastPowerupSpawnY = -Infinity;
  let attemptId = null;
  let scoreSubmitted = false;
  let pendingFinish = false;

  bestNode.textContent = String(best);
  startButton.disabled = true;

  const image = (src) => new Promise((resolve) => {
    if (!src) { resolve(null); return; }
    const load = (attempt) => {
      const img = new Image();
      img.decoding = "async";
      let finished = false;
      let timeout;
      const failed = () => {
        if (finished) return;
        finished = true;
        clearTimeout(timeout);
        img.onload = img.onerror = null;
        if (attempt < 2) setTimeout(() => load(attempt + 1), 350 * (attempt + 1));
        else resolve(null);
      };
      img.onerror = failed;
      img.onload = async () => {
        try {
          if (img.decode) await img.decode();
          if (!img.naturalWidth || !img.naturalHeight) { failed(); return; }
          if (finished) return;
          finished = true;
          clearTimeout(timeout);
          img.onload = img.onerror = null;
          resolve(img);
        } catch (error) { failed(); }
      };
      timeout = setTimeout(failed, 20000);
      img.src = attempt ? `${src}${src.includes("?") ? "&" : "?"}asset_retry=${attempt}` : src;
    };
    load(0);
  });

  // Download only the current chapter. Each chapter is published atomically:
  // simulation never encounters partially prepared sprites or collision masks.
  const assetStages = new Map();
  const stageNames = { sky: "Облака", space: "Космос", garage: "Забытый паддок", winter: "Антарктида", summit: "Высокогорный паддок" };
  const yieldAssetWork = () => new Promise((resolve) => {
    if (window.requestIdleCallback) window.requestIdleCallback(resolve, { timeout: 250 });
    else setTimeout(resolve, 0);
  });

  async function prepareAssets(entries) {
    const images = await Promise.all(entries.map(([key]) => image(canvas.dataset[key])));
    if (images.some((loaded) => !loaded)) throw new Error("Incomplete game artwork");
    const prepared = {};
    for (let i = 0; i < entries.length; i += 1) {
      await yieldAssetWork();
      Object.assign(prepared, entries[i][1](images[i]));
    }
    return prepared;
  }

  function loadStage(name) {
    let stage = assetStages.get(name);
    if (stage?.ready) return Promise.resolve(true);
    if (stage?.pending) return stage.pending;
    if (stage && performance.now() < stage.retryAt) return Promise.resolve(false);
    if (!stage) { stage = { ready: false, pending: null, retryAt: 0 }; assetStages.set(name, stage); }
    stage.pending = prepareAssets(stageAssets(name)).then((prepared) => {
      Object.assign(art, prepared);
      stage.ready = true;
      return true;
    }).catch(() => {
      stage.retryAt = performance.now() + 3000;
      return false;
    }).finally(() => { stage.pending = null; });
    return stage.pending;
  }

  function stageReady(name) {
    if (assetStages.get(name)?.ready) return true;
    loadStage(name);
    waitingForStage = name;
    return false;
  }

  function streamWorldAssets() {
    waitingForStage = null;
    if (summit) return stageReady("summit");
    if (antarctica || antarcticaScene || antarcticaArrival) {
      if (runScore() >= 9700) loadStage("summit");
      return stageReady("winter");
    }
    if (portalTransition) return stageReady("garage");
    const score = runScore();
    if (forgottenPaddock) {
      if (!stageReady("garage")) return false;
      if (score >= 6500) loadStage("winter");
      return score < 7900 || stageReady("winter");
    }
    // Prefetch well ahead of the first visible pixel/encounter. Fast admin
    // flights still hit readiness barriers, without advancing the game clock.
    if (cameraY >= 1200) loadStage("sky");
    if (cameraY >= 7000) loadStage("space");
    if (score >= 4000) loadStage("garage");
    if (cameraY >= 2700 && !stageReady("sky")) return false;
    if (cameraY >= 10000 && !stageReady("space")) return false;
    if (score >= 4900 && !stageReady("garage")) return false;
    return true;
  }

  async function preparePreview(names) {
    if (bossTestStatus) bossTestStatus.textContent = "Загружаем графику для теста…";
    const ready = (await Promise.all(names.map(loadStage))).every(Boolean);
    if (!ready && bossTestStatus) bossTestStatus.textContent = "Графика не загрузилась. Проверьте соединение и повторите тест.";
    return ready;
  }

  function showAssetError() {
    assetLoadFailed = true;
    artReady = false;
    title.textContent = "Игра не загрузилась";
    copy.textContent = "Не удалось загрузить графику. Проверьте соединение и повторите загрузку.";
    startButton.textContent = "Повторить загрузку";
    startButton.disabled = false;
    overlay.classList.remove("is-hidden");
  }

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
  // collision checks touch only nearby cells of this 64x64 mask.
  function alphaMask(pixels, stride, x, y, spriteWidth, spriteHeight, columns = 64, rows = 64) {
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
    const poses = splitSpriteSheet(sheet, 4, [0, .251, .486, .787, 1], false);
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

  function storyFrames(sheet, count, boundaries = null) {
    const poses = splitSpriteSheet(sheet, count, boundaries, false);
    if (poses.length !== count || poses.some((pose) => !pose)) return [];
    const cellWidth = Math.max(...poses.map((pose) => pose.sw));
    const cellHeight = Math.max(...poses.map((pose) => pose.sh));
    return poses.map((pose) => {
      const tile = document.createElement("canvas");
      tile.width = cellWidth;
      tile.height = cellHeight;
      const painter = tile.getContext("2d");
      painter.imageSmoothingEnabled = false;
      painter.drawImage(pose.image, pose.sx, pose.sy, pose.sw, pose.sh,
        Math.round((cellWidth - pose.sw) / 2), cellHeight - pose.sh, pose.sw, pose.sh);
      return { image: tile, sx: 0, sy: 0, sw: cellWidth, sh: cellHeight };
    });
  }

  function walkFrames(sheet) {
    const poses = splitSpriteSheet(sheet, 8, null, false);
    if (poses.length !== 8 || poses.some((pose) => !pose)) return [];
    const anchors = poses.map((pose) => {
      const rows = Math.max(1, Math.floor(pose.sh * .28));
      const data = pose.image.getContext("2d").getImageData(pose.sx, pose.sy, pose.sw, rows).data;
      let left = pose.sw, right = 0;
      for (let y = 0; y < rows; y += 1) for (let x = 0; x < pose.sw; x += 1) {
        if (data[(y * pose.sw + x) * 4 + 3] <= 18) continue;
        left = Math.min(left, x); right = Math.max(right, x);
      }
      return (left + right) / 2;
    });
    const w = Math.ceil(2 * Math.max(...poses.map((pose, i) => Math.max(anchors[i], pose.sw - anchors[i]))));
    const h = Math.max(...poses.map((pose) => pose.sh));
    return poses.map((pose, i) => {
      const tile = document.createElement("canvas"); tile.width = w; tile.height = h;
      tile.getContext("2d").drawImage(pose.image, pose.sx, pose.sy, pose.sw, pose.sh,
        Math.round(w / 2 - anchors[i]), h - pose.sh, pose.sw, pose.sh);
      return { image: tile, sx: 0, sy: 0, sw: w, sh: h };
    });
  }

  function piranhaFrames(sheet) {
    const poses = splitSpriteSheet(sheet, 4, null, false);
    if (poses.length !== 4 || poses.some((pose) => !pose)) return [];
    // Align on the red mouth, not the wing bounds: flapping must not move the
    // fish body or its collision ellipse between animation frames.
    const anchors = poses.map((pose) => {
      const pixels = pose.image.getContext("2d").getImageData(pose.sx, pose.sy, pose.sw, pose.sh).data;
      let left = pose.sw, right = 0, top = pose.sh, bottom = 0;
      for (let y = 0; y < pose.sh; y += 1) for (let x = 0; x < pose.sw; x += 1) {
        const at = (y * pose.sw + x) * 4;
        if (pixels[at + 3] < 100 || pixels[at] < 90 || pixels[at] < pixels[at + 1] * 1.5 || pixels[at] < pixels[at + 2] * 1.4) continue;
        left = Math.min(left, x); right = Math.max(right, x); top = Math.min(top, y); bottom = Math.max(bottom, y);
      }
      return { x: right + (right - left) * .65, y: (top + bottom) / 2 - (bottom - top) * .08 };
    });
    const w = Math.ceil(2 * Math.max(...poses.map((p, i) => Math.max(anchors[i].x, p.sw - anchors[i].x))));
    const h = Math.ceil(2 * Math.max(...poses.map((p, i) => Math.max(anchors[i].y, p.sh - anchors[i].y))));
    return poses.map((pose, i) => {
      const tile = document.createElement("canvas"); tile.width = w; tile.height = h;
      tile.getContext("2d").drawImage(pose.image, pose.sx, pose.sy, pose.sw, pose.sh,
        Math.round(w / 2 - anchors[i].x), Math.round(h / 2 - anchors[i].y), pose.sw, pose.sh);
      return { image: tile, sx: 0, sy: 0, sw: w, sh: h };
    });
  }

  function cleanSpriteContour(data, w, h) {
    // Generated sheets can contain isolated specks or fragments of the next
    // cell. Retain the main connected silhouette before cropping AND masking.
    const labels = new Uint32Array(w * h), queue = new Uint32Array(w * h);
    let label = 0, largest = 0, largestSize = 0;
    for (let p = 0; p < labels.length; p += 1) {
      if (labels[p] || data[p * 4 + 3] <= 18) continue;
      label += 1;
      let head = 0, tail = 1;
      queue[0] = p; labels[p] = label;
      while (head < tail) {
        const at = queue[head++], x = at % w, y = Math.floor(at / w);
        for (let dy = -1; dy <= 1; dy += 1) {
          for (let dx = -1; dx <= 1; dx += 1) {
            const nx = x + dx, ny = y + dy;
            if (nx < 0 || nx >= w || ny < 0 || ny >= h) continue;
            const next = ny * w + nx;
            if (labels[next] || data[next * 4 + 3] <= 18) continue;
            labels[next] = label; queue[tail++] = next;
          }
        }
      }
      if (tail > largestSize) { largestSize = tail; largest = label; }
    }
    for (let p = 0; p < labels.length; p += 1) {
      if (labels[p] === largest && largest) continue;
      // Keep the source's translucent one-pixel antialiasing edge only when
      // directly adjoining the main silhouette, never another opaque island.
      const alpha = data[p * 4 + 3];
      let edge = false;
      if (alpha > 0 && alpha <= 18 && largest) {
        const x = p % w, y = Math.floor(p / w);
        for (let dy = -1; dy <= 1 && !edge; dy += 1)
          for (let dx = -1; dx <= 1; dx += 1) {
            const nx = x + dx, ny = y + dy;
            if (nx >= 0 && nx < w && ny >= 0 && ny < h && labels[ny * w + nx] === largest) edge = true;
          }
      }
      if (!edge) data[p * 4 + 3] = 0;
    }
  }

  function splitSpriteSheet(sheet, columns, boundaries = null, needsMask = true, cleanContour = false) {
    if (!sheet || !columns) return [];
    const frameHeight = sheet.naturalHeight;
    const frames = [];
    for (let frameIndex = 0; frameIndex < columns; frameIndex += 1) {
      const startX = Math.round((boundaries ? boundaries[frameIndex] : frameIndex / columns) * sheet.naturalWidth);
      const endX = Math.round((boundaries ? boundaries[frameIndex + 1] : (frameIndex + 1) / columns) * sheet.naturalWidth);
      const frameWidth = endX - startX;
      // Keep each frame on its own immutable surface. In particular, do not
      // reuse a canvas backing store while WebKit may still be reading it.
      const tile = document.createElement("canvas");
      tile.width = frameWidth;
      tile.height = frameHeight;
      const tileCtx = tile.getContext("2d", { willReadFrequently: true });
      tileCtx.imageSmoothingEnabled = false;
      tileCtx.drawImage(sheet, startX, 0,
        endX - startX, frameHeight, 0, 0, frameWidth, frameHeight);
      let pixels;
      if (cleanContour) {
        const imageData = tileCtx.getImageData(0, 0, frameWidth, frameHeight);
        pixels = imageData.data;
        cleanSpriteContour(pixels, frameWidth, frameHeight);
        tileCtx.putImageData(imageData, 0, 0);
      } else pixels = tileCtx.getImageData(0, 0, frameWidth, frameHeight).data;
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
      if (maxX < minX || maxY < minY) { frames.push(null); continue; }
      const mask = needsMask ? alphaMask(pixels, frameWidth, minX, minY, sw, sh) : null;
      // Keep precisely the original pixels, but discard transparent margins
      // from retained canvas surfaces (especially large cinematic sheets).
      const cropped = document.createElement("canvas");
      cropped.width = sw;
      cropped.height = sh;
      cropped.getContext("2d").drawImage(tile, minX, minY, sw, sh, 0, 0, sw, sh);
      frames.push({ image: cropped, sx: 0, sy: 0, sw, sh, mask, sourceX: minX, sourceY: minY });
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
    if (sidBoss?.phase === "victory") return frames[sidBoss.timer < 1.15 ? 3 : sidBoss.timer < 4.6 ? 1 : 2];

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
    // Cinematic zooms can request a new size every frame. Keep their original
    // cropped pixels instead of continuously allocating and evicting textures.
    if (sizes.size >= 8) {
      if (!sizes.has("source")) {
        const original = document.createElement("canvas");
        original.width = sprite.sw;
        original.height = sprite.sh;
        original.getContext("2d").drawImage(sprite.image, sprite.sx, sprite.sy,
          sprite.sw, sprite.sh, 0, 0, sprite.sw, sprite.sh);
        sizes.set("source", original);
      }
      return sizes.get("source");
    }
    const texture = document.createElement("canvas");
    texture.width = pixelWidth;
    texture.height = pixelHeight;
    const painter = texture.getContext("2d");
    painter.imageSmoothingEnabled = true;
    painter.imageSmoothingQuality = "high";
    painter.drawImage(sprite.image, sprite.sx, sprite.sy, sprite.sw, sprite.sh,
      0, 0, pixelWidth, pixelHeight);
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
    winterSeamCache = null;
    skyGradient = ctx.createLinearGradient(0, 0, 0, height);
    skyGradient.addColorStop(0, "#498bc9");
    skyGradient.addColorStop(1, "#89bddc");
    // Keep scenery in decoded images. Large mirrored canvas copies consumed
    // tens of MB on Retina screens and could lose their backing store on iOS.
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
    if (!art.space || alpha <= 0) return;
    const tileHeight = width * art.space.naturalHeight / art.space.naturalWidth;
    if (!tileHeight) return;
    const cycle = tileHeight * 2;
    // The scenery drifts DOWN as the player climbs, at a slower parallax rate.
    const offset = Math.max(0, climb - spaceFade.start) * .045 % cycle;
    ctx.globalAlpha = alpha;
    for (let y = offset - cycle; y < height; y += cycle) {
      // Align to physical pixels and overlap one pixel: fractional canvas
      // sampling must never expose the bright sky underneath adjacent tiles.
      const top = Math.floor(y * dpr) / dpr;
      const middle = Math.ceil((y + tileHeight) * dpr) / dpr;
      const bottom = Math.ceil((y + cycle) * dpr) / dpr;
      if (middle >= 0 && top < height) {
        ctx.drawImage(art.space, 0, top, width, middle - top + 1 / dpr);
      }
      if (bottom >= 0 && middle < height) {
        ctx.save();
        ctx.translate(0, bottom);
        ctx.scale(1, -1);
        ctx.drawImage(art.space, 0, 0, width, bottom - middle + 1 / dpr);
        ctx.restore();
      }
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

  // Repeated transparent cloud art is much wider than its on-screen size.
  // Scale once per viewport at full backing-store resolution, not every frame.
  // Keep this separate from animated sprite caches and retain original assets.
  function drawCloud(x, y, w, h) {
    if (y + h < 0 || y > height || x + w < 0 || x > width) return;
    let sizes = sceneryCache.get(art.cloud);
    if (!sizes) { sizes = new Map(); sceneryCache.set(art.cloud, sizes); }
    const pw = Math.max(1, Math.ceil(w * dpr));
    const ph = Math.max(1, Math.ceil(h * dpr));
    const key = `${pw}:${ph}`;
    let texture = sizes.get(key);
    if (!texture) {
      texture = document.createElement("canvas");
      texture.width = pw; texture.height = ph;
      const painter = texture.getContext("2d");
      painter.imageSmoothingEnabled = false;
      painter.drawImage(art.cloud, 0, 0, pw, ph);
      sizes.set(key, texture);
    }
    ctx.drawImage(texture, x, y, w, h);
  }

  function drawBackdrop() {
    if (summit) { drawSummitBackdrop(); return; }
    if (antarctica) { drawAntarctica(); return; }
    if (forgottenPaddock) {
      drawForgottenPaddock();
      return;
    }
    const climb = Math.max(0, cameraY);
    const intoSky = backgroundFade(climb, skyFade.start, skyFade.end);
    const intoSpace = backgroundFade(climb, spaceFade.start, spaceFade.end);
    // Always repaint the base, including on WebKit and during scene fades.
    // Cached scenery must never be relied upon to erase the previous frame.
    ctx.fillStyle = skyGradient || "#6ba5d3";
    ctx.fillRect(0, 0, width, height);
    if (art.journey && intoSky < 1) {
      const source = art.journey;
      const view = backgroundView(climb, source.naturalWidth, source.naturalHeight, width, height);
      ctx.globalAlpha = 1 - intoSky;
      ctx.drawImage(source, 0, view.y, source.naturalWidth, view.height, 0, 0, width, height);
    }
    drawSpaceBackdrop(climb, intoSpace);
    // Separate cloud sprites cross the screen downward. Their wrap happens
    // entirely outside the viewport, so infinite sky has no image seam. They
    // gradually give way to space rather than ending at a hard level boundary.
    const cloudsAlpha = backgroundFade(climb, 2800, skyFade.end) * (1 - intoSpace);
    if (art.cloud && cloudsAlpha > 0) {
      for (let i = 0; i < 6; i += 1) {
        const cloudWidth = width * (.38 + (i % 3) * .12);
        const cloudHeight = cloudWidth * art.cloud.naturalHeight / art.cloud.naturalWidth;
        const cycle = height + 2 * cloudHeight + 40;
        const y = ((i / 6 * cycle + climb * (.09 + (i % 3) * .025)) % cycle) - cloudHeight - 20;
        const x = (i % 2 ? width - cloudWidth * .72 : -cloudWidth * .28)
          + Math.sin(elapsed * .12 + i) * width * .015;
        ctx.globalAlpha = cloudsAlpha * (.3 + (i % 3) * .12);
        drawCloud(x, y, cloudWidth, cloudHeight);
      }
    }
    drawSpaceDecor(climb, intoSpace);
    ctx.globalAlpha = 1;
    drawTotoCloud();
  }

  function worldToScreen(worldY) {
    return height - (worldY - cameraY);
  }

  function runScore() {
    return Math.max(0, Math.floor((peakY - startY) / 11)) + frags * 30 + marshalBonus + bossBonus;
  }

  function beginPortal() {
    if (forgottenPaddock || portalTransition || !player) return;
    resetSpaceEncounters(false);
    portalTransition = { age: 0, x: player.x / width, y: worldToScreen(player.y) / height };
    rocketTimer = 0;
    somersault = null;
    openingJump = false;
    invulnerableTimer = Math.max(invulnerableTimer, 6);
    spaceBoss = null;
    bossShots = [];
  }

  function updatePortal(dt) {
    if (!portalTransition) return false;
    portalTransition.age += dt;
    if (portalTransition.age >= 3) {
      portalTransition = null;
      forgottenPaddock = true;
      arrivalUntil = elapsed + 4;
      hazards = [];
      enemies = [];
      hawks = []; skyFlock = null; totoCloud = null;
      powerups = []; marshals = []; effects = [];
      invulnerableTimer = 3;
      // A fresh, reachable landing ladder replaces the old space platforms.
      // Hold the racer on its broad starting pad while the fade clears.
      platforms = [];
      const landingY = cameraY + height * .24;
      const pad = addPlatform(landingY, width / 2, "normal");
      pad.width = pad.hitboxWidth = pad.spriteWidth = width * .58;
      let y = landingY, x = width / 2;
      while (y < cameraY + height + 420) {
        y += 115;
        x = choosePlatformX(x, 115);
        addPlatform(y, x, "normal");
      }
      worldTop = y;
      player.x = width / 2;
      player.y = landingY + player.height / 2;
      player.vx = 0;
      player.vy = 0;
      openingJump = true;
      updateHud();
    }
    return true;
  }

  function drawForgottenPaddock() {
    ctx.fillStyle = "#080f16";
    ctx.fillRect(0, 0, width, height);
    if (art.garage) {
      const pixelWidth = Math.ceil(width * dpr);
      if (!garageCache || garageCache.width !== pixelWidth) {
        const tileHeight = Math.round(pixelWidth * art.garage.naturalHeight / art.garage.naturalWidth);
        const overlap = Math.round(tileHeight * .12);
        garageCache = document.createElement("canvas");
        garageCache.width = pixelWidth;
        garageCache.height = tileHeight - overlap;
        const painter = garageCache.getContext("2d", { alpha: false });
        painter.drawImage(art.garage, 0, 0, pixelWidth, tileHeight);
        // Blend the tail into the head once, keeping garages upright when tiled.
        for (let row = 0; row < overlap; row += 1) {
          painter.globalAlpha = 1 - row / overlap;
          const sourceY = (garageCache.height + row) / tileHeight * art.garage.naturalHeight;
          painter.drawImage(art.garage, 0, sourceY, art.garage.naturalWidth,
            art.garage.naturalHeight / tileHeight, 0, row, pixelWidth, 1);
        }
      }
      const cycle = garageCache.height / dpr;
      const offset = cameraY * .16 % cycle;
      for (let y = offset - cycle; y < height; y += cycle) {
        const top = Math.floor(y * dpr) / dpr;
        const bottom = Math.ceil((y + cycle) * dpr) / dpr;
        ctx.drawImage(garageCache, 0, top, width, bottom - top + 1 / dpr);
      }
    }
    ctx.save();
    ctx.globalAlpha = .65 + Math.sin(elapsed * 1.2) * .12;
    ctx.fillStyle = "#b1ccc3";
    ctx.font = "bold 11px monospace";
    ctx.textAlign = "center";
    ctx.fillText("WE ARE CHECKING…", width / 2, height * .18);
    ctx.restore();
  }

  function beginAntarcticaScene() {
    if (antarctica || antarcticaScene || !player) return;
    antarcticaScene = { age: 0, fromX: player.x / width, fromY: worldToScreen(player.y) / height };
    antarcticaArrival = null;
    machine.classList.add("is-story");
    rocketTimer = 0;
    kimiBoost = 0;
    babyKimi = null;
    somersault = null;
    spaceBoss = null;
    bossShots = [];
    hazards = [];
    enemies = [];
    hawks = [];
    releaseTouchControls();
    if (introCaption) introCaption.textContent = "Верхний этаж. Тото отталкивает Рассела и нажимает красную кнопку.";
  }

  function enterAntarctica() {
    resetWinterEncounters();
    antarcticaScene = null;
    antarcticaArrival = { age: 0 };
    antarctica = true;
    antarcticaEntryY = cameraY;
    antarcticaEntryScore = runScore();
    winterMemoryStartedAt = null;
    arrivalUntil = 0;
    player.x = width * .68;
    // Leave peakY and all earned bonuses untouched through the cutscene.
    player.y = cameraY + height * .42;
    player.vx = 0;
    player.vy = 0;
    facing = 1;
    openingJump = false;
    invulnerableTimer = 3;
    platforms = [];
    enemies = [];
    hazards = [];
    powerups = [];
    marshals = [];
    effects = [];
    worldTop = player.y - player.height / 2;
    addPlatform(worldTop, player.x, "normal");
    // Give the player a reachable first landing after leaving the portal.
    worldTop += 125;
    addPlatform(worldTop, player.x + width * .08, "normal");
    nextMarshalY = worldTop + 1800;
    lastPowerupSpawnY = worldTop;
    extendWorld();
    releaseTouchControls();
    if (introCaption) introCaption.textContent = "Рассел выпадает из портала в ледяную пещеру. У выхода справа его встречает Сид.";
    updateHud();
  }

  function finishAntarcticaArrival() {
    antarcticaArrival = null;
    machine.classList.remove("is-story");
    player.vx = 0;
    player.vy = 720;
    invulnerableTimer = 3;
    nextHudUpdate = 0;
    antarcticaEntryScore = runScore();
    releaseTouchControls();
    if (introCaption) introCaption.textContent = "Сид указывает наверх. Прыгай по ледяным платформам.";
    updateHud();
  }

  function drawAntarctica() {
    ctx.fillStyle = "#aabdd8";
    ctx.fillRect(0, 0, width, height);
    const source = art.antarctica;
    if (!source) return;
    const tileHeight = width * source.naturalHeight / source.naturalWidth;
    const overlap = tileHeight * .18;
    const cycle = tileHeight - overlap;
    const offset = Math.max(0, cameraY - antarcticaEntryY) * .13 % cycle;
    const sourceOverlap = source.naturalHeight * .18;
    const seamWidth = canvas.width;
    const seamHeight = Math.max(1, Math.ceil(overlap * dpr));
    if (!winterSeamCache || winterSeamCache.width !== seamWidth || winterSeamCache.height !== seamHeight) {
      // Only cache the narrow join, at full display resolution. No giant
      // repeating backdrop surface, and no 16 alpha blends on every frame.
      winterSeamCache = document.createElement("canvas");
      winterSeamCache.width = seamWidth;
      winterSeamCache.height = seamHeight;
      const painter = winterSeamCache.getContext("2d", { alpha: false });
      painter.imageSmoothingEnabled = false;
      painter.drawImage(source, 0, source.naturalHeight - sourceOverlap, source.naturalWidth, sourceOverlap,
        0, 0, seamWidth, seamHeight);
      for (let band = 0; band < 16; band += 1) {
        painter.globalAlpha = (band + .5) / 16;
        painter.drawImage(source, 0, sourceOverlap * band / 16, source.naturalWidth, sourceOverlap / 16,
          0, seamHeight * band / 16, seamWidth, seamHeight / 16 + 1);
      }
    }
    ctx.save();
    // Blend upright images directly: no giant offscreen texture on iPhones.
    for (let y = offset - cycle * 2; y < height; y += cycle) {
      ctx.globalAlpha = 1;
      if (y + overlap + cycle >= 0 && y + overlap < height) {
        ctx.drawImage(source, 0, sourceOverlap, source.naturalWidth, source.naturalHeight - sourceOverlap,
          0, y + overlap, width, cycle + 1 / dpr);
      }
      if (y + overlap >= 0 && y < height) ctx.drawImage(winterSeamCache, 0, y, width, overlap);
    }
    ctx.globalAlpha = .65;
    ctx.fillStyle = "#f0f8ff";
    for (let i = 0; i < 32; i += 1) {
      const x = (decorRandom(i, 43) * width + elapsed * (7 + i % 5)) % width;
      const y = (decorRandom(i, 71) * height + elapsed * (16 + i % 9) + cameraY * .08) % height;
      const size = i % 3 === 0 ? 3 : 2;
      ctx.fillRect(Math.round(x), Math.round(y), size, size);
    }
    ctx.restore();
    drawWinterMemory();
  }

  function drawIcePlatform(platform) {
    const index = platform.kind === "moving" ? 1 : platform.kind === "break" ? 2 : platform.kind === "spring" ? 3 : 0;
    drawFrame(art.winterPlatforms[index], platform.x, platform.y, platform.spriteWidth, "platform");
    if (platform.frozenUntil > elapsed) {
      const y = worldToScreen(platform.y);
      if (y < -20 || y > height + 20) return;
      ctx.save();
      ctx.strokeStyle = "#94e5ff";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(platform.x - platform.hitboxWidth * .44, y + 1);
      ctx.lineTo(platform.x + platform.hitboxWidth * .44, y + 1);
      ctx.stroke();
      ctx.fillStyle = "#e2faff";
      for (let i = -1; i <= 1; i += 1) ctx.fillRect(platform.x + i * platform.hitboxWidth * .25, y + 4, 3, 3);
      ctx.restore();
    }
  }

  function resetWinterEncounters() {
    winterEncounter = null;
    winterProjectiles = [];
    winterEncounterWait = 8;
    winterEnemyIndex = -1;
    winterSlide = winterWind = winterWindDirection = 0;
  }

  function spawnWinterEncounter(kind = null) {
    if (!antarctica || antarcticaArrival || winterEncounter || sidBoss) return false;
    const kinds = ["iceman", "strategist", "steward"];
    winterEnemyIndex = winterEnemyIndex < 0 ? Math.floor(Math.random() * kinds.length) : (winterEnemyIndex + 1) % kinds.length;
    const type = kind || kinds[winterEnemyIndex];
    // Queue the encounter above the entire viewport and existing fish. It
    // enters naturally as the camera rises; never erase visible piranhas.
    const spawnY = enemies.reduce((top, enemy) => enemy.dead ? top : Math.max(top, enemy.y + 250), cameraY + height + 100);
    winterEncounter = { type, age: 0, phase: "arriving", phaseAge: 0, round: 0,
      x: width * (player.x < width / 2 ? .74 : .26), y: spawnY,
      direction: player.x < width / 2 ? -1 : 1, target: null };
    return true;
  }

  function winterEnemyGeometry(mob = winterEncounter) {
    const actorHeight = mob.type === "iceman" ? 94 : 82;
    return { x: mob.x, y: mob.y, rx: mob.type === "iceman" ? 24 : 22, ry: actorHeight * .36, height: actorHeight };
  }

  function winterEnemyPose(mob) {
    return mob.phase === "defeated" || mob.phase === "open" ? 3
      : mob.phase === "attack" ? 2 : mob.phase === "warning" ? 1 : 0;
  }

  function updateWinterEncounter(dt, previousFeet, currentFeet, previousPlayerX = player.x) {
    if (!antarctica || antarcticaArrival || sidBoss) return;
    winterSlide = Math.max(0, winterSlide - dt);
    winterWind = Math.max(0, winterWind - dt);
    if (!winterEncounter) {
      winterEncounterWait -= dt;
      if (winterEncounterWait <= 0 && !winterProjectiles.length) spawnWinterEncounter();
    }
    const mob = winterEncounter;
    if (mob) {
      const previousY = mob.y;
      mob.age += dt;
      const go = (phase) => { mob.phase = phase; mob.phaseAge = 0; };
      const body = winterEnemyGeometry(mob);
      const screenY = worldToScreen(mob.y);
      const fullyVisible = screenY >= body.height / 2 + 28 && screenY < height - body.height / 2;
      if (mob.phase === "arriving") {
        if (fullyVisible) go("idle");
      } else if (mob.phase === "defeated") {
        mob.phaseAge += dt;
        mob.y -= (80 + mob.phaseAge * 140) * dt;
      } else if (fullyVisible) {
        // Do not run attack timers while hidden above the screen or below it.
        mob.phaseAge += dt;
      }
      if (mob.phase === "idle" && mob.phaseAge >= 1.1) {
        mob.direction = player.x < mob.x ? -1 : 1;
        if (mob.type === "strategist") {
          // A normal, reachable platform, never the only spring or a broken one.
          const candidates = platforms.filter((p) => !p.broken && p.kind === "normal"
            && p.y > cameraY + 50 && p.y < cameraY + height * .8 && p.y > player.y - 80);
          mob.target = candidates.reduce((best, p) => !best || Math.abs(p.y - player.y - 160) < Math.abs(best.y - player.y - 160) ? p : best, null);
        }
        go("warning");
      } else if (mob.phase === "warning" && mob.phaseAge >= 1.6) {
        go("attack");
        mob.round += 1;
        if (mob.type === "strategist") {
          if (mob.target && !mob.target.broken) mob.target.frozenUntil = elapsed + 7;
        } else if (mob.type === "iceman") {
          winterProjectiles.push({ type: "gust", x: mob.x + mob.direction * 34, y: mob.y + 8,
            vx: mob.direction * 115, vy: 0, age: 0 });
        } else {
          const vx = clamp((player.x - mob.x) * .35, -65, 65);
          winterProjectiles.push({ type: "penalty", x: mob.x, y: mob.y - 25, vx, vy: -112, age: 0 });
        }
      } else if (mob.phase === "attack" && mob.phaseAge >= .65) go("open");
      else if (mob.phase === "open" && mob.phaseAge >= 2.4) go("idle");

      const active = mob.phase !== "arriving" && mob.phase !== "defeated";
      const canBounce = active && (mob.type !== "steward" || mob.phase === "open");
      if (canBounce && player.vy < 0 && movingLanding(previousFeet, currentFeet,
        previousY + body.ry, mob.y + body.ry, previousPlayerX, mob.x, mob.x, body.rx * 2)) {
        player.y = mob.y + body.ry + player.height / 2;
        player.vy = 830;
        somersault = null;
        openingJump = false;
        frags += 1;
        go("defeated");
        winterProjectiles = [];
        invulnerableTimer = Math.max(invulnerableTimer, .45);
        effects.push({ index: 10, x: mob.x, y: mob.y, age: 0, duration: .4, size: 48 * visualScale() });
      } else if (active && mob.type === "steward" && mob.phase !== "open" && invulnerableTimer <= 0) {
        const dx = (player.x - body.x) / (body.rx + player.width * .29);
        const dy = (player.y - body.y) / (body.ry + player.height * .34);
        if (dx * dx + dy * dy < 1) { endGame(); return; }
      }
      // Retire only once body AND caption have moved below the viewport.
      if (mob.y < cameraY - body.height / 2 - 32) {
        winterEncounter = null;
        winterEncounterWait = 12 + Math.random() * 8;
      }
    }
    let kept = 0;
    for (const shot of winterProjectiles) {
      const oldX = shot.x, oldY = shot.y;
      shot.age += dt;
      shot.x += shot.vx * dt;
      shot.y += shot.vy * dt;
      if (shot.age > 5 || shot.y < cameraY - 60 || shot.x < -80 || shot.x > width + 80) continue;
      const rx = shot.type === "gust" ? 25 : 20, ry = shot.type === "gust" ? 11 : 12;
      let hit = false;
      if (invulnerableTimer <= 0) {
        // Sweep relative motion; the hero can be moving much faster than a shot.
        const oldPlayerY = previousFeet + player.height / 2;
        const oldPlayerX = Math.abs(player.x - previousPlayerX) > width / 2 ? player.x : previousPlayerX;
        const dx = shot.x - oldX - (player.x - oldPlayerX), dy = shot.y - oldY - (player.y - oldPlayerY);
        const ox = oldX - oldPlayerX, oy = oldY - oldPlayerY;
        const t = clamp(-(ox * dx + oy * dy) / Math.max(.001, dx * dx + dy * dy), 0, 1);
        hit = ((ox + dx * t) / (rx + player.width * .27)) ** 2
          + ((oy + dy * t) / (ry + player.height * .33)) ** 2 < 1;
      }
      if (hit && shot.type === "penalty") { endGame(); return; }
      if (hit) {
        winterWind = .8;
        winterWindDirection = Math.sign(shot.vx);
        continue;
      }
      winterProjectiles[kept++] = shot;
    }
    winterProjectiles.length = kept;
  }

  function drawWinterEncounter() {
    if (!antarctica || antarcticaArrival) return;
    const mob = winterEncounter;
    if (mob) {
      const frames = art[`winter${mob.type[0].toUpperCase()}${mob.type.slice(1)}`];
      const pose = winterEnemyPose(mob), sprite = frames?.[pose];
      if (sprite) {
        const body = winterEnemyGeometry(mob), h = body.height;
        const w = h * sprite.sw / sprite.sh, sy = worldToScreen(mob.y);
        const anchor = mob.type === "iceman" ? [.5, .41, .3, .5][pose] : .5;
        ctx.save(); ctx.translate(mob.x, sy); ctx.scale(mob.direction, 1);
        if (mob.phase === "warning") ctx.globalAlpha = .8 + Math.sin(mob.phaseAge * 16) * .2;
        if (mob.phase === "defeated") ctx.rotate(Math.min(1.2, mob.phaseAge * .5));
        ctx.drawImage(rasterSprite(sprite, w, h), -w * anchor, -h / 2, w, h);
        ctx.restore();
        let label = mob.type === "iceman" ? "LEAVE ME ALONE" : mob.type === "strategist"
          ? (mob.phase === "attack" || mob.phase === "open" ? "STAY OUT" : "BOX BOX")
          : mob.phase === "open" ? "ПРЫГАЙ СВЕРХУ!" : "FIA · +5 SEC";
        if (mob.phase === "defeated") label = "+30";
        ctx.save(); ctx.textAlign = "center"; ctx.font = "bold 10px monospace";
        ctx.strokeStyle = "#f2faff"; ctx.lineWidth = 3; ctx.lineJoin = "round";
        ctx.fillStyle = mob.type === "strategist" ? "#a32c35" : "#21385a";
        const x = clamp(mob.x, 85, width - 85), y = sy - h / 2 - 10;
        ctx.strokeText(label, x, y); ctx.fillText(label, x, y); ctx.restore();
        if (mob.type === "strategist" && mob.phase === "warning" && mob.target && !mob.target.broken) {
          ctx.save(); ctx.setLineDash([4, 5]); ctx.strokeStyle = "rgba(190,55,64,.65)"; ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.moveTo(mob.x, sy + h * .3); ctx.lineTo(mob.target.x, worldToScreen(mob.target.y)); ctx.stroke(); ctx.restore();
        }
      }
    }
    for (const shot of winterProjectiles) {
      const y = worldToScreen(shot.y);
      if (y < -40 || y > height + 40) continue;
      ctx.save(); ctx.translate(shot.x, y);
      if (shot.type === "gust") {
        ctx.scale(Math.sign(shot.vx), 1);
        ctx.strokeStyle = "#b4edff"; ctx.lineWidth = 3;
        for (let i = -1; i <= 1; i += 1) {
          ctx.beginPath(); ctx.moveTo(-22, i * 9); ctx.quadraticCurveTo(28, i * 9 + 7, 19, i * 9 - 3); ctx.stroke();
        }
      } else {
        ctx.rotate(Math.sin(shot.age * 4) * .1);
        ctx.fillStyle = "#19304d"; ctx.fillRect(-22, -14, 44, 28);
        ctx.strokeStyle = "#c5edff"; ctx.lineWidth = 2; ctx.strokeRect(-22, -14, 44, 28);
        ctx.fillStyle = "#f2faff"; ctx.font = "bold 10px monospace"; ctx.textAlign = "center"; ctx.fillText("+5 SEC", 0, 3);
      }
      ctx.restore();
    }
  }

  function drawWinterMemory(foreground = false) {
    if (winterMemoryStartedAt === null || antarcticaArrival || sidBoss) return;
    const age = elapsed - winterMemoryStartedAt;
    const fade = sceneEase(age, 0, 2) * (1 - sceneEase(age, 18, 20));
    if (fade <= 0 || !art.winterPortrait) return;
    const fontSize = Math.min(clamp(width / 35, 10, 12), Math.max(9, height * .035));
    const lineHeight = Math.ceil(fontSize * 1.5);
    const maxWidth = Math.min(width * .86, 420);
    const key = `${maxWidth}:${fontSize}:semibold`;
    ctx.save(); ctx.font = `600 ${fontSize}px system-ui`;
    if (!winterQuoteLayout || winterQuoteLayout.key !== key) {
      const lines = [];
      // Group the sentence by meaning, then wrap each phrase for the viewport.
      const phrases = winterMemoryQuote.replace(", he", ",\nhe").replace(" and borderline", "\nand borderline").split("\n");
      for (const phrase of phrases) {
        let line = "";
        for (const word of phrase.split(" ")) {
          const next = line ? `${line} ${word}` : word;
          if (line && ctx.measureText(next).width > maxWidth) { lines.push(line); line = word; }
          else line = next;
        }
        if (line) lines.push(line);
      }
      winterQuoteLayout = { key, lines };
    }
    const textHeight = winterQuoteLayout.lines.length * lineHeight;
    const textTop = Math.max(16, height * .5 - textHeight);
    const portraitTop = Math.min(Math.max(82, height * .12), height * .2);
    const portraitHeight = Math.min(height * .28, 230, Math.max(0, textTop - portraitTop + 10));
    if (!foreground && portraitHeight > 0) {
      const portraitWidth = portraitHeight * art.winterPortrait.sw / art.winterPortrait.sh;
      ctx.globalAlpha = fade * .55;
      ctx.drawImage(rasterSprite(art.winterPortrait, portraitWidth, portraitHeight),
        (width - portraitWidth) / 2, portraitTop, portraitWidth, portraitHeight);
    }
    // Lettering only: no panel or background obscuring the winter scenery.
    // A fine frost-coloured outline keeps navy letters readable over ice.
    if (foreground) {
      ctx.globalAlpha = fade;
      ctx.textAlign = "center";
      ctx.strokeStyle = "rgba(240,248,255,.95)"; ctx.lineWidth = 2; ctx.lineJoin = "round";
      ctx.fillStyle = "#27385f";
      const textY = textTop + fontSize;
      winterQuoteLayout.lines.forEach((line, index) => {
        ctx.strokeText(line, width / 2, textY + index * lineHeight);
        ctx.fillText(line, width / 2, textY + index * lineHeight);
      });
    }
    ctx.restore();
  }

  function sidArenaHeight() { return Math.min(height, visibleWorldHeight); }

  function sidBossGeometry() {
    const arenaH = sidArenaHeight();
    return { x: width * .5 + Math.sin(sidBoss.age * .5) * Math.min(22, width * .04),
      feet: cameraY + arenaH - Math.min(215, arenaH * .32), h: Math.min(112, arenaH * .21) };
  }

  function buildSidArena(previousHeight = null) {
    const arenaH = sidArenaHeight();
    const oldY = player.y;
    platforms = [];
    const floorY = cameraY + arenaH * .09, gap = Math.min(112, arenaH * .19);
    const tiles = Math.ceil(width / 68);
    for (let i = 0; i < tiles; i += 1) {
      const p = addPlatform(floorY, (i + .5) * width / tiles, "normal");
      p.width = p.hitboxWidth = width / tiles + 3;
      p.spriteWidth = width / tiles + 12;
    }
    for (let row = 1; row <= 3; row += 1) {
      if (floorY + row * gap + player.height >= cameraY + arenaH - Math.min(72, arenaH * .18)) break;
      for (const lane of [.18, .5, .82]) addPlatform(floorY + row * gap, width * lane, "normal");
    }
    worldTop = cameraY + height;
    if (previousHeight) player.y = cameraY + (oldY - cameraY) / previousHeight * arenaH;
    player.y = clamp(player.y, floorY + player.height / 2,
      cameraY + arenaH - Math.min(72, arenaH * .18) - player.height / 2);
    if (previousHeight && sidBoss) {
      for (const shot of sidBoss.shots) {
        for (const key of ["y", "fromY", "targetY"]) if (shot[key] !== undefined) shot[key] = cameraY + (shot[key] - cameraY) / previousHeight * arenaH;
      }
      for (const key of ["heroFromY", "heroLandY"]) if (sidBoss[key] !== undefined) sidBoss[key] = cameraY + (sidBoss[key] - cameraY) / previousHeight * arenaH;
    }
  }

  function beginSidBoss() {
    if (!antarctica || antarcticaArrival || sidBoss || sidBossCleared) return false;
    resetWinterEncounters();
    enemies = []; hazards = []; hawks = []; marshals = []; powerups = []; effects = [];
    rocketTimer = kimiBoost = softBootJumps = 0;
    freeFlight = false;
    if (flightButton) { flightButton.setAttribute("aria-pressed", "false"); flightButton.textContent = "Свободный полёт: выкл."; }
    sidBoss = { hp: 10, age: 0, phase: "intro", timer: 0, round: 0, shots: [], lanes: [], hits: 0 };
    player.y = cameraY + sidArenaHeight() * .35; player.vy = 720;
    openingJump = false; somersault = null;
    invulnerableTimer = Math.max(invulnerableTimer, 2);
    buildSidArena();
    loadStage("summit");
    updateHud();
    return true;
  }

  function sidPhase(phase) { sidBoss.phase = phase; sidBoss.timer = 0; }

  function beginSidIceWarning() {
    const safe = clamp(Math.floor(player.x / width * 4), 0, 3);
    const lanes = [0, 1, 2, 3].filter(lane => lane !== safe);
    // Two marked lanes; at least two unmarked lanes remain safe.
    if (Math.random() < .5) lanes.reverse();
    sidBoss.lanes = lanes.slice(0, 2);
    sidPhase("ice-warning");
  }

  function sidShotGeometry(shot) {
    const frame = art.sidBossProps[shot.kind === "can" ? 0 : shot.kind === "crushed" ? 1 : 2];
    const h = shot.kind === "ice" ? 43 : shot.kind === "can" ? 34 : 27;
    return { frame, h, w: h * frame.sw / frame.sh };
  }

  function throwSidCan() {
    const b = sidBossGeometry(), targetX = sidBoss.canLane;
    sidBoss.shots.push({ kind: "can", x: b.x, y: b.feet + b.h * .55, fromX: b.x,
      fromY: b.feet + b.h * .55, targetX, targetY: b.feet - 30,
      age: 0, vy: -(83 + Math.min(28, sidBoss.hits * 3)), reflected: false });
    const otherX = targetX < width / 2 ? width * .84 : width * .16;
    sidBoss.shots.push({ kind: "crushed", x: otherX, y: cameraY + sidArenaHeight() + 35,
      age: 0, vy: -112, reflected: false });
  }

  function updateSidBoss(dt) {
    const boss = sidBoss;
    if (!boss) return false;
    boss.age += dt; boss.timer += dt;
    if (boss.phase === "victory") {
      invulnerableTimer = Math.max(invulnerableTimer, .2);
      boss.shots = [];
      const t = sceneEase(boss.timer, 4.6, 6.7);
      const landing = sceneEase(boss.timer, 0, 1.15);
      const landX = sceneMix(boss.heroFromX, boss.heroLandX, landing);
      const landY = sceneMix(boss.heroFromY, boss.heroLandY, landing) + Math.sin(landing * Math.PI) * 12;
      player.x = sceneMix(landX, width / 2, t);
      player.y = sceneMix(landY, cameraY + sidArenaHeight() * .9, t);
      if (boss.timer >= 6.8 && stageReady("summit")) enterSummit();
      return true;
    }
    if (boss.phase === "intro" && boss.timer >= 1.8) beginSidIceWarning();
    else if (boss.phase === "ice-warning" && boss.timer >= Math.max(.95, 1.25 - boss.hits * .025)) {
      for (const lane of boss.lanes) boss.shots.push({ kind: "ice", x: (lane + .5) * width / 4,
        y: cameraY + sidArenaHeight() + 35, age: 0, vy: -(100 + boss.hits * 2) });
      sidPhase("ice");
    } else if (boss.phase === "ice" && boss.timer >= 1.7) {
      boss.canLane = clamp(player.x, 50, width - 50); sidPhase("can-warning");
    } else if (boss.phase === "can-warning" && boss.timer >= 1) {
      throwSidCan(); boss.round += 1; sidPhase("can");
    } else if (boss.phase === "can" && boss.timer >= 7) {
      boss.shots = []; beginSidIceWarning();
    } else if (boss.phase === "hit" && boss.timer >= .8) beginSidIceWarning();
    return false;
  }

  function collideSidShots(dt, previousFeet, currentFeet, previousPlayerX = player.x) {
    const boss = sidBoss;
    if (!boss || boss.phase === "victory") return;
    const kept = [];
    for (const shot of boss.shots) {
      const oldX = shot.x, oldY = shot.y;
      shot.age += dt;
      const geometry = sidShotGeometry(shot);
      if (shot.reflected) {
        const b = sidBossGeometry(), targetY = b.feet + b.h * .65;
        const dx = b.x - shot.x, dy = targetY - shot.y, distance = Math.hypot(dx, dy);
        if (distance <= 520 * dt + 12) {
          boss.hp = Math.max(0, boss.hp - 1); boss.hits = 10 - boss.hp; boss.shots = [];
          invulnerableTimer = Math.max(invulnerableTimer, .65);
          if (boss.hp === 0) {
            beginSidVictory();
          } else sidPhase("hit");
          updateHud(); return;
        }
        shot.x += dx / distance * 520 * dt; shot.y += dy / distance * 520 * dt;
        kept.push(shot); continue;
      }
      if (shot.kind === "can" && shot.age < .65) {
        const t = clamp(shot.age / .65, 0, 1);
        shot.x = sceneMix(shot.fromX, shot.targetX, t);
        shot.y = sceneMix(shot.fromY, shot.targetY, t) + Math.sin(t * Math.PI) * 26;
      } else shot.y += shot.vy * dt;
      if (shot.y + geometry.h / 2 < cameraY - 40 || shot.age > 10) continue;
      if (shot.kind === "can" && shot.age >= .65 && player.vy < 0
        && movingLanding(previousFeet, currentFeet, oldY + geometry.h / 2, shot.y + geometry.h / 2,
          previousPlayerX, oldX, shot.x, Math.max(28, geometry.w))) {
        player.y = shot.y + geometry.h / 2 + player.height / 2;
        player.vy = 760; shot.reflected = true;
        openingJump = false; somersault = null;
        invulnerableTimer = Math.max(invulnerableTimer, .35);
        kept.push(shot); continue;
      }
      if (invulnerableTimer <= 0) {
        const oldPlayerY = previousFeet + player.height / 2;
        const oldPlayerX = Math.abs(player.x - previousPlayerX) > width / 2 ? player.x : previousPlayerX;
        const steps = Math.max(1, Math.ceil((Math.abs(player.vy) + Math.abs(shot.vy)) * dt / 8));
        for (let step = 0; step <= steps; step += 1) {
          const t = step / steps;
          if (spriteOverlapsEllipse(geometry.frame, sceneMix(oldX, shot.x, t), sceneMix(oldY, shot.y, t), geometry.w, geometry.h,
            sceneMix(oldPlayerX, player.x, t), sceneMix(oldPlayerY, player.y, t), player.width * .28, player.height * .34)) {
            endGame(); return;
          }
        }
      }
      kept.push(shot);
    }
    boss.shots = kept;
  }

  function drawSidBoss() {
    const boss = sidBoss;
    if (!boss) return;
    const arenaH = sidArenaHeight(), arenaTop = height - arenaH;
    const b = sidBossGeometry(), victory = boss.phase === "victory", age = boss.timer;
    const pose = boss.phase === "ice-warning" || boss.phase === "ice" ? 1
      : boss.phase === "can-warning" ? 2 : boss.phase === "can" && age < .6 ? 3 : 0;
    const finalePose = boss.phase === "hit" ? 0 : age < .8 ? 0 : age < 1.9 ? 1 : age < 2.8 ? 2 : (Math.floor(age * 9) % 2 ? 3 : 2);
    const sprite = victory || boss.phase === "hit" ? art.sidBossFinale[finalePose] : art.sidBossAttack[pose];
    const shake = boss.phase === "ice-warning" ? Math.sin(age * 32) * 3 : boss.phase === "hit" ? Math.sin(age * 28) * 5 : 0;
    const fly = victory ? sceneEase(age, 2.8, 4.4) : 0;
    const squash = boss.phase === "can-warning" ? 1 + Math.sin(age * 8) * .035 : 1;
    if (!victory || age < 3.5) drawFrame(art.winterPlatforms[0], b.x, b.feet, Math.min(150, width * .4), "platform");
    if (victory || boss.phase === "hit") {
      const fridge = art.sidBossProps[3], fridgeH = b.h * .55;
      const fall = victory ? Math.max(0, age - 3.5) ** 2 * 90 : 0;
      drawFrame(fridge, b.x + b.h * .54, b.feet + fridgeH / 2 - fall,
        fridgeH * fridge.sw / fridge.sh, "center", fridgeH);
    }
    drawStoryActor(sprite, b.x + shake + (victory ? Math.sin(age * 2.5) * 18 * fly : 0),
      worldToScreen(b.feet) - fly * (arenaH * .55 + b.h), b.h,
      victory ? Math.sin(age * 7) * .035 : Math.sin(boss.age * 2) * .015, 1 / squash, squash);
    const roofY = arenaTop + Math.min(72, arenaH * .18);
    ctx.save();
    // Roof shards are deliberately small code-native ice facets, not a large
    // offscreen texture; the fall/open animation stays sharp at any DPR.
    if (!victory || age < 3.5) {
      const cap = art.winterPlatforms[0], tileW = width / 7 + 3, tileH = spriteSize(cap, tileW);
      for (let i = 0; i < 7; i += 1) {
        ctx.drawImage(rasterSprite(cap, tileW, tileH), i * width / 7 - 1.5, roofY - tileH, tileW, tileH);
      }
    } else if (age < 4.8) {
      const t = age - 3.5; ctx.fillStyle = "#b7e9ff"; ctx.globalAlpha = Math.max(0, 1 - t / 1.3);
      for (let i = 0; i < 20; i += 1) {
        const x = width / 2 + (i - 10) * (12 + t * 18), y = roofY + t * t * (100 + i % 4 * 16);
        ctx.fillRect(x, y, 4 + i % 3, 7);
      }
    }
    if (boss.phase === "ice-warning") {
      ctx.setLineDash([3, 8]); ctx.strokeStyle = "#e49c7e"; ctx.lineWidth = 1.5;
      for (const lane of boss.lanes) {
        const x = (lane + .5) * width / 4;
        ctx.beginPath(); ctx.moveTo(x, roofY + 30); ctx.lineTo(x, height - 24); ctx.stroke();
      }
    }
    ctx.restore();
    for (const shot of boss.shots) {
      const s = sidShotGeometry(shot);
      if (shot.kind === "can") {
        ctx.save(); ctx.strokeStyle = shot.reflected ? "#f5e18b" : "#80e7ff"; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.ellipse(shot.x, worldToScreen(shot.y), s.w / 2 + 5, s.h / 2 + 4, 0, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
      }
      drawFrame(s.frame, shot.x, shot.y, s.w, "center", s.h);
    }
    ctx.save(); ctx.font = "bold 11px monospace"; ctx.fillStyle = "#eaf8ff";
    ctx.strokeStyle = "#162d49"; ctx.lineWidth = 3; ctx.textAlign = "left";
    const hudY = arenaTop + Math.min(98, arenaH * .15);
    const title = victory ? "СИД ПОБЕЖДЁН · 10/10" : `СИД · ${boss.hits}/10`;
    ctx.strokeText(title, 14, hudY); ctx.fillText(title, 14, hudY);
    for (let i = 0; i < 10; i += 1) { ctx.fillStyle = i < boss.hp ? "#e59e66" : "#7594a7"; ctx.fillRect(14 + i * 13, hudY + 7, 10, 4); }
    ctx.textAlign = "center"; ctx.font = "bold 10px monospace";
    const hint = victory ? "RED BULL ДАЁТ КРЫЛЬЯ" : boss.phase === "ice-warning" ? "УКЛОНЯЙСЯ ОТ ЛЬДА"
      : boss.phase === "can-warning" || boss.phase === "can" ? "ЦЕЛУЮ БАНКУ — ОТБЕЙ СВЕРХУ" : "10 БАНОК ОТКРОЮТ ПРОХОД";
    ctx.strokeText(hint, width / 2, height - 9); ctx.fillStyle = "#f4df9f"; ctx.fillText(hint, width / 2, height - 9); ctx.restore();
    if (victory && age > 4.3) {
      const size = Math.min(width * .19, arenaH * .14) * sceneEase(age, 4.3, 5.2);
      drawStoryPortal(width / 2, arenaTop + arenaH * .18, size, age, art.summit);
      drawCinemaFrame("ПРОХОД ОТКРЫТ", "Высокогорный паддок", sceneEase(age, 4.4, 5));
    }
  }

  function enterSummit() {
    if (!sidBoss || sidBoss.hp > 0 || !assetStages.get("summit")?.ready) return false;
    sidBossCleared = true; sidBoss = null; summit = true; antarctica = false;
    resetWinterEncounters();
    summitEntryY = cameraY; bossBonus += 500;
    summitPlatformIndex = 0;
    summitGoatNextY = cameraY + height + 3000;
    summitRareLastY = -Infinity;
    summitEncounter = null; summitShots.length = 0;
    summitEnemyNextY = cameraY + height + 1000;
    summitEnemyLastType = Math.random() < .5 ? "drone" : "marmot";
    summitCommentator = null;
    summitCommentatorNextY = cameraY + height + 5000;
    platforms = []; enemies = []; hazards = []; hawks = []; powerups = []; marshals = []; effects = [];
    player.x = width / 2; player.y = cameraY + height * .35; player.vy = 720;
    openingJump = false; invulnerableTimer = 3;
    worldTop = player.y - player.height / 2;
    addPlatform(worldTop, player.x, "normal");
    extendWorld(); updateHud();
    return true;
  }

  function drawSummitBackdrop() {
    const source = art.summit;
    ctx.fillStyle = "#69a5de"; ctx.fillRect(0, 0, width, height);
    if (!source) return;
    const scale = Math.max(width / source.naturalWidth, height / source.naturalHeight) * 1.3;
    const sourceHeight = height / scale, sourceWidth = width / scale;
    const climb = Math.max(0, cameraY - summitEntryY), progress = clamp(climb / 6000, 0, 1);
    const sy = (source.naturalHeight - sourceHeight) * (1 - progress);
    ctx.drawImage(source, (source.naturalWidth - sourceWidth) / 2, sy, sourceWidth, sourceHeight, 0, 0, width, height);
    if (art.cloud && climb > 3500) {
      ctx.save(); ctx.globalAlpha = Math.min(.4, (climb - 3500) / 5000);
      for (let i = 0; i < 4; i += 1) {
        const w = width * .4, h = w * art.cloud.naturalHeight / art.cloud.naturalWidth, cycle = height + h * 2;
        const y = ((i / 4 * cycle + climb * .13) % cycle) - h;
        drawCloud(i % 2 ? width - w * .8 : -w * .2, y, w, h);
      }
      ctx.restore();
    }
  }

  function decorateSummitPlatform(platform) {
    const step = summitPlatformIndex++ % 18;
    const difficulty = clamp((platform.y - summitEntryY) / 6000, 0, 1);
    platform.kind = "normal";
    platform.width = platform.hitboxWidth = platform.spriteWidth = 89.7 * visualScale() - difficulty * 3;
    platform.height = 9;
    if (step >= 8 && step <= 11) {
      platform.summitKind = "purple";
      platform.kind = "normal";
    } else if (step === 5 || step === 15) {
      platform.summitKind = "cable";
      platform.kind = "moving";
      platform.range = 16;
      platform.width = platform.hitboxWidth = platform.spriteWidth = 78;
    } else if (platform.y >= summitGoatNextY && platform.y - summitRareLastY >= 2200) {
      platform.goat = { phase: 0, kicked: false, cooldown: 0 };
      platform.width = platform.hitboxWidth = platform.spriteWidth = 62;
      summitRareLastY = platform.y;
      summitGoatNextY = platform.y + 6500 + Math.random() * 2500;
    } else if (step === 3 || step === 13) {
      platform.kind = "break";
    } else if (step === 1 || step === 6 || step === 14) {
      platform.kind = "moving";
      platform.range = 16;
    } else if (step === 16) {
      platform.kind = "spring";
      platform.spriteWidth = 52;
      platform.width = platform.hitboxWidth = 20;
    }
    platform.spriteIndex = platform.kind === "moving" ? 1 : platform.kind === "break" ? 2 : platform.kind === "spring" ? 3 : 0;
  }

  function summitPlatformGap() {
    return platformGap();
  }

  function summitPlatformFrames(sheet) {
    const rowHeight = sheet.naturalHeight / 4;
    const packed = document.createElement("canvas");
    packed.width = sheet.naturalWidth * 4; packed.height = rowHeight;
    const painter = packed.getContext("2d");
    for (let i = 0; i < 4; i++) painter.drawImage(sheet, 0, i * rowHeight, sheet.naturalWidth, rowHeight,
      i * sheet.naturalWidth, 0, sheet.naturalWidth, rowHeight);
    packed.naturalWidth = packed.width; packed.naturalHeight = packed.height;
    return checkedFrames(splitSpriteSheet(packed, 4, null, false, true), 4);
  }

  function summitEnemyFrames(sheet) {
    const poses = checkedFrames(splitSpriteSheet(sheet, 4, null, false, true), 4);
    const w = Math.max(...poses.map(p => p.sw)), h = Math.max(...poses.map(p => p.sh));
    return poses.map(p => {
      const tile = document.createElement("canvas"); tile.width = w; tile.height = h;
      const painter = tile.getContext("2d");
      painter.imageSmoothingEnabled = false;
      painter.drawImage(p.image, Math.round((w - p.sw) / 2), h - p.sh);
      const pixels = painter.getImageData(0, 0, w, h).data;
      return {image:tile, sx:0, sy:0, sw:w, sh:h, mask:alphaMask(pixels, w, 0, 0, w, h)};
    });
  }

  function spawnSummitEnemy(type = null) {
    if (!summit || summitEncounter || summitShots.length || !art.summitMarmot || !art.summitDrone) return false;
    if (summitCommentator && summitCommentator.y > cameraY - 100) return false;
    const y = cameraY + height + 100;
    if (platforms.some(p => p.goat && Math.abs(p.y - y) < 650)) return false;
    type = type || (summitEnemyLastType === "drone" ? "marmot" : "drone");
    const support = type === "marmot" ? platforms.find(p => !p.broken && !p.goat && !p.commentator
      && p.kind === "normal" && !p.summitKind && p.y >= y && p.y <= y + 350) : null;
    if (type === "marmot" && !support) return false;
    const w = type === "marmot" ? 64 : 76;
    const frame = type === "marmot" ? art.summitMarmot[0] : art.summitDrone[0];
    const h = spriteSize(frame, w);
    summitEncounter = {type, support, x:support?.x ?? width * (player.x < width / 2 ? .72 : .28),
      y:support ? support.y + h / 2 : y, w, h, phase:"arriving", timer:0,
      direction:player.x < width / 2 ? -1 : 1, age:0};
    summitEnemyLastType = type;
    return true;
  }

  function summitEnemyPose(mob) {
    if (mob.type === "drone" && mob.phase === "defeated") return art.summitDroneBroken;
    const frames = mob.type === "marmot" ? art.summitMarmot : art.summitDrone;
    return frames[mob.phase === "warning" ? 1 : mob.phase === "attack" || mob.phase === "open" ? 2
      : mob.phase === "defeated" || mob.phase === "retreat" ? 3 : 0];
  }

  function updateSummitEnemies(dt, previousFeet, currentFeet, previousX = player.x) {
    if (!summit) { summitEncounter = null; summitShots.length = 0; return; }
    if (!summitEncounter && !summitShots.length && cameraY + height >= summitEnemyNextY) spawnSummitEnemy();
    const mob = summitEncounter;
    if (mob) {
      const oldY = mob.y, oldX = mob.x;
      mob.age += dt;
      const sy = worldToScreen(mob.y), visible = sy > mob.h / 2 + 20 && sy < height - mob.h / 2;
      const go = phase => { mob.phase = phase; mob.timer = 0; };
      if (mob.phase === "arriving") {
        if (mob.type === "drone") mob.y -= 28 * dt;
        if (visible) go("idle");
      } else if (mob.phase === "defeated") {
        mob.timer += dt; mob.y -= (80 + mob.timer * 160) * dt;
        if (mob.type === "drone") mob.x += mob.direction * 22 * dt;
      } else if (mob.phase === "retreat") {
        mob.timer += dt; mob.x += mob.direction * 70 * dt; mob.y += 35 * dt;
      } else if (visible) {
        mob.timer += dt;
        if (mob.phase === "idle") {
          if (mob.type === "drone") mob.x += clamp(player.x - mob.x, -50, 50) * dt;
          if (mob.timer >= .9) { mob.direction = player.x < mob.x ? -1 : 1; go("warning"); }
        } else if (mob.phase === "warning" && mob.timer >= 1.3) {
          // Aim freezes during the warning. Only one projectile per encounter.
          summitShots.push({type:mob.type === "marmot" ? "snow" : "nut", x:mob.x + (mob.type === "marmot" ? mob.direction * 22 : 0),
            y:mob.y - mob.h * (mob.type === "marmot" ? .04 : .38), vx:mob.type === "marmot" ? mob.direction * 120 : 0,
            vy:mob.type === "marmot" ? -8 : -130, age:0});
          go("attack");
        } else if (mob.phase === "attack" && mob.timer >= .5) go(mob.type === "drone" ? "retreat" : "open");
      }
      if (mob.phase !== "defeated") {
        // Use the resting head silhouette, not the raised warning flag, as a foothold.
        const frame = mob.type === "marmot" ? art.summitMarmot[0] : art.summitDrone[0];
        const top = spriteLanding(frame, mob.x, mob.y, mob.w, mob.h, oldX, oldY,
          previousFeet, currentFeet, previousX, mob.type === "marmot" && mob.direction > 0 ? -1 : 1);
        if (top !== null) {
          player.y = top + player.height / 2; player.vy = 830;
          protectBounce();
          openingJump = false; somersault = null; frags += 1; go("defeated");
        }
      }
      if (mob.y + mob.h / 2 < cameraY - 60 || mob.x < -mob.w || mob.x > width + mob.w) {
        summitEncounter = null;
        summitEnemyNextY = cameraY + height + 1500 + Math.random() * 900;
      }
    }
    let kept = 0;
    for (const shot of summitShots) {
      const oldX = shot.x, oldY = shot.y;
      shot.age += dt; shot.x += shot.vx * dt;
      if (shot.type === "nut") shot.vy = Math.max(-220, shot.vy - 35 * dt);
      shot.y += shot.vy * dt;
      if (shot.y < cameraY - 70 || shot.x < -50 || shot.x > width + 50) continue;
      const px = Math.abs(player.x - previousX) > width / 2 ? player.x : previousX;
      const ox = oldX - px, oy = oldY - previousFeet - player.height / 2;
      const dx = shot.x - oldX - (player.x - px), dy = shot.y - oldY - (player.y - previousFeet - player.height / 2);
      const t = clamp(-(ox * dx + oy * dy) / Math.max(.001, dx * dx + dy * dy), 0, 1);
      const hit = ((ox + dx * t) / (6 + player.width * .27)) ** 2
        + ((oy + dy * t) / (6 + player.height * .33)) ** 2 < 1;
      if (hit) { if (invulnerableTimer <= 0) { endGame(); return; } continue; }
      summitShots[kept++] = shot;
    }
    summitShots.length = kept;
  }

  function drawSummitEnemies() {
    if (!summit) return;
    const mob = summitEncounter;
    if (mob) {
      const sy = worldToScreen(mob.y);
      if (sy > -mob.h && sy < height + mob.h) {
        const pose = summitEnemyPose(mob);
        const drawH = mob.type === "drone" && mob.phase === "defeated" ? spriteSize(pose, mob.w) : mob.h;
        ctx.save(); ctx.translate(mob.x, sy);
        if (mob.type === "marmot" && mob.direction > 0) ctx.scale(-1, 1);
        if (mob.phase === "defeated") ctx.rotate(mob.type === "drone" ? mob.direction * mob.timer * 2 : Math.min(.7, mob.timer * .5));
        ctx.drawImage(rasterSprite(pose, mob.w, drawH), -mob.w / 2, -drawH / 2, mob.w, drawH);
        if (mob.type === "drone" && mob.phase === "defeated" && mob.timer < .8) {
          ctx.fillStyle = "#f7cd76";
          for (let i = 0; i < 5; i++) {
            const a = i * Math.PI * 2 / 5, r = 8 + mob.timer * 30;
            ctx.fillRect(Math.cos(a) * r, Math.sin(a) * r, 3, 2);
          }
        }
        if (mob.type === "drone" && mob.phase === "warning" && Math.floor(mob.timer * 8) % 2 === 0) {
          ctx.fillStyle = "#ffda76"; ctx.fillRect(-mob.w * .3, -mob.h * .1, 5, 3);
          ctx.fillRect(mob.w * .3 - 5, -mob.h * .1, 5, 3);
        }
        ctx.restore();
      }
    }
    for (const shot of summitShots) {
      const y = worldToScreen(shot.y);
      if (y < -15 || y > height + 15) continue;
      ctx.save(); ctx.translate(shot.x, y);
      if (shot.type === "snow") {
        ctx.fillStyle = "#b5d2e7"; ctx.beginPath(); ctx.arc(0, 0, 8, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = "#f6fbff"; ctx.fillRect(-5, -5, 8, 7); ctx.fillRect(-2, -7, 5, 3);
      } else {
        ctx.rotate(shot.age * 2); ctx.fillStyle = "#bfbdad"; ctx.strokeStyle = "#424954"; ctx.lineWidth = 2;
        ctx.beginPath();
        for (let i = 0; i < 6; i++) { const a = i * Math.PI / 3; ctx.lineTo(Math.cos(a) * 9, Math.sin(a) * 9); }
        ctx.closePath(); ctx.fill(); ctx.stroke(); ctx.fillStyle = "#303c49";
        ctx.fillRect(-3, -3, 6, 6);
      }
      ctx.restore();
    }
  }

  function goatPose(platform) {
    const t = platform.goat.phase;
    return art.summitGoat[t < 2.2 ? 0 : t < 2.8 ? 1 : t < 3.3 ? 2 : 3];
  }

  function updateSummitGoats(dt, previousFeet, currentFeet, previousX) {
    if (!summit) return;
    for (const platform of platforms) {
      const goat = platform.goat;
      if (!goat || platform.broken || platform.y < cameraY - 90 || platform.y > cameraY + height + 90) continue;
      goat.phase = (goat.phase + dt) % 4;
      goat.cooldown = Math.max(0, goat.cooldown - dt);
      if (goat.kicked && goat.cooldown === 0) goat.kicked = false;
      if (goat.kicked || goat.cooldown > 0) continue;
      const frame = goatPose(platform), w = 48, h = spriteSize(frame, w);
      const hop = goat.phase >= 2.8 && goat.phase < 3.3 ? Math.sin((goat.phase - 2.8) / .5 * Math.PI) * 9 : 0;
      const goatY = platform.y + h / 2 + hop;
      const top = spriteLanding(frame, platform.x, goatY, w, h, platform.previousX ?? platform.x, goatY,
        previousFeet, currentFeet, previousX);
      if (top !== null) {
        player.y = top + player.height / 2; player.vy = 850;
        protectBounce();
        openingJump = false; somersault = null;
        goat.kicked = true; goat.cooldown = 1.2;
      } else if (goat.phase >= 2.8 && goat.phase < 3.3 && invulnerableTimer <= 0
        && spriteOverlapsEllipse(frame, platform.x, goatY, w, h,
          player.x, player.y, player.width * .3, player.height * .35)) {
        // A readable nudge, not a surprise instant death. It cannot repeat every frame.
        player.vx += (player.x < platform.x ? -1 : 1) * 150;
        goat.cooldown = 1.5;
      }
    }
  }

  function drawSummitPlatform(platform) {
    const y = worldToScreen(platform.y), w = platform.spriteWidth;
    if (y < -100 || y > height + 110) return;
    const purple = platform.summitKind === "purple", cable = platform.summitKind === "cable";
    ctx.save();
    if (cable) {
      const frame = art.summitCableCar, h = spriteSize(frame, w);
      ctx.strokeStyle = "#465565"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(0, y - h * .28); ctx.lineTo(width, y - h * .28); ctx.stroke();
      // The roof is 36% down the trimmed sprite; its plane matches the physics.
      ctx.drawImage(rasterSprite(frame, w, h), platform.x - w / 2, y - h * .36, w, h);
      ctx.restore();
      return;
    }
    const frame = art.summitPlatforms[platform.spriteIndex || 0], h = spriteSize(frame, w);
    ctx.drawImage(rasterSprite(frame, w, h), platform.x - w / 2, y, w, h);
    if (purple) {
      ctx.fillStyle = "#b593e8";
      ctx.fillRect(platform.x - platform.hitboxWidth / 2, y, platform.hitboxWidth, 2);
    }
    const goat = platform.goat;
    if (goat && art.summitGoat) {
      const pose = goat.kicked ? art.summitGoat[3] : goatPose(platform), gw = 48, gh = spriteSize(pose, gw);
      const hop = !goat.kicked && goat.phase >= 2.8 && goat.phase < 3.3 ? Math.sin((goat.phase - 2.8) / .5 * Math.PI) * 9 : 0;
      ctx.drawImage(rasterSprite(pose, gw, gh), platform.x - gw / 2, y - gh - hop, gw, gh);
    }
    ctx.restore();
  }

  function spawnSummitCommentator(y = cameraY + height + 120) {
    if (!summit || !art.summitCommentator || summitCommentator) return;
    const x = width * (.35 + Math.random() * .3);
    const w = Math.min(170, width * .36);
    const support = addPlatform(y, x, "normal");
    support.width = support.hitboxWidth = support.spriteWidth = w * 1.1;
    support.commentator = true;
    summitCommentator = {x, y, w, support, phase:"boast", timer:0, age:0, vy:0,
      direction:x < width / 2 ? -1 : 1};
    // At most one encounter, with the next one placed further up the world.
    summitRareLastY = y;
    summitCommentatorNextY = y + 11000 + Math.random() * 4000;
  }

  function updateSummitCommentator(dt, previousFeet, currentFeet, previousPlayerX) {
    if (!summit) { summitCommentator = null; return; }
    if (!summitCommentator && cameraY + height + 180 >= summitCommentatorNextY) {
      const spawnY = cameraY + height + 120;
      if (Math.abs(spawnY - summitRareLastY) < 2200) summitCommentatorNextY = summitRareLastY + 2400;
      else spawnSummitCommentator(spawnY);
    }
    const npc = summitCommentator;
    if (!npc) return;
    npc.age += dt; npc.timer += dt;
    if (npc.phase === "boast" && player.vy < 0 && previousFeet > currentFeet) {
      const pose = art.summitCommentator[1];
      const h = spriteSize(pose, npc.w);
      const oldX = Math.abs(player.x - previousPlayerX) > width / 2 ? player.x : previousPlayerX;
      const steps = Math.max(1, Math.ceil((previousFeet - currentFeet + Math.abs(player.x - oldX)) / 3));
      for (let i = 0; i <= steps; i++) {
        const t = i / steps, x = oldX + (player.x - oldX) * t;
        if (Math.abs(x - npc.x) > npc.w * .43) continue;
        const top = spriteTopAtX(pose, npc.x, npc.y + h / 2, npc.w, h, x);
        const feet = previousFeet + (currentFeet - previousFeet) * t;
        if (top <= npc.y + h * .15 || previousFeet < top || feet > top) continue;
        player.y = top + player.height / 2;
        player.vy = 810;
        openingJump = false; somersault = null;
        npc.phase = "shout"; npc.timer = 0;
        break;
      }
    } else if (npc.phase === "shout" && npc.timer >= .8) {
      npc.phase = "fall"; npc.timer = 0; npc.vy = -35;
    } else if (npc.phase === "fall") {
      npc.vy -= 410 * dt;
      npc.y += npc.vy * dt;
      npc.x += npc.direction * 20 * dt;
    }
    // No timeout while visible: it leaves by falling or scrolling below view.
    if (npc.y + spriteSize(art.summitCommentator[1], npc.w) < cameraY - 100) summitCommentator = null;
  }

  function drawCommentatorPlatform(platform) {
    const y = worldToScreen(platform.y), w = platform.spriteWidth;
    if (y < -20 || y > height + 40) return;
    ctx.save();
    ctx.fillStyle = "#34404c"; ctx.fillRect(platform.x - w / 2, y, w, 10);
    ctx.fillStyle = "#9aabb9"; ctx.fillRect(platform.x - w / 2, y, w, 3);
    ctx.fillStyle = "#b6a36c";
    for (let i = 8; i < w - 4; i += 18) ctx.fillRect(platform.x - w / 2 + i, y + 4, 7, 3);
    ctx.strokeStyle = "#34404c"; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(platform.x - w * .42, y + 10);
    ctx.lineTo(platform.x, y + 27); ctx.lineTo(platform.x + w * .42, y + 10); ctx.stroke();
    ctx.restore();
  }

  function drawSummitCommentator() {
    const npc = summitCommentator;
    if (!summit || !npc) return;
    const index = npc.phase === "fall" ? 3 : npc.phase === "shout" ? 2
      : Math.floor(npc.age * 2) % 5 === 0 ? 0 : 1;
    const pose = art.summitCommentator[index], h = spriteSize(pose, npc.w);
    const feet = worldToScreen(npc.y);
    if (feet < -h - 130 || feet > height + h + 130) return;
    const angle = npc.phase === "fall" ? npc.direction * Math.min(.55, npc.timer * .4)
      : npc.phase === "shout" ? Math.sin(npc.timer * 24) * .018 : 0;
    ctx.save(); ctx.translate(npc.x, feet); ctx.rotate(angle);
    ctx.drawImage(rasterSprite(pose, npc.w, h), -npc.w / 2, -h, npc.w, h);
    // A few foam bubbles follow the bath, without frame-dependent allocations.
    ctx.fillStyle = "#edf8ff";
    for (let i = 0; i < 5; i++) {
      const age = (npc.age * .5 + i / 5) % 1;
      ctx.globalAlpha = (1 - age) * .75;
      ctx.fillRect((i - 2) * npc.w * .15, -h * .58 - age * 15, 3, 3);
    }
    ctx.restore();
    const shout = npc.phase !== "boast";
    if (npc.phase === "fall" && npc.timer > 1.1) return;
    ctx.save(); ctx.font = `bold ${shout ? 13 : 10}px monospace`; ctx.textAlign = "center";
    // Text layout changes only when the phrase or logical viewport changes.
    // Avoid measuring/allocating the same two lines on every animation frame.
    if (!npc.speech || npc.speech.shout !== shout || npc.speech.width !== width) {
      const lines = shout ? ["БАН БАН БАН"] : ["Я САМЫЙ ЛУЧШИЙ", "КОММЕНТАТОР ФОРМУЛЫ 1!"];
      npc.speech = {shout, width, lines,
        bubbleW: Math.min(width - 24, Math.max(...lines.map(line => ctx.measureText(line).width)) + 24)};
    }
    const {lines, bubbleW} = npc.speech;
    const bubbleH = lines.length * 15 + 16;
    const bubbleX = clamp(npc.x - bubbleW / 2, 12, width - bubbleW - 12);
    const bubbleY = feet - h - bubbleH - 10;
    ctx.fillStyle = shout ? "#fff0d2" : "#e9eff2";
    ctx.strokeStyle = "#273847"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.roundRect(bubbleX, bubbleY, bubbleW, bubbleH, 6); ctx.fill(); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(npc.x - 4, bubbleY + bubbleH);
    ctx.lineTo(npc.x + 2, bubbleY + bubbleH + 7); ctx.lineTo(npc.x + 7, bubbleY + bubbleH); ctx.fill();
    ctx.fillStyle = "#1e2b36";
    lines.forEach((line, i) => ctx.fillText(line, bubbleX + bubbleW / 2, bubbleY + 18 + i * 15));
    ctx.restore();
  }

  function beginSidVictory() {
    const boss = sidBoss;
    if (!boss) return;
    effects = []; somersault = null; rocketTimer = 0;
    boss.heroFromX = player.x; boss.heroFromY = player.y;
    const land = platforms.filter(p => !p.broken && p.y <= player.y - player.height / 2)
      .reduce((best, p) => !best || Math.abs(p.x - player.x) + Math.abs(p.y - player.y) < Math.abs(best.x - player.x) + Math.abs(best.y - player.y) ? p : best, null);
    boss.heroLandX = land?.x ?? width / 2;
    boss.heroLandY = (land?.y ?? cameraY + height * .09) + player.height / 2;
    player.vx = player.vy = 0;
    sidPhase("victory");
  }

  async function startSidVictoryTest() {
    if (!adminSandbox && mode === "running" && !adminBossTestMode) return;
    await startSidBossTest();
    if (!adminBossTestMode || !sidBoss) return;
    if (!await preparePreview(["summit"])) return;
    if (!sidBoss || !adminBossTestMode) return;
    sidBoss.hp = 0; sidBoss.hits = 10; sidBoss.shots = [];
    beginSidVictory();
    draw();
    if (bossTestStatus) bossTestStatus.textContent = "Победа над Сидом → высокогорный паддок · тест без записи результата";
  }

  async function startSidBossTest() {
    if (!artReady || (mode === "running" && !adminBossTestMode && !adminSandbox)) return;
    if (!await preparePreview(["sky", "garage", "winter"])) return;
    if (mode === "running" && !adminBossTestMode && !adminSandbox) return;
    await startWinterBiomeTest();
    if (!antarctica || !adminBossTestMode) return;
    peakY = startY + 10000 * 11;
    beginSidBoss(); draw();
    if (bossTestStatus) bossTestStatus.textContent = "Сид · 10 попаданий · тест без сохранения результата";
  }

  async function startCommentatorTest() {
    if (!adminSandbox && mode === "running" && !adminBossTestMode) return;
    await startSidBossTest();
    if (!adminBossTestMode || !sidBoss || !await preparePreview(["summit"])) return;
    if (!adminBossTestMode || !sidBoss) return;
    sidBoss.hp = 0;
    if (!enterSummit()) return;
    enemies = []; hazards = [];
    spawnSummitCommentator(cameraY + height * .4);
    draw();
    if (bossTestStatus) bossTestStatus.textContent = "Комментатор · прыгни сверху на ванну · тест без сохранения результата";
  }

  async function startSummitEnemyTest(type) {
    await startCommentatorTest();
    if (!summit || !adminBossTestMode) return;
    summitCommentator = null;
    summitEncounter = null; summitShots.length = 0;
    platforms = platforms.filter(p => !p.commentator);
    const support = addPlatform(cameraY + height + 160, width * .65, "normal");
    support.width = support.hitboxWidth = support.spriteWidth = 65;
    if (!spawnSummitEnemy(type)) return;
    summitEncounter.y = cameraY + height * .72;
    if (summitEncounter.support) summitEncounter.support.y = summitEncounter.y - summitEncounter.h / 2;
    draw();
    if (bossTestStatus) bossTestStatus.textContent = `${type === "marmot" ? "Сурок · жёлтый флаг и снежок" : "Дрон · предупреждение и сброс гайки"} · тест без сохранения результата`;
  }

  function sceneEase(age, start, end) {
    const t = clamp((age - start) / (end - start), 0, 1);
    return t * t * t * (t * (t * 6 - 15) + 10);
  }

  function sceneMix(from, to, t) { return from + (to - from) * t; }

  function storyHeroHeight() { return Math.min(clamp(width * .2, 76, 104), height * .22); }

  function walkingSprite(distance, actorHeight) {
    const phase = Math.floor(Math.abs(distance) / (actorHeight * .95) * 8) % 8;
    return art.walkFrames[phase];
  }

  function drawStoryActor(sprite, x, feet, actorHeight, angle = 0, scaleX = 1, scaleY = 1, alpha = 1) {
    if (!sprite || alpha <= 0) return;
    const actorWidth = actorHeight * sprite.sw / sprite.sh;
    ctx.save();
    ctx.globalAlpha *= alpha;
    ctx.translate(x, feet);
    ctx.rotate(angle);
    ctx.scale(scaleX, scaleY);
    // Raster size stays fixed while camera/pose transforms animate the image.
    ctx.drawImage(rasterSprite(sprite, actorWidth, actorHeight), -actorWidth / 2, -actorHeight, actorWidth, actorHeight);
    ctx.restore();
  }

  function drawStoryShadow(x, y, radius, alpha) {
    ctx.save(); ctx.globalAlpha *= alpha;
    ctx.fillStyle = "#08121e";
    ctx.beginPath(); ctx.ellipse(x, y + 2, radius, radius * .18, 0, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  function drawCinemaFrame(label, subtitle, visibility = 1) {
    const bar = Math.min(34, Math.max(22, height * .055)) * visibility;
    ctx.save(); ctx.globalAlpha = visibility;
    ctx.fillStyle = "#071019";
    ctx.fillRect(0, 0, width, bar);
    ctx.fillRect(0, height - bar - 14, width, bar + 14);
    ctx.fillStyle = "#a6bac8";
    ctx.textAlign = "left"; ctx.font = "600 10px system-ui";
    ctx.fillText(label, 16, Math.max(17, bar * .64), width - 70);
    ctx.fillStyle = "#edf4f8";
    ctx.textAlign = "center"; ctx.font = `500 ${Math.min(14, width / 28)}px system-ui`;
    if (subtitle) ctx.fillText(subtitle, width / 2, height - (bar + 14) / 2 + 5, width - 32);
    ctx.restore();
  }

  function drawStoryPortal(x, y, radius, age, scenery) {
    if (radius <= .1) return;
    ctx.save(); ctx.translate(x, y);
    ctx.fillStyle = "rgba(91,190,239,.08)";
    ctx.beginPath(); ctx.ellipse(0, 0, radius * 1.3, radius * 1.5, 0, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.ellipse(0, 0, radius, radius * 1.16, 0, 0, Math.PI * 2);
    ctx.save(); ctx.clip();
    ctx.fillStyle = "#0b1d37"; ctx.fillRect(-radius, -radius * 1.2, radius * 2, radius * 2.4);
    if (scenery) ctx.drawImage(scenery, -radius, -radius * 1.16, radius * 2, radius * 2.32);
    ctx.fillStyle = `rgba(120,205,250,${.12 + Math.sin(age * 5) * .06})`;
    ctx.fillRect(-radius, -radius * 1.2, radius * 2, radius * 2.4);
    ctx.restore();
    for (let ring = 0; ring < 3; ring += 1) {
      ctx.strokeStyle = ring % 2 ? "#e2faff" : "#71c5f1";
      ctx.lineWidth = ring ? 1.5 : 3;
      ctx.beginPath(); ctx.ellipse(0, 0, radius + ring * 4, radius * 1.16 + ring * 3,
        Math.sin(age * 2.5 + ring) * .08, age * .4 + ring, age * .4 + ring + Math.PI * 1.8); ctx.stroke();
    }
    for (let i = 0; i < 24; i += 1) {
      const angle = i * Math.PI / 12 + age * .9;
      const r = radius * (1.15 + (1 - (age * .75 + i / 24) % 1) * .7);
      ctx.globalAlpha = .25 + (i % 3) * .2;
      ctx.strokeStyle = "#beeaff"; ctx.lineWidth = i % 3 ? 1 : 2;
      ctx.beginPath(); ctx.moveTo(Math.cos(angle) * r, Math.sin(angle) * r * 1.16);
      ctx.lineTo(Math.cos(angle - .05) * r * .91, Math.sin(angle - .05) * r * 1.06); ctx.stroke();
    }
    ctx.restore();
  }

  function controlHeroMotion(age, scene, floorY, heroHeight, portalX, portalY) {
    const landing = sceneEase(age, 0, 1.45), approach = sceneEase(age, 2.0, 3.15);
    const shove = sceneEase(age, 4.42, 5.1), suction = sceneEase(age, 8.25, 10.65);
    let x = sceneMix(scene.fromX * width, width * .38, landing) + width * .09 * approach - width * .24 * shove;
    let feet = sceneMix(scene.fromY * height + player.height / 2, floorY, landing)
      - Math.sin(landing * Math.PI) * Math.min(125, height * .17) - Math.sin(shove * Math.PI) * heroHeight * .5;
    if (age > 2 && age < 3.15) feet -= Math.abs(Math.sin(age * 12)) * 2;
    x = sceneMix(x, portalX + Math.sin(suction * Math.PI * 2) * width * .06, suction);
    feet = sceneMix(feet, portalY + heroHeight * .3, suction);
    return { x, feet, shove, suction, rotation: -shove * .25 * (1 - sceneEase(age, 5.25, 5.8)) + suction * Math.PI * 2.4 };
  }

  function drawAntarcticaScene() {
    const scene = antarcticaScene, age = scene.age;
    const ease = (from, to) => sceneEase(age, from, to);
    const floorY = height * .71, heroHeight = storyHeroHeight();
    const consoleWidth = Math.min(width * .31, 174, height * .25), consoleHeight = spriteSize(art.controlConsole, consoleWidth);
    const consoleX = width * .63, buttonX = consoleX + consoleWidth * .79;
    const buttonY = floorY - consoleHeight * .79;
    const portalX = width * .245, portalY = floorY - heroHeight * 1.7;
    const buttonShot = ease(5.95, 6.55) * (1 - ease(7.35, 8.0));
    const portalShot = ease(7.8, 8.65);
    const zoom = 1 + buttonShot * .72 + portalShot * .08;
    const focusX = sceneMix(width * .5, buttonX - width * .08, buttonShot) - portalShot * width * .045;
    const focusY = sceneMix(height * .53, buttonY + heroHeight * .15, buttonShot);
    const impactAge = age - 4.45;
    const impact = impactAge > 0 ? Math.exp(-impactAge * 15) : 0;
    const pressAge = age - 6.92;
    const pressImpact = pressAge > 0 ? Math.exp(-pressAge * 16) : 0;
    ctx.save();
    ctx.fillStyle = "rgba(3,12,20,.22)"; ctx.fillRect(0, 0, width, height);
    ctx.translate(width / 2 + Math.sin(age * 91) * impact * 3, height * .53 + Math.sin(age * 75) * pressImpact * 2);
    ctx.scale(zoom, zoom); ctx.translate(-focusX, -focusY);
    // Floor depth, foot shadows and suspended dust ground the actors.
    ctx.fillStyle = "#111d28"; ctx.fillRect(width * .025, floorY + 10, width * .95, height * .2);
    ctx.fillStyle = "#34444e"; ctx.fillRect(width * .025, floorY, width * .95, 16);
    ctx.fillStyle = "#8b999e"; ctx.fillRect(width * .025, floorY, width * .95, 3);
    for (let i = 0; i < 12; i += 1) {
      const x = width * (.04 + i * .08);
      ctx.fillStyle = i % 2 ? "#b49a54" : "#30373b"; ctx.fillRect(x, floorY + 8, width * .04, 4);
      ctx.fillStyle = "#3d4b54"; ctx.fillRect(x, floorY + 20, 4, height * .12);
    }
    ctx.fillStyle = "#46535a"; ctx.fillRect(width * .025, floorY + height * .11, width * .95, 3);
    for (let i = 0; i < 16; i += 1) {
      ctx.globalAlpha = .1 + i % 3 * .06; ctx.fillStyle = "#adbbc7";
      ctx.fillRect((decorRandom(i, 11) * width + age * 3) % width, floorY - decorRandom(i, 14) * height * .5, 1, 1);
    }
    ctx.globalAlpha = 1;
    drawStoryShadow(consoleX + consoleWidth / 2, floorY, consoleWidth * .48, .5);
    const buttonPress = ease(6.8, 6.96) * (1 - ease(7.15, 7.4));
    ctx.save(); ctx.translate(0, buttonPress * 2);
    ctx.drawImage(rasterSprite(art.controlConsole, consoleWidth, consoleHeight), consoleX, floorY - consoleHeight, consoleWidth, consoleHeight);
    ctx.restore();
    if (age > 6.9) {
      ctx.save(); ctx.globalAlpha = .1 + Math.sin(age * 8) * .025;
      ctx.fillStyle = "#fb4539"; ctx.beginPath(); ctx.ellipse(buttonX, buttonY, consoleWidth * .24, consoleWidth * .19, 0, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
      ctx.fillStyle = "#f36a59";
      for (let i = 0; i < 4; i += 1) ctx.fillRect(consoleX + consoleWidth * (.14 + i * .12), floorY - consoleHeight * .54, 3, 2);
    }
    const bossHeight = heroHeight * 1.38;
    const bossEnter = ease(3.25, 4.15), bossStep = ease(5.6, 6.35);
    const pressX = buttonX - bossHeight * .3;
    const bossX = sceneMix(width * 1.15, width * .61, bossEnter) + (pressX - width * .61) * bossStep;
    if (age > 3.25) {
      const pose = age > 4.25 && age < 5.15 ? 1 : age > 6.25 && age < 7.55 ? 2 : age >= 7.55 ? 3 : 0;
      const lunge = Math.sin(ease(4.28, 4.7) * Math.PI) * 5;
      drawStoryShadow(bossX, floorY, bossHeight * .23, .5);
      drawStoryActor(art.totoStoryFrames[pose], bossX - lunge, floorY, bossHeight,
        age < 4.15 ? -.035 * Math.sin(age * 14) : 0, 1, 1 - buttonPress * .025);
    }
    const portalGrow = ease(7.45, 8.5);
    drawStoryPortal(portalX, portalY, Math.min(width * .2, 98, height * .16) * portalGrow, age, art.caveArrival);
    const motion = controlHeroMotion(age, scene, floorY, heroHeight, portalX, portalY);
    const landingBounce = Math.sin(clamp((age - 1.45) / .32, 0, 1) * Math.PI) * .13;
    const heroPose = age < 1.45 ? art.heroFrames[1] : age < 1.8 ? art.heroStoryFrames[4]
      : age > 4.42 && age < 5.8 ? art.heroStoryFrames[3]
        : age > 8.25 ? art.heroFrames[2] : age > 2 && age < 3.15 ? walkingSprite(width * .09 * ease(2, 3.15), heroHeight) : art.heroStoryFrames[0];
    drawStoryShadow(motion.x, floorY, heroHeight * (.23 - motion.suction * .12), .36 * (1 - motion.suction));
    if (age > 8.4 && age < 10.6) {
      for (let i = 3; i > 0; i -= 1) {
        const ghost = controlHeroMotion(age - i * .07, scene, floorY, heroHeight, portalX, portalY);
        drawStoryActor(heroPose, ghost.x, ghost.feet, heroHeight, ghost.rotation, 1 - ghost.suction * .97, 1 - ghost.suction * .97, .055);
      }
    }
    drawStoryActor(heroPose, motion.x, motion.feet, heroHeight, motion.rotation,
      (1 + landingBounce) * (1 - motion.suction * .97), (1 - landingBounce) * (1 - motion.suction * .97), 1 - motion.suction);
    ctx.restore();
    // A short impact flash and a matching cold-white portal cut punctuate actions.
    if (impact > .02) { ctx.save(); ctx.globalAlpha = impact * .07; ctx.fillStyle = "#edf6ff"; ctx.fillRect(0, 0, width, height); ctx.restore(); }
    drawCinemaFrame("ВЕРХНИЙ ЭТАЖ / ПУЛЬТ БОЛЛИДА", age > 4 && age < 6 ? "Тото: «Я сам.»" : age > 7.5 && age < 9.1 ? "Маршрут изменён." : "");
    if (age > 10.65) { ctx.save(); ctx.globalAlpha = ease(10.65, controlSceneDuration); ctx.fillStyle = "#d9edff"; ctx.fillRect(0, 0, width, height); ctx.restore(); }
  }

  function drawAntarcticaArrival() {
    const age = antarcticaArrival.age, ease = (a, b) => sceneEase(age, a, b);
    const source = art.caveArrival;
    const sceneWidth = Math.max(width * 1.8, height * source.naturalWidth / source.naturalHeight);
    const sceneHeight = sceneWidth * source.naturalHeight / source.naturalWidth;
    const floorY = height * .76;
    const heroHeight = storyHeroHeight();
    const portalX = sceneWidth * .24, heroStart = portalX + heroHeight * .28;
    const heroEnd = sceneWidth * .7, sidX = heroEnd + width * .46;
    const walk = ease(2.0, 4.9), jump = ease(7.1, 8.85), handoff = ease(8.25, 9.65);
    const pan = ease(1.8, 5.0);
    const cameraX = clamp(sceneMix(portalX - width * .32, heroEnd - width * .42, pan), 0, sceneWidth - width);
    ctx.save(); ctx.globalAlpha = 1 - handoff;
    ctx.drawImage(source, -cameraX, floorY - sceneHeight * .78, sceneWidth, sceneHeight);
    // Near-field snow sweeps past more quickly than the panoramic cave walls.
    for (let i = 0; i < 24; i += 1) {
      const x = (decorRandom(i, 73) * sceneWidth + age * (12 + i % 7)) % sceneWidth - cameraX;
      if (x < sceneWidth * .54 - cameraX) continue;
      ctx.globalAlpha = (1 - handoff) * (.2 + i % 3 * .17); ctx.fillStyle = "#e7f6ff";
      ctx.fillRect(x, (decorRandom(i, 81) * height + age * (15 + i % 8)) % height, 2, 2);
    }
    ctx.globalAlpha = 1 - handoff;
    const collapse = 1 - ease(1.0, 1.75);
    drawStoryPortal(portalX - cameraX, floorY - heroHeight, heroHeight * .66 * collapse, age + 11, art.garage);
    const sidPose = age < 4.65 ? 0 : age < 5.25 ? 1 : age < 6.3 ? 2 : 3;
    const sidHeight = heroHeight * 1.3;
    drawStoryShadow(sidX - cameraX, floorY, sidHeight * .25, .3);
    drawStoryActor(art.sidFrames[sidPose], sidX - cameraX, floorY, sidHeight, Math.sin(age * 2.5) * .012);
    // A small snow burst and two settling bounces give the portal landing weight.
    const landing = ease(0, .8), stand = ease(1.1, 1.8);
    let heroX = sceneMix(portalX - heroHeight * .12, heroStart, landing) + (heroEnd - heroStart) * walk - cameraX;
    let heroFeet = floorY - (1 - landing) * heroHeight * .9 - Math.abs(Math.sin(age * 10)) * (1 - stand) * (age > .8 ? 2.5 : 0);
    if (age > 2 && age < 4.9) heroFeet -= Math.abs(Math.sin(age * 13)) * 2;
    const finalFeet = worldToScreen(player.y) + player.height / 2;
    heroX = sceneMix(heroX, player.x, jump);
    heroFeet = sceneMix(heroFeet, finalFeet, jump) - Math.sin(jump * Math.PI) * Math.min(85, height * .12);
    if (age > .7 && age < 1.6) {
      const puff = clamp((age - .7) / .9, 0, 1);
      ctx.save(); ctx.globalAlpha *= 1 - puff; ctx.fillStyle = "#dcefff";
      for (let i = 0; i < 12; i += 1) {
        const direction = i % 2 ? -1 : 1;
        ctx.fillRect(heroStart - cameraX + direction * (5 + puff * (18 + i * 2)), floorY - Math.sin(puff * Math.PI) * (6 + i * 1.5), 3, 2);
      }
      ctx.restore();
    }
    ctx.restore();
    // The previewed landing platform is the actual collision platform used
    // when control resumes; cinematic and gameplay positions share a baseline.
    if (age > 6.3) {
      ctx.save(); ctx.globalAlpha = ease(6.3, 7.0);
      drawIcePlatform(platforms[0]);
      ctx.globalAlpha = handoff;
      for (let i = 1; i < platforms.length; i += 1) drawIcePlatform(platforms[i]);
      ctx.restore();
    }
    const shrink = sceneMix(1, player.height / heroHeight, handoff);
    const turn = age < .8 ? (1 - landing) * -Math.PI * 1.4 : age > 2 && age < 4.9 ? Math.sin(age * 13) * .025 : 0;
    const pose = age < 1.4 ? art.heroStoryFrames[4] : age > 7.1 ? (age > 8.85 ? art.heroFrames[0] : art.heroFrames[1])
      : age > 2 && age < 4.9 ? walkingSprite((heroEnd - heroStart) * walk, heroHeight) : age > 6 ? art.heroStoryFrames[5] : art.heroStoryFrames[0];
    drawStoryShadow(heroX, floorY, heroHeight * .23, .27 * (1 - jump));
    drawStoryActor(pose, heroX, heroFeet, heroHeight, turn, shrink, shrink);
    const subtitle = age > 5.2 && age < 6.3 ? "Сид: «Ты потерялся?»" : age >= 6.3 && age < 7.4 ? "Сид: «Тебе наверх!»" : "";
    drawCinemaFrame("АНТАРКТИДА / ЛЕДЯНАЯ ПЕЩЕРА", subtitle, 1 - ease(8.85, caveSceneDuration));
    if (age < .5) { ctx.save(); ctx.globalAlpha = 1 - ease(0, .5); ctx.fillStyle = "#d9edff"; ctx.fillRect(0, 0, width, height); ctx.restore(); }
  }

  async function startAntarcticaPreview(arrivalOnly = false) {
    if (!artReady) return;
    if (mode === "running" && !adminBossTestMode && !adminSandbox) {
      if (bossTestStatus) bossTestStatus.textContent = "Сначала завершите текущий забег";
      return;
    }
    if (!await preparePreview(["garage", "winter"])) return;
    if (mode === "running" && !adminBossTestMode && !adminSandbox) return;
    startGame(true, { forceRestart: true, adminTest: true });
    forgottenPaddock = true;
    peakY = player.y = startY + 8000 * 11;
    player.x = width / 2;
    cameraY = player.y - cameraTrackingOffset();
    openingJump = false;
    freeFlight = false;
    if (flightButton) { flightButton.setAttribute("aria-pressed", "false"); flightButton.textContent = "Свободный полёт: выкл."; }
    beginAntarcticaScene();
    if (arrivalOnly) enterAntarctica();
    if (bossTestStatus) bossTestStatus.textContent = arrivalOnly ? "Тест пещеры · рекорд и попытка не сохраняются" : "Тест Антарктиды · рекорд и попытка не сохраняются";
    updateHud(); draw();
  }

  function startAntarcticaTest() { return startAntarcticaPreview(false); }

  async function startWinterBiomeTest() {
    if (!artReady) return;
    if (mode === "running" && !adminBossTestMode && !adminSandbox) {
      if (bossTestStatus) bossTestStatus.textContent = "Сначала завершите текущий забег";
      return;
    }
    await startAntarcticaPreview(true);
    if (!antarcticaArrival || !adminBossTestMode) return;
    finishAntarcticaArrival();
    antarcticaEntryScore = runScore() - 100;
    winterMemoryStartedAt = elapsed - 2;
    enemies = [.22, .78].map((lane, i) => ({ type: "piranha", x: width * lane, baseX: width * lane,
      y: cameraY + height * (.72 + i * .16), phase: i * 1.7, variant: 0, dead: false }));
    if (bossTestStatus) bossTestStatus.textContent = "Тест зимы · пираньи и фон +100 · без записи результата";
    draw();
  }

  function drawPortal() {
    if (!portalTransition) return;
    const age = portalTransition.age;
    const growth = Math.min(1, age / .7);
    const radius = Math.min(width * .22, 110) * growth;
    ctx.save();
    ctx.fillStyle = `rgba(3, 5, 16, ${Math.min(.75, age * .3)})`;
    ctx.fillRect(0, 0, width, height);
    ctx.translate(width / 2, height * .26);
    ctx.rotate(age * .8);
    for (let ray = 0; ray < 12; ray += 1) {
      ctx.rotate(Math.PI / 6);
      ctx.strokeStyle = ray % 2 ? "#ac8be6" : "#f3eaff";
      ctx.lineWidth = ray % 2 ? 2 : 4;
      ctx.beginPath();
      ctx.moveTo(radius * .8, 0);
      ctx.lineTo(radius * (1.5 + .2 * Math.sin(age * 2 + ray)), 0);
      ctx.stroke();
    }
    ctx.fillStyle = "#020207";
    ctx.beginPath(); ctx.arc(0, 0, radius, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "#c29cfa"; ctx.lineWidth = 5; ctx.stroke();
    ctx.strokeStyle = "#f0e4ff"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.ellipse(0, 0, radius * 1.3, radius * .45, -.4, 0, Math.PI * 2); ctx.stroke();
    ctx.restore();
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
    const spriteHeight = spriteSize(antarctica || summit ? art.winterPlatforms[spriteIndex] : sprites[spriteIndex], spriteWidth);
    const platform = {
      x,
      originX: x,
      y,
      width: platformWidth,
      hitboxWidth: kind === "spring" ? spriteWidth * (antarctica || summit ? .36 : .72) : platformWidth,
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

  function choosePlatformX(previousX, gap, movementReserve = 0) {
    const minX = width * .14;
    const maxX = width * .86;
    const jumpSpeed = 720;
    const gravity = 1240;
    const discriminant = Math.max(0, jumpSpeed * jumpSpeed - 2 * gravity * gap);
    const landingTime = (jumpSpeed + Math.sqrt(discriminant)) / gravity;
    const horizontalSpeed = Math.min(440, width * .62);
    const maxOffset = Math.max(36, Math.min(width * .35, horizontalSpeed * landingTime * .72) - movementReserve);
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
    summitCommentator = null; summitCommentatorNextY = 0;
    summitPlatformIndex = 0; summitGoatNextY = 0; summitRareLastY = -Infinity;
    summitEncounter = null; summitShots.length = 0; summitEnemyNextY = 0;
    sidBoss = null;
    sidBossCleared = false;
    summit = false;
    summitEntryY = 0;
    resetSpaceEncounters();
    resetWinterEncounters();
    waitingForStage = null;
    antarctica = false;
    antarcticaScene = null;
    antarcticaArrival = null;
    antarcticaEntryY = 0;
    antarcticaEntryScore = 0;
    winterMemoryStartedAt = null;
    machine.classList.remove("is-story");
    babyKimi = null;
    kimiWait = 12 + Math.random() * 8;
    kimiBoost = 0;
    lastEnemyVariant = -1;
    forgottenPaddock = false;
    portalTransition = null;
    arrivalUntil = 0;
    const heroHeight = 70 * visualScale();
    // Preserve the previous gameplay hitbox independently of the new hat/arms.
    const heroWidth = heroHeight * .75;
    const firstY = Math.max(150, Math.min(190, height * .22));
    platforms = [];
    enemies = [];
    hazards = [];
    hawks = [];
    hawkSpawnWait = 2 + Math.random() * 2;
    skyFlock = null; totoCloud = null;
    skyFlockWait = 4; totoCloudWait = 7;
    spaceBoss = null;
    bossShots = [];
    guaranteedSpaceBossSpawned = false;
    bossBonus = 0;
    bossVictoryUntil = 0;
    marshals = [];
    nextMarshalY = 1800;
    marshalBonus = 0;
    bonusNoticeUntil = 0;
    bossWait = 90 + Math.random() * 60;
    powerups = [];
    effects = [];
    cameraY = 0;
    openingJump = true;
    somersault = null;
    nextSomersaultAt = 2;
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

    enemies.push({ x: width * .73, baseX: width * .73, y: 440, variant: nextEnemyVariant(), phase: Math.random() * 6, dead: false });
    extendWorld();
    updateHud();
    draw();
  }

  function extendWorld() {
    if (sidBoss) return;
    const targetWorldTop = cameraY + height + 420;
    while (worldTop < targetWorldTop) {
      // Bath supports can be appended behind the route's current highest point.
      // Continue from the highest generated foothold, not the last array entry.
      const lastPlatform = platforms.reduce((highest, platform) =>
        !highest || platform.y > highest.y ? platform : highest, null);
      const lastX = lastPlatform ? lastPlatform.x : width / 2;
      const gap = summit ? summitPlatformGap() : platformGap();
      const y = worldTop + gap;
      const nextX = choosePlatformX(lastX, gap, summit ? (lastPlatform?.kind === "moving" ? lastPlatform.range : 0) + 16 : 0);
      const nextPlatform = addPlatform(y, nextX, selectPlatformKind());
      if (summit) decorateSummitPlatform(nextPlatform);
      if (summit && summitPlatformIndex % 3 === 0) {
        const sideX = nextX < width / 2 ? width * .78 : width * .22;
        if (Math.abs(sideX - nextX) > 85) {
          const side = addPlatform(y - 35, sideX, "normal");
          side.summitSide = true;
        }
      }
      addPowerupBetween(lastPlatform, nextPlatform);
      if (y >= nextMarshalY && nextPlatform.kind === "normal") {
        marshals.push({ platform: nextPlatform, collected: false });
        nextMarshalY = y + 1800 + Math.random() * 1000;
      }
      worldTop = y;
    }

    if (!summit && elapsed >= arrivalUntil && !spaceEncounter && !spaceBoss && (!antarctica || (!winterEncounter && !winterProjectiles.length))
      && (!enemies.length || worldTop - enemies[enemies.length - 1].y > (antarctica ? 370 : 490))) {
      const enemyX = width * (.18 + Math.random() * .64);
      enemies.push({
        type: antarctica || summit ? "piranha" : "tire",
        variant: nextEnemyVariant(),
        x: enemyX,
        baseX: enemyX,
        y: worldTop - 100,
        phase: Math.random() * Math.PI * 2,
        dead: false,
      });
    }
    if (antarctica && !summit) hazards.length = 0;
    const hazardSpacing = !forgottenPaddock && cameraY < spaceFade.start ? 560 : 430;
    if (elapsed >= arrivalUntil && (summit || !antarctica) && !spaceEncounter && !spaceBoss
      && (!hazards.length || worldTop - hazards[hazards.length - 1].y > (summit ? 720 : hazardSpacing))
      && (!summit || hazards.length < 3)) {
      const spriteIndex = Math.random() < .68 ? 5 : 6;
      const compoundRoll = Math.random();
      const compound = spriteIndex === 5
        ? (compoundRoll < .34 ? "soft" : compoundRoll < .67 ? "medium" : "hard")
        : null;
      hazards.push({
        x: width * (.13 + Math.random() * .74),
        y: worldTop + 90,
        speed: summit ? 100 + Math.random() * 35 : 100 + Math.random() * 48 + Math.min(75, cameraY * .012),
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
    const score = runScore();
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
    const displayName = summit ? "Высокогорный паддок" : sidBoss ? "Сид · босс" : antarctica ? "Антарктида" : forgottenPaddock ? "Забытый паддок" : backgroundZoneNames[zoneIndex];
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
      attempts.textContent = new Intl.NumberFormat("ru-RU").format(record.attempts);
      attempts.setAttribute("aria-label", `${record.attempts} попыток`);
      row.append(rank, name, score, attempts);
      leaderboardNode.appendChild(row);
    });
  }

  function applyLeaderboard(data) {
    if (!data) return;
    const title = document.getElementById("doodle-leaderboard-title");
    if (title && data.board_title) title.textContent = data.board_title;
    if (Array.isArray(data.records)) renderLeaderboard(data.records);
    if (totalAttemptsNode && Number.isFinite(data.total_attempts)) totalAttemptsNode.textContent = String(data.total_attempts);
  }

  function registerAttempt() {
    if (adminSandbox || adminBossTestMode) return;
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
    if (adminSandbox || adminBossTestMode) return;
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

  function finishIntro() {
    if (mode !== "intro") return;
    intro = null;
    mode = "running";
    machine.classList.remove("is-intro");
    if (introSkipButton) introSkipButton.hidden = true;
    if (introCaption) introCaption.textContent = "Забег начался.";
    releaseTouchControls();
    const firstPlatform = platforms[0];
    player.x = firstPlatform.x;
    player.y = firstPlatform.y + player.height / 2;
    player.vx = 0;
    player.vy = 720;
    facing = -1;
    registerAttempt();
    updateHud();
    canvas.focus({ preventScroll: true });
  }

  function updateIntro(dt) {
    if (!intro) return;
    const previousAge = intro.age;
    intro.age += dt;
    if (introCaption && previousAge < .55 && intro.age >= .55) {
      introCaption.textContent = "Леклер: «В первый раз?»";
    }
    if (introCaption && previousAge < 2.25 && intro.age >= 2.25) {
      introCaption.textContent = "Рассел снимает петлю и прыгает на первую платформу.";
    }
    if (intro.age >= introDuration) finishIntro();
  }

  function drawIntroActor(sprite, x, feetY, actorHeight, flipped = false) {
    const actorWidth = actorHeight * sprite.sw / sprite.sh;
    ctx.save();
    ctx.translate(x, feetY);
    if (flipped) ctx.scale(-1, 1);
    ctx.drawImage(rasterSprite(sprite, actorWidth, actorHeight),
      -actorWidth / 2, -actorHeight, actorWidth, actorHeight);
    ctx.restore();
  }

  function drawIntroRope(anchorX, beamY, loopX, loopY, rx, ry, layer = "back") {
    ctx.save();
    // Back strand/arc are occluded by the actor. Only the small front arc
    // crosses the neck, never an entire ring across the face or torso.
    ctx.lineCap = "round";
    for (const [color, thickness] of [["#51301d", 1.7], ["#d8b47a", .8]]) {
      ctx.strokeStyle = color;
      ctx.lineWidth = thickness;
      if (layer === "back") {
        ctx.beginPath();
        ctx.moveTo(anchorX, beamY);
        ctx.quadraticCurveTo(anchorX, loopY - ry - 12, loopX + rx, loopY);
        ctx.stroke();
      }
      ctx.beginPath();
      ctx.ellipse(loopX, loopY, rx, ry, 0,
        layer === "back" ? Math.PI : 0, layer === "back" ? Math.PI * 2 : Math.PI);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawIntro() {
    const age = intro.age;
    const leap = clamp((age - 3.5) / 1.55, 0, 1);
    const ease = leap * leap * (3 - 2 * leap);
    const zoom = 1.32 - .32 * ease;
    const stageWidth = Math.min(width * .68, 390);
    const stageHeight = spriteSize(art.introScaffold, stageWidth);
    const stageX = (width - stageWidth) / 2;
    const feetY = height - 80;
    const stageY = feetY - stageHeight * .75;
    const beamY = stageY + stageHeight * .1;
    const heroX = stageX + stageWidth * .66;
    const driverX = stageX + stageWidth * .36;
    const actorHeight = player.height;
    const driverHeight = actorHeight * 1.08;
    // Coordinates measured against the trimmed standing sprites.
    const driverNeckX = driverX - driverHeight * .018;
    const driverNeckY = feetY - driverHeight * .795;
    const lift = clamp((age - 2.25) / .85, 0, 1);
    const release = clamp((age - 3.1) / .4, 0, 1);
    const loopX = heroX - actorHeight * .025 + release * (16 + Math.sin((age - 3.1) * 5) * 5);
    const loopY = feetY - actorHeight * (.62 + lift * .52);
    const loopRX = actorHeight * (.055 + lift * .295 - release * .12);
    const loopRY = actorHeight * (.022 + lift * .12);
    const stageOpacity = 1 - clamp((age - 4.05) / 1, 0, 1);

    ctx.save();
    // Zoom out around the ground as the actor joins the real game world.
    ctx.translate(width / 2, height);
    ctx.scale(zoom, zoom);
    ctx.translate(-width / 2, -height);
    drawBackdrop();
    ctx.save();
    ctx.globalAlpha = clamp((age - 3.15) / .7, 0, 1);
    for (const platform of platforms) {
      drawSprite(platform.spriteIndex, platform.x, platform.y,
        platform.spriteWidth, "platform", platform.height);
    }
    ctx.restore();

    ctx.save();
    ctx.globalAlpha = stageOpacity;
    ctx.drawImage(rasterSprite(art.introScaffold, stageWidth, stageHeight),
      stageX, stageY, stageWidth, stageHeight);
    drawIntroRope(driverX + actorHeight * .3, beamY,
      driverNeckX, driverNeckY, driverHeight * .045, driverHeight * .02);
    drawIntroActor(art.introDriver, driverX, feetY, driverHeight);
    drawIntroRope(driverX + actorHeight * .3, beamY,
      driverNeckX, driverNeckY, driverHeight * .045, driverHeight * .02, "front");
    drawIntroRope(heroX + actorHeight * .34, beamY, loopX, loopY, loopRX, loopRY);
    ctx.restore();

    if (age < 3.5) {
      const pose = art.introHeroFrames[age < 2.25 ? 0 : age < 3.1 ? 1 : 2];
      const poseHeight = actorHeight * pose.sh / art.introHeroFrames[0].sh;
      drawIntroActor(pose, heroX, feetY, poseHeight, true);
    } else {
      const firstPlatform = platforms[0];
      const destinationFeet = worldToScreen(firstPlatform.y);
      const x = heroX + (firstPlatform.x - heroX) * ease;
      const y = feetY + (destinationFeet - feetY) * leap - Math.sin(leap * Math.PI) * 112;
      const pose = art.heroFrames[leap >= 1 ? 0 : leap < .5 ? 1 : 3];
      drawIntroActor(pose, x, y, actorHeight, true);
    }

    ctx.save();
    ctx.globalAlpha = stageOpacity;
    drawIntroRope(heroX + actorHeight * .34, beamY, loopX, loopY, loopRX, loopRY, "front");

    if (age >= .55 && age < 2.9) {
      const bubbleWidth = 100;
      const bx = driverX - bubbleWidth / 2;
      const by = feetY - driverHeight - 30;
      ctx.fillStyle = "#fff5df";
      ctx.strokeStyle = "#80674d";
      ctx.lineWidth = 1;
      ctx.shadowColor = "rgba(42, 29, 18, .25)";
      ctx.shadowOffsetY = 2;
      ctx.beginPath();
      ctx.moveTo(bx + 3, by);
      ctx.lineTo(bx + bubbleWidth - 3, by);
      ctx.lineTo(bx + bubbleWidth, by + 3);
      ctx.lineTo(bx + bubbleWidth, by + 19);
      ctx.lineTo(bx + bubbleWidth - 3, by + 22);
      ctx.lineTo(driverX + 4, by + 22);
      ctx.lineTo(driverX, by + 27);
      ctx.lineTo(driverX - 4, by + 22);
      ctx.lineTo(bx + 3, by + 22);
      ctx.lineTo(bx, by + 19);
      ctx.lineTo(bx, by + 3);
      ctx.closePath();
      ctx.fill();
      ctx.shadowColor = "transparent";
      ctx.stroke();
      ctx.fillStyle = "#3e2d24";
      ctx.font = "bold 10px 'Courier New', monospace";
      ctx.textAlign = "center";
      ctx.fillText("В первый раз?".slice(0, Math.floor((age - .55) * 24)), driverX, by + 14);
    }
    ctx.restore();
    ctx.restore();
  }

  function startGame(skipIntro = false, { forceRestart = false, adminTest = false } = {}) {
    if (!artReady) return;
    if (!adminTest && !isGameFullscreen()) void toggleFullscreen();
    if (!forceRestart && mode === "intro") { finishIntro(); return; }
    if (!forceRestart && mode === "running") return;
    adminBossTestMode = adminTest;
    if (bossTestStatus && !adminTest) bossTestStatus.textContent = "Тест не влияет на рекорды и число попыток";
    if (bossTestStatus && adminTest) bossTestStatus.textContent = "Тестовый бой · рекорд и попытка не сохраняются";
    cancelAnimationFrame(frame);
    buildGame();
    mode = "intro";
    intro = { age: 0 };
    machine.classList.add("is-intro");
    if (introSkipButton) introSkipButton.hidden = false;
    if (introCaption) introCaption.textContent = "Паддок. Рассел и Леклер стоят на эшафоте.";
    updateAccumulator = 0;
    nextHudUpdate = 0;
    setOverlay("running");
    if (skipIntro || alwaysSkipIntro || !art.introScaffold || !art.introDriver || art.introHeroFrames.length !== 3) finishIntro();
    previousTime = performance.now();
    lastRenderTime = previousTime;
    frame = requestAnimationFrame(loop);
    canvas.focus({ preventScroll: true });
  }

  async function startTotoBossTest() {
    if (!artReady) return;
    if (mode === "running" && !adminBossTestMode) {
      if (bossTestStatus) bossTestStatus.textContent = "Сначала завершите текущий забег, чтобы не потерять его попытку";
      return;
    }

    if (!await preparePreview(["sky", "space"])) return;
    if (mode === "running" && !adminBossTestMode) return;

    startGame(true, { forceRestart: true, adminTest: true });
    if (mode !== "running" || !player) return;

    const encounterScore = 3500;
    player.x = width / 2;
    player.y = startY + encounterScore * 11;
    player.vx = 0;
    player.vy = 720;
    peakY = player.y;
    cameraY = Math.max(spaceFade.end + 240, player.y - cameraTrackingOffset());
    openingJump = false;
    forgottenPaddock = false;
    portalTransition = null;
    rocketTimer = 0;
    invulnerableTimer = 0;
    freeFlight = false;
    if (flightButton) {
      flightButton.setAttribute("aria-pressed", "false");
      flightButton.textContent = "Свободный полёт: выкл.";
    }

    // A short ladder of safe launch pads keeps the test alive until the boss
    // finishes its entrance and opens the stomp target.
    platforms = [];
    addPlatform(player.y - player.height / 2 - 10, player.x, "normal");
    let platformY = player.y + 125;
    const platformLimit = cameraY + height + 440;
    while (platformY < platformLimit) {
      addPlatform(platformY, width / 2, "normal");
      platformY += 132;
    }
    worldTop = platforms[platforms.length - 1].y;
    enemies = [];
    hazards = [];
    hawks = [];
    powerups = [];
    marshals = [];
    effects = [];
    spaceBoss = null;
    bossShots = [];
    guaranteedSpaceBossSpawned = false;
    bossBonus = 0;
    bossVictoryUntil = 0;
    bossWait = 90;
    updateHud();
    draw();
    canvas.focus({ preventScroll: true });
  }

  function endGame() {
    if (mode !== "running") return;
    mode = "over";
    somersault = null;
    const heightPoints = Math.max(0, Math.floor((peakY - startY) / 11));
    finalScore = heightPoints + frags * 30 + marshalBonus + bossBonus;
    lastWasRecord = !adminBossTestMode && finalScore > best;
    if (!adminSandbox && !adminBossTestMode && finalScore > best) {
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
    if (!objectWidth || !objectHeight) return -Infinity;
    const left = x - objectWidth / 2;
    // Landing reach must cover the harmful torso width as well: otherwise a
    // boot at the edge can miss while the wider damage ellipse kills the run.
    const halfPlayerWidth = player ? player.width * .32 : 0;
    if (targetX + halfPlayerWidth < left || targetX - halfPlayerWidth > left + objectWidth) return -Infinity;
    if (!mask) return y + objectHeight / 2;
    const firstColumn = clamp(Math.floor((targetX - halfPlayerWidth - left) / objectWidth * mask.columns), 0, mask.columns - 1);
    const lastColumn = clamp(Math.floor((targetX + halfPlayerWidth - left) / objectWidth * mask.columns), 0, mask.columns - 1);
    let topRow = mask.rows;
    for (let column = firstColumn; column <= lastColumn; column += 1) {
      const columnTop = mask.topRows ? mask.topRows[column] : mask.rows;
      if (columnTop < topRow) topRow = columnTop;
    }
    return topRow === mask.rows ? -Infinity : y + objectHeight / 2 - topRow / mask.rows * objectHeight;
  }

  // Follow both objects through the physics step. A foot may cross a curved
  // silhouette before the final x coordinate reaches a lower part of its edge.
  function spriteLanding(sprite, x, y, w, h, oldX, oldY, previousFeet, currentFeet, previousX, mirror = 1) {
    if (player.vy >= 0 || currentFeet >= previousFeet) return null;
    if (Math.abs(player.x - previousX) > width / 2) previousX = player.x;
    const travel = Math.abs(player.x - previousX) + Math.abs(x - oldX)
      + Math.abs(currentFeet - previousFeet) + Math.abs(y - oldY);
    const steps = Math.max(1, Math.ceil(travel / 2));
    for (let i = 0; i <= steps; i += 1) {
      const t = i / steps, cx = oldX + (x - oldX) * t, cy = oldY + (y - oldY) * t;
      const fx = previousX + (player.x - previousX) * t;
      const top = spriteTopAtX(sprite, cx, cy, w, h, cx + (fx - cx) * mirror);
      const feet = previousFeet + (currentFeet - previousFeet) * t;
      if (Number.isFinite(top) && previousFeet - oldY >= top - cy - 3 && feet <= top + 2) {
        return top + y - cy;
      }
    }
    return null;
  }

  function protectBounce() {
    // Other collision passes still hold the pre-bounce trajectory this step.
    invulnerableTimer = Math.max(invulnerableTimer, .12);
  }

  function sweptHazardContact(hitbox, previousHazardY, previousX, previousY) {
    if (Math.abs(player.x - previousX) > width / 2) previousX = player.x;
    const dx = player.x - previousX;
    const relativeDy = player.y - previousY - (hitbox.y - previousHazardY);
    const steps = Math.max(1, Math.ceil(Math.max(Math.abs(dx), Math.abs(relativeDy)) / 4));
    for (let i = 0; i <= steps; i += 1) {
      const t = i / steps;
      if (spriteOverlapsEllipse(hitbox.sprite, hitbox.x,
        previousHazardY + (hitbox.y - previousHazardY) * t, hitbox.width, hitbox.height,
        previousX + dx * t, previousY + (player.y - previousY) * t,
        player.width * .29, player.height * .34)) return true;
    }
    return false;
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

  function landingPlatform(previousFeet, currentFeet, previousX, currentX) {
    let landing = null;
    let earliest = Infinity;
    const descent = previousFeet - currentFeet;
    if (descent <= 0) return null;
    // Wrapping around the screen is not a sweep through its centre.
    if (Math.abs(currentX - previousX) > width / 2) previousX = currentX;
    for (const platform of platforms) {
      if (platform.broken || platform.y < cameraY + 4) continue;
      if (platform.spaceService === spaceEncounter && spaceEncounter?.type === "pitstop") continue;
      const t = (previousFeet - platform.y) / descent;
      if (t < 0 || t > 1 || t >= earliest) continue;
      const feetX = previousX + (currentX - previousX) * t;
      const platformX = (platform.previousX ?? platform.x)
        + (platform.x - (platform.previousX ?? platform.x)) * t;
      if (Math.abs(feetX - platformX) > platform.hitboxWidth * .5 + player.width * .3) continue;
      landing = platform;
      earliest = t;
    }
    return landing;
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
    ctx.drawImage(rasterSprite(frame, rocketWidth, rocketHeight),
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
    if (!player || invulnerableTimer <= 0 || portalTransition) return;
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

  function updateSkyDetails(dt) {
    if (forgottenPaddock || cameraY < skyFade.end || cameraY >= spaceFade.start) {
      skyFlock = null;
      totoCloud = null;
      return;
    }
    totoCloudWait -= dt;
    if (!totoCloud && totoCloudWait <= 0 && art.totoCloud) {
      totoCloud = { age: 0, x: width * (.25 + Math.random() * .5), y: height * .24 };
      totoCloudWait = 30 + Math.random() * 15;
    }
    if (totoCloud) {
      totoCloud.age += dt;
      if (totoCloud.age > 10) totoCloud = null;
    }
    skyFlockWait -= dt;
    if (!skyFlock && skyFlockWait <= 0 && art.duckFrames) {
      const direction = Math.random() < .5 ? -1 : 1;
      skyFlock = { age: 0, x: direction > 0 ? -65 : width + 65,
        y: cameraY + height * .78, direction, birds: Array.from({ length: 5 }, () => ({ used: false })) };
      skyFlockWait = 20 + Math.random() * 10;
    }
    if (skyFlock) {
      skyFlock.age += dt;
      skyFlock.x += skyFlock.direction * 65 * dt;
      const tail = skyFlock.x - skyFlock.direction * 170;
      if ((skyFlock.direction > 0 ? tail > width + 65 : tail < -65)
        || skyFlock.y < cameraY - 100) skyFlock = null;
    }
  }

  function skyDuckPosition(index) {
    const flock = skyFlock;
    const rank = Math.ceil(index / 2);
    const catchup = index === 4 ? 35 * (1 - clamp((flock.age - 2) / 2, 0, 1)) : 0;
    return { x: flock.x - flock.direction * (rank * 49 + catchup),
      y: flock.y + (index % 2 ? rank * 24 : -rank * 24) };
  }

  function collideSkyDucks(previousFeet, currentFeet, dt, previousX) {
    if (!skyFlock || player.vy >= 0 || rocketTimer > 0) return;
    for (let i = 0; i < skyFlock.birds.length; i += 1) {
      const bird = skyFlock.birds[i];
      if (bird.used) continue;
      const pos = skyDuckPosition(i), top = pos.y + 7;
      if (previousFeet < top || currentFeet > top) continue;
      const t = (previousFeet - top) / Math.max(.001, previousFeet - currentFeet);
      const dx = Math.abs(player.x - previousX) > width / 2 ? 0 : player.x - previousX;
      const contactX = player.x - dx * (1 - t);
      const birdX = pos.x - skyFlock.direction * 65 * dt * (1 - t);
      if (Math.abs(contactX - birdX) > 18 + player.width * .22) continue;
      player.y = top + player.height / 2;
      player.vy = 820;
      bird.used = true;
      somersault = null;
      openingJump = false;
      break;
    }
  }

  function drawTotoCloud() {
    if (!totoCloud || !art.totoCloud || forgottenPaddock || portalTransition || cameraY >= spaceFade.start) return;
    const age = totoCloud.age;
    const alpha = Math.min(clamp(age / 2, 0, 1), clamp((10 - age) / 3, 0, 1)) * .48;
    const w = width * .53, h = spriteSize(art.totoCloud, w);
    const y = totoCloud.y + age * 3;
    ctx.save(); ctx.globalAlpha = alpha;
    ctx.drawImage(rasterSprite(art.totoCloud, w, h), totoCloud.x - w / 2 + age * 2, y, w, h);
    ctx.restore();
  }

  function drawSkyDucks() {
    if (!skyFlock || !art.duckFrames || forgottenPaddock || portalTransition || cameraY >= spaceFade.start) return;
    for (let i = 0; i < skyFlock.birds.length; i += 1) {
      const pos = skyDuckPosition(i), bird = skyFlock.birds[i];
      const pose = art.duckFrames[Math.floor(skyFlock.age * 9 + i) % 4];
      // All poses share the sheet's body anchor, not the cropped wing bounds.
      // This keeps the torso and landing surface still while wings flap.
      const scale = 46 / art.duckCellWidth;
      const w = pose.sw * scale, h = pose.sh * scale, y = worldToScreen(pos.y);
      if (pos.x < -55 || pos.x > width + 55 || y < -55 || y > height + 55) continue;
      ctx.save(); ctx.translate(pos.x, y);
      if (i === 4 && skyFlock.age > 2 && skyFlock.age < 4) {
        ctx.fillStyle = "#e9e6c4"; ctx.globalAlpha = .65;
        for (let n = 0; n < 3; n += 1) ctx.fillRect(-skyFlock.direction * (28 + n * 7), 0, 4, 2);
        ctx.globalAlpha = 1;
      }
      ctx.save(); ctx.scale(skyFlock.direction, 1);
      ctx.drawImage(rasterSprite(pose, w, h),
        (pose.sourceX - art.duckCellWidth * .5) * scale,
        (pose.sourceY - art.duckBodyY) * scale, w, h); ctx.restore();
      ctx.restore();
    }
  }

  function updateHawks(dt, previousFeet = player.y - player.height / 2 - player.vy * dt,
    currentFeet = player.y - player.height / 2, previousPlayerX = player.x - player.vx * dt) {
    if (forgottenPaddock) { hawks = []; return false; }
    const spawnHere = cameraY >= skyFade.end && cameraY < spaceFade.start;
    if (!spawnHere && !hawks.length) return false;
    if (!art.hawkFrames || !art.hawkFrames.length) return false;

    if (spawnHere) hawkSpawnWait -= dt;
    if (spawnHere && hawkSpawnWait <= 0) {
      const size = 82 * visualScale();
      const direction = Math.random() < .5 ? 1 : -1;
      const screenY = height * (.32 + Math.random() * .4);
      hawks.push({
        x: direction > 0 ? -size : width + size,
        previousX: direction > 0 ? -size : width + size,
        y: cameraY + height - screenY,
        direction,
        speed: 135 + Math.random() * 55,
        size,
      });
      hawkSpawnWait = 4 + Math.random() * 3.5;
    }

    let kept = 0;
    for (const hawk of hawks) {
      const previousX = hawk.x;
      hawk.previousX = previousX;
      hawk.x += hawk.direction * hawk.speed * dt;
      if (hawk.x < -hawk.size || hawk.x > width + hawk.size
        || hawk.y < cameraY - hawk.size || hawk.y > cameraY + height + hawk.size) continue;

      const frame = art.hawkFrames[0];
      const hawkHeight = spriteSize(frame, hawk.size);
      // Check the descending feet against the actual, mirrored silhouette
      // before testing harmful side contacts. Interpolate the moving bird too.
      const startX = Math.abs(player.x - previousPlayerX) > width / 2 ? player.x : previousPlayerX;
      let bounced = false;
      const top = spriteLanding(frame, hawk.x, hawk.y, hawk.size, hawkHeight,
        previousX, hawk.y, previousFeet, currentFeet, startX, hawk.direction);
      if (top !== null) {
        player.y = top + player.height / 2;
        player.vy = 810;
        protectBounce();
        openingJump = false;
        bounced = true;
      }
      if (bounced) { hawks[kept++] = hawk; continue; }
      const travel = Math.abs(hawk.x - previousX) + Math.abs(player.vx * dt) + Math.abs(player.vy * dt);
      const steps = Math.max(1, Math.ceil(travel / 9));
      let overlaps = false;
      for (let step = 0; step <= steps; step += 1) {
        const t = step / steps;
        const birdX = previousX + (hawk.x - previousX) * t;
        const playerX = startX + (player.x - startX) * t;
        if (spriteOverlapsEllipse(frame,
          birdX,
          hawk.y,
          hawk.size,
          hawkHeight,
          birdX + (playerX - birdX) * hawk.direction,
          player.y - player.vy * dt * (1 - t),
          player.width * .29,
          player.height * .34)) {
          overlaps = true;
          break;
        }
      }
      if (overlaps && invulnerableTimer <= 0) {
        endGame();
        return true;
      }
      hawks[kept++] = hawk;
    }
    hawks.length = kept;
    return false;
  }

  function drawHawks() {
    if (!art.hawkFrames || !art.hawkFrames.length) return;
    for (const hawk of hawks) {
      const frame = art.hawkFrames[0];
      const drawHeight = spriteSize(frame, hawk.size);
      const screenY = worldToScreen(hawk.y);
      ctx.save();
      ctx.translate(hawk.x, screenY);
      if (hawk.direction < 0) ctx.scale(-1, 1);
      ctx.drawImage(rasterSprite(frame, hawk.size, drawHeight),
        -hawk.size / 2, -drawHeight / 2, hawk.size, drawHeight);
      ctx.restore();
    }
  }

  function setBossWarning(boss) {
    boss.phase = "warning";
    boss.timer = 0;
    boss.round += 1;
    // Keep the safe lane close enough to reach during the warning on touch.
    const lane = clamp(Math.floor(player.x / (width / 4)), 0, 3);
    boss.safeLane = clamp(lane + (Math.random() < .5 ? -1 : 1), 0, 3);
    const targetX = (boss.safeLane + .5) * width / 4;
    const supportY = player.y - player.height / 2 - 18;
    // A bridge immediately below the feet catches even an already falling hero.
    // From it, ordinary jumps can reach the stationary refuge ladder.
    const bridgeX = (player.x + targetX) / 2;
    let bridge = platforms.find(p => p.bossBridge && !p.broken && p.y <= supportY && p.y >= supportY - 65
      && Math.abs(player.x - p.x) <= p.hitboxWidth / 2 && Math.abs(targetX - p.x) <= p.hitboxWidth / 2);
    if (!bridge) {
      bridge = addPlatform(supportY, bridgeX, "normal");
      bridge.bossBridge = true;
      bridge.width = bridge.hitboxWidth = bridge.spriteWidth = Math.abs(player.x - targetX) + 80;
    }
    boss.safeTopY = Math.floor(bridge.y / 150) * 150;
    extendBossRefuge(boss);
  }

  function extendBossRefuge(boss) {
    if (boss.phase !== "warning" && boss.phase !== "volley") return;
    const x = (boss.safeLane + .5) * width / 4;
    while (boss.safeTopY < cameraY + visibleWorldHeight + 150) {
      boss.safeTopY += 150;
      // Fixed world rows survive repeated warnings without stacking ladders.
      // Reuse ordinary footholds too when they already cover the refuge lane.
      if (platforms.some(p => !p.broken && p.kind !== "break" && p.kind !== "moving"
        && Math.abs(p.y - boss.safeTopY) < 25
        && Math.abs(p.x - x) < p.hitboxWidth / 2 - 8)) continue;
      const platform = addPlatform(boss.safeTopY, x, "normal");
      platform.width = platform.hitboxWidth = platform.spriteWidth = Math.min(100, width / 4 - 12);
      platform.bossSafe = true;
    }
  }

  function openBossTarget(boss) {
    boss.phase = "descending";
    boss.timer = 0;
    bossShots = [];
    // An ordinary 720-speed jump reaches ~209 world units. Put a stable
    // launch platform below the player and the target only 115 units above it.
    const supportY = player.y - player.height / 2 - 25;
    const supportX = clamp(player.x, 55, width - 55);
    boss.support = addPlatform(supportY, supportX, "normal");
    platforms.sort((a, b) => a.y - b.y);
    boss.targetX = clamp(supportX + (boss.round % 2 ? 30 : -30), 55, width - 55);
    boss.landingY = supportY + 115;
  }

  function collideWithSpaceBoss(previousFeet, currentFeet, previousX = player.x) {
    const boss = spaceBoss;
    if (!boss || boss.phase !== "open" || rocketTimer > 0 || player.vy >= 0) return false;
    if (!movingLanding(previousFeet, currentFeet, boss.landingY, boss.landingY,
      previousX, boss.x, boss.x, 78)) return false;
    player.y = boss.landingY + player.height / 2;
    player.vy = 720;
    openingJump = false;
    somersault = null;
    invulnerableTimer = Math.max(invulnerableTimer, 1.2);
    boss.hp -= 1;
    boss.timer = 0;
    boss.phase = boss.hp === 0 ? "defeated" : "hit";
    bossShots = [];
    effects.push({ index: 10, x: boss.x, y: boss.landingY, age: 0, duration: .5, size: 70 });
    if (boss.hp === 0) {
      bossBonus += 300;
      bossVictoryUntil = elapsed + 3;
      updateHud();
    }
    return true;
  }

  function resetSpaceEncounters(clearBoots = true) {
    if (spaceEncounter?.platform) delete spaceEncounter.platform.spaceService;
    spaceEncounter = null;
    spacePitHold = null;
    spaceEncounterWait = 7;
    spaceEncounterIndex = -1;
    if (clearBoots) softBootJumps = 0;
  }

  function inSpaceChapter() {
    return !forgottenPaddock && !antarctica && !portalTransition && cameraY >= spaceFade.end;
  }

  function spawnSpaceEncounter(kind = null) {
    if (!inSpaceChapter() || spaceBoss || spaceEncounter || spacePitHold) return false;
    const kinds = ["carbon", "satellite", "pitstop", "alonso"];
    spaceEncounterIndex = (spaceEncounterIndex + 1) % kinds.length;
    const type = kind || kinds[spaceEncounterIndex];
    const event = { type, age: 0, x: width * .5, y: player.y + 160, used: false, debris: [], ghosts: [] };
    if (type === "carbon") {
      const safeLane = clamp(Math.floor(player.x / width * 4), 0, 3);
      for (let lane = 0; lane < 4; lane += 1) {
        if (lane === safeLane) continue;
        const index = event.debris.length;
        event.debris.push({ x: (lane + .5) * width / 4, y: cameraY + height + 50 + index * 35,
          index: index < 2 ? index : 2 + Math.floor(Math.random() * 2), vy: -(72 + index * 11), dead: false });
      }
    } else if (type === "satellite") {
      event.x = width * (player.x < width / 2 ? .78 : .22);
      event.y = cameraY + height * .76;
      for (let i = 0; i < 3; i += 1) event.ghosts.push({ x: width * (i % 2 ? .7 : .3), y: player.y + 100 + i * 125 });
    } else if (type === "pitstop") {
      const candidates = platforms.filter((p) => !p.broken && p.y > player.y + 40 && p.y < player.y + 230);
      const target = candidates.find((p) => p.kind === "normal") || candidates[0];
      event.x = clamp(target?.x || player.x, 85, width - 85);
      event.y = target?.y || player.y + 150;
      // The service deck temporarily takes over this real landing surface.
      // Its old platform is restored if Toto interrupts the event.
      event.platform = target || null;
      if (target) target.spaceService = event;
    } else {
      event.direction = player.x < width / 2 ? -1 : 1;
      event.x = event.direction > 0 ? -85 : width + 85;
      event.y = player.y + 210;
    }
    spaceEncounter = event;
    return true;
  }

  function clearSpaceEncounter() {
    if (spaceEncounter?.platform) delete spaceEncounter.platform.spaceService;
    spaceEncounter = null;
    spacePitHold = null;
    spaceEncounterWait = 8 + Math.random() * 5;
  }

  function spacePitDeck(event) {
    return { x: event.platform?.x ?? event.x, y: event.platform?.y ?? event.y, width: 150 };
  }

  function updateSpaceEvents(dt) {
    if (!inSpaceChapter()) {
      if (spaceEncounter || spacePitHold) clearSpaceEncounter();
      return false;
    }
    if (!spaceEncounter) {
      spaceEncounterWait -= dt;
      if (spaceEncounterWait <= 0) spawnSpaceEncounter();
    }
    const event = spaceEncounter;
    if (!event) return false;
    event.age += dt;
    if (event.type === "carbon") {
      for (const item of event.debris) item.y += item.vy * dt;
    }
    if (event.type === "alonso") {
      event.x += event.direction * 48 * dt;
      if (event.x > width + 100 || event.x < -100) { clearSpaceEncounter(); return false; }
    }
    if (spacePitHold) {
      const deck = spacePitDeck(event);
      spacePitHold.age += dt;
      player.x = deck.x; player.y = deck.y + player.height / 2;
      player.vx = player.vy = 0;
      invulnerableTimer = Math.max(invulnerableTimer, 1.1);
      if (spacePitHold.age >= .75) {
        spacePitHold = null;
        softBootJumps = 2; // The service launch is the first of three soft jumps.
        player.vy = 930;
        openingJump = false;
      }
      return true;
    }
    if (event.type === "carbon") {
      if (event.debris.every(item => item.dead || item.y < cameraY - 100)) clearSpaceEncounter();
    } else if (event.age > 11 || event.y < cameraY - 180) clearSpaceEncounter();
    return false;
  }

  function collideWithSpaceEvents(previousFeet, currentFeet, dt, previousX = player.x) {
    const event = spaceEncounter;
    if (!event || !inSpaceChapter()) return;
    if (event.type === "pitstop" && rocketTimer <= 0) {
      const deck = spacePitDeck(event);
      if (deck.y > cameraY + 4 && player.vy < 0 && crossedLandingSurface(previousFeet, currentFeet,
        deck.y, deck.y, player.x, deck.x, deck.width * .8, player.width * .44)) {
        player.y = deck.y + player.height / 2;
        if (!event.used) {
          event.used = true; spacePitHold = { age: 0 };
          player.x = deck.x; player.vx = player.vy = 0;
          invulnerableTimer = Math.max(invulnerableTimer, 1.1);
        } else {
          player.vy = softBootJumps > 0 ? 930 : 720;
          if (softBootJumps > 0) softBootJumps -= 1;
        }
        somersault = null;
      }
    } else if (event.type === "alonso") {
      const frame = art.spaceAlonso[0], drawWidth = 150, drawHeight = spriteSize(frame, drawWidth);
      const contactX = event.x + (player.x - event.x) * event.direction;
      const top = spriteTopAtX(frame, event.x, event.y, drawWidth, drawHeight, contactX);
      if (player.vy < 0 && crossedLandingSurface(previousFeet, currentFeet, top, top,
        player.x, event.x, 90, player.width * .44)) {
        player.y = top + player.height / 2;
        player.vy = event.used ? 720 : 1080;
        event.used = true;
        invulnerableTimer = Math.max(invulnerableTimer, .65);
        openingJump = false; somersault = null;
      }
    } else if (event.type === "carbon") {
      for (const item of event.debris) {
        if (item.dead || item.y < cameraY - 80) continue;
        const sprite = art.spaceCarbon[item.index], w = item.index < 2 ? 72 : 26, h = spriteSize(sprite, w);
        if (item.index < 2 && player.vy < 0) {
          const top = spriteLanding(sprite, item.x, item.y, w, h, item.x, item.y - item.vy * dt,
            previousFeet, currentFeet, previousX);
          if (top !== null) {
            player.y = top + player.height / 2; player.vy = 850;
            protectBounce();
            openingJump = false; somersault = null; item.dead = true;
            continue;
          }
        }
        if (invulnerableTimer > 0) continue;
        const oldPlayerY = previousFeet + player.height / 2;
        const steps = Math.max(1, Math.ceil((Math.abs(player.vy) + Math.abs(item.vy)) * dt / 8));
        for (let step = 0; step <= steps; step += 1) {
          const t = step / steps;
          if (spriteOverlapsEllipse(sprite, item.x, item.y - item.vy * dt * (1 - t), w, h,
            player.x, oldPlayerY + (player.y - oldPlayerY) * t, player.width * .27, player.height * .33)) {
            endGame(); return;
          }
        }
      }
    }
  }

  function drawSpaceEvents() {
    const event = spaceEncounter;
    if (!event || !inSpaceChapter()) return;
    let label = "", labelX = event.x, labelY = worldToScreen(event.y) - 55;
    if (event.type === "carbon") {
      // Draw continuously from spawn above the viewport: hiding the sprites
      // during a warning let the rising camera reveal them mid-screen at once.
      for (const item of event.debris) {
        if (!item.dead) drawFrame(art.spaceCarbon[item.index], item.x, item.y, item.index < 2 ? 72 : 26);
      }
    } else if (event.type === "satellite") {
      const pose = event.age < 1.5 ? 0 : event.age < 3.5 ? 1 : event.age < 8 ? 2 : 3;
      drawFrame(art.spaceSatellite[pose], event.x, event.y, 112);
      label = event.age < 3.5 ? (event.x > width / 2 ? "← WE ARE CHECKING" : "WE ARE CHECKING →") : "STAY OUT!";
      if (event.age >= 1.5 && event.age < 8) {
        for (const ghost of event.ghosts) {
          ctx.save(); ctx.globalAlpha = .24 + Math.sin(elapsed * (event.age > 3.5 ? 21 : 9)) * .12;
          drawSprite(0, ghost.x, ghost.y, 72, "platform");
          const y = worldToScreen(ghost.y);
          ctx.strokeStyle = "#9be8ff"; ctx.lineWidth = 1; ctx.setLineDash([3, 4]);
          ctx.beginPath(); ctx.moveTo(ghost.x - 31, y + 2); ctx.lineTo(ghost.x + 31, y + 2); ctx.stroke();
          ctx.font = "9px monospace"; ctx.textAlign = "center"; ctx.globalAlpha = .65; ctx.fillStyle = "#9be8ff";
          ctx.fillText("HOLOGRAM", ghost.x, y + 22); ctx.restore();
        }
      }
    } else if (event.type === "pitstop") {
      const deck = spacePitDeck(event);
      const pose = spacePitHold ? (spacePitHold.age < .25 ? 1 : 2) : event.used ? 3 : 0;
      const sprite = art.spacePitstop[pose], h = spriteSize(sprite, deck.width);
      // Original sheet deck is at row 356 in every frame; keep that exact
      // plane fixed while mechanics raise/lower their tools around the hero.
      const deckOffset = (356 - sprite.sourceY) / sprite.sh * h;
      ctx.drawImage(rasterSprite(sprite, deck.width, h), deck.x - deck.width / 2, worldToScreen(deck.y) - deckOffset, deck.width, h);
      labelX = deck.x; labelY = worldToScreen(deck.y) - 61;
      label = spacePitHold ? "МЕНЯЕМ НА SOFT…" : event.used ? "SOFT · 3 ПРЫЖКА" : "ЛУННЫЙ ПИТ-СТОП";
    } else {
      const pose = Math.floor(event.age * 6) % 4;
      const sprite = art.spaceAlonso[pose], h = spriteSize(sprite, 150);
      ctx.save(); ctx.translate(event.x, worldToScreen(event.y)); ctx.scale(event.direction, 1);
      ctx.drawImage(rasterSprite(sprite, 150, h), -75, -h / 2, 150, h); ctx.restore();
      label = "GP2 ENGINE!";
    }
    if (label) {
      ctx.save(); ctx.font = "bold 10px monospace"; ctx.textAlign = "center";
      ctx.strokeStyle = "#10192c"; ctx.lineWidth = 3; ctx.fillStyle = "#e9d5ac";
      const x = clamp(labelX, 94, width - 94), y = Math.max(95, labelY);
      ctx.strokeText(label, x, y); ctx.fillText(label, x, y); ctx.restore();
    }
  }

  async function startSpaceEventTest(kind) {
    if (!artReady || (mode === "running" && !adminBossTestMode && !adminSandbox)) return;
    if (!await preparePreview(["sky", "space"])) return;
    if (mode === "running" && !adminBossTestMode && !adminSandbox) return;
    startGame(true, { forceRestart: true, adminTest: true });
    peakY = player.y = startY + 2000 * 11;
    player.x = width / 2; player.vy = 720;
    cameraY = player.y - cameraTrackingOffset(); openingJump = false;
    platforms = []; enemies = []; hazards = []; powerups = []; marshals = [];
    let y = player.y - player.height / 2 - 8, x = player.x;
    addPlatform(y, x, "normal");
    while (y < cameraY + height + 320) { const gap = platformGap(); y += gap; x = choosePlatformX(x, gap); addPlatform(y, x, "normal"); }
    worldTop = y;
    spawnSpaceEncounter(kind);
    if (bossTestStatus) bossTestStatus.textContent = "Тест космического события · без сохранения результата";
    updateHud(); draw();
  }

  function updateSpaceBoss(dt) {
    if (forgottenPaddock || cameraY < spaceFade.end || !art.spaceBoss || !art.bossWheel) return;
    if (!spaceBoss) {
      const score = runScore();
      const firstEncounter = !guaranteedSpaceBossSpawned && score >= 3500;
      if (guaranteedSpaceBossSpawned && score > 4500) bossWait -= dt;
      if (firstEncounter || (guaranteedSpaceBossSpawned && score > 4500 && bossWait <= 0)) {
        guaranteedSpaceBossSpawned = true;
        spaceBoss = { age: 0, timer: 0, phase: "arrival", hp: 3, round: 0,
          x: width / 2, screenY: spaceBossScreenY(), safeLane: 1, landingY: 0 };
        // Existing world objects and events finish naturally during the fight.
        bossShots = [];
      }
    }
    if (spaceBoss) {
      const boss = spaceBoss;
      extendBossRefuge(boss);
      boss.age += dt;
      boss.timer += dt;
      if (boss.phase === "descending") {
        const targetY = worldToScreen(boss.landingY) + spriteSize(art.spaceBoss, 100) / 2;
        boss.x += (boss.targetX - boss.x) * Math.min(1, dt * 6);
        boss.screenY += (targetY - boss.screenY) * Math.min(1, dt * 6);
        if (boss.timer >= .65) {
          boss.x = boss.targetX;
          boss.screenY = targetY;
          boss.phase = "open";
          boss.timer = 0;
        }
      } else if (boss.phase === "open" || boss.phase === "hit" || boss.phase === "defeated") {
        boss.screenY = worldToScreen(boss.landingY) + spriteSize(art.spaceBoss, 100) / 2;
      } else {
        boss.screenY += (spaceBossScreenY() - boss.screenY) * Math.min(1, dt * 4);
        boss.x += (width * (.5 + Math.sin(boss.age * .7) * .25) - boss.x) * Math.min(1, dt * 2);
      }
      if (boss.phase === "arrival" && boss.timer >= 1.2) setBossWarning(boss);
      else if (boss.phase === "warning" && boss.timer >= 1.1) {
        boss.phase = "volley";
        boss.timer = 0;
        for (let lane = 0; lane < 4; lane += 1) {
          if (lane === boss.safeLane) continue;
          const screenY = spaceBossScreenY() - 5;
          bossShots.push({ x: (lane + .5) * width / 4, screenY,
            y: cameraY + height - screenY, speed: 175 });
        }
      } else if (boss.phase === "volley" && boss.timer >= 2.6) openBossTarget(boss);
      else if ((boss.phase === "open" && boss.timer >= 4.2) || (boss.phase === "hit" && boss.timer >= .65)) {
        if (boss.round < 3) setBossWarning(boss);
        else { boss.phase = "leaving"; boss.timer = 0; bossShots = []; }
      }
      if ((boss.phase === "leaving" || boss.phase === "defeated") && boss.timer >= 1) {
        spaceBoss = null;
        bossShots = [];
        bossWait = 120 + Math.random() * 60;
      }
    }
    const shotWidth = 36;
    const shotHeight = spriteSize(art.bossWheel, shotWidth);
    let kept = 0;
    for (const shot of bossShots) {
      const previousY = shot.y;
      shot.screenY += shot.speed * dt;
      shot.y = cameraY + height - shot.screenY;
      const steps = Math.max(1, Math.ceil((Math.abs(player.vy) * dt + Math.abs(shot.y - previousY)) / 10));
      let hit = false;
      for (let step = 0; step <= steps; step += 1) {
        const t = step / steps;
        if (spriteOverlapsEllipse(art.bossWheel, shot.x, previousY + (shot.y - previousY) * t,
          shotWidth, shotHeight, player.x - player.vx * dt * (1 - t),
          player.y - player.vy * dt * (1 - t), player.width * .29, player.height * .34)) {
          hit = true;
          break;
        }
      }
      if (hit && invulnerableTimer <= 0) { endGame(); return; }
      if (!hit && shot.screenY < height + 60) bossShots[kept++] = shot;
    }
    bossShots.length = kept;
  }

  function spaceBossScreenY() {
    return height - visibleWorldHeight + Math.min(170, visibleWorldHeight * .28);
  }

  function drawSpaceBoss() {
    for (const shot of bossShots) drawFrame(art.bossWheel, shot.x, shot.y, 36);
    if (!spaceBoss || !art.spaceBoss) return;
    const boss = spaceBoss;
    const bossWidth = 100;
    const bossHeight = spriteSize(art.spaceBoss, bossWidth);
    ctx.save();
    if (boss.phase === "warning") {
      for (let lane = 0; lane < 4; lane += 1) {
        const safe = lane === boss.safeLane;
        ctx.fillStyle = safe ? "rgba(129,209,168,.1)" : "rgba(222,110,99,.13)";
        const top = spaceBossScreenY() - 5;
        ctx.fillRect(lane * width / 4 + 4, top, width / 4 - 8, height - top);
        ctx.fillStyle = safe ? "#a5e6c5" : "#ffc28c";
        ctx.font = "bold 13px monospace";
        ctx.textAlign = "center";
        ctx.fillText(safe ? "↓" : "!", (lane + .5) * width / 4, top + 25);
      }
    }
    const leaving = boss.phase === "leaving" || boss.phase === "defeated";
    ctx.globalAlpha = leaving ? Math.max(0, 1 - boss.timer) : Math.min(1, boss.age / .6);
    const shake = boss.phase === "hit" ? Math.sin(boss.timer * 55) * 5 : 0;
    ctx.drawImage(rasterSprite(art.spaceBoss, bossWidth, bossHeight),
      boss.x - bossWidth / 2 + shake, boss.screenY - bossHeight / 2 - (leaving ? boss.timer * 70 : 0), bossWidth, bossHeight);
    ctx.globalAlpha = 1;
    if (boss.phase === "open") {
      const targetY = worldToScreen(boss.landingY);
      ctx.strokeStyle = "#b7f0ce";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(boss.x - 39, targetY);
      ctx.lineTo(boss.x + 39, targetY);
      ctx.stroke();
      ctx.font = "bold 11px monospace";
      ctx.fillStyle = "#d0ffe3";
      ctx.textAlign = "center";
      ctx.fillText("↓ ПРЫГНИ СВЕРХУ", boss.x, targetY - 12);
    }
    const panelWidth = Math.min(270, width - 30);
    ctx.fillStyle = "rgba(17,21,35,.88)";
    ctx.fillRect((width - panelWidth) / 2, 88, panelWidth, 54);
    ctx.textAlign = "center";
    ctx.font = "bold 12px monospace";
    ctx.fillStyle = "#f8e9cf";
    const label = boss.phase === "defeated" ? "ТОТО ПОБЕЖДЁН · +300"
      : boss.phase === "leaving" ? "ТОТО УЛЕТАЕТ"
        : boss.phase === "open" ? "ТАРЕЛКА УЯЗВИМА"
          : boss.phase === "descending" ? "ТАРЕЛКА ОПУСКАЕТСЯ" : "ТОТО ВОЛЬФ · БОСС";
    ctx.fillText(label, width / 2, 105);
    for (let i = 0; i < 3; i += 1) {
      ctx.fillStyle = i < boss.hp ? "#e6b76e" : "#424854";
      ctx.fillRect(width / 2 - 40 + i * 28, 115, 24, 6);
    }
    ctx.font = "10px monospace";
    ctx.fillStyle = "#c4cddd";
    ctx.fillText(boss.phase === "open" ? "Прыгни с подсвеченной платформы" : "Залп " + Math.max(1, boss.round) + "/3 · уклоняйся", width / 2, 135);
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

  function movingLanding(previousFeet, currentFeet, previousTop, currentTop, previousX, oldX, x, targetWidth) {
    if (Math.abs(player.x - previousX) > width / 2) previousX = player.x;
    const before = previousFeet - previousTop, after = currentFeet - currentTop;
    if (before < -3 || after > 2 || after >= before) return false;
    const t = clamp(before / (before - after), 0, 1);
    return Math.abs(previousX + (player.x - previousX) * t - oldX - (x - oldX) * t)
      <= targetWidth / 2 + player.width * .32;
  }

  function nextEnemyVariant() {
    const count = art.enemyVariants ? art.enemyVariants.length : 1;
    if (count < 2) return 0;
    const choice = lastEnemyVariant < 0 ? Math.floor(Math.random() * count)
      : (lastEnemyVariant + 1 + Math.floor(Math.random() * (count - 1))) % count;
    lastEnemyVariant = choice;
    return choice;
  }

  function enemyFrame(enemy) {
    if (enemy.type === "piranha") return art.piranhaFrames[Math.floor(elapsed * 10 + enemy.phase) % 4];
    return (art.enemyVariants && art.enemyVariants[enemy.variant]) || sprites[4];
  }

  function piranhaGeometry(enemy, time = elapsed) {
    return { x: enemy.x, y: enemy.y + Math.sin(time * 3 + enemy.phase) * 6,
      rx: 19, ry: 14, width: 74 };
  }

  function drawPiranha(enemy) {
    const body = piranhaGeometry(enemy), frame = enemyFrame(enemy);
    const h = spriteSize(frame, body.width), y = worldToScreen(body.y);
    if (y + h / 2 < 0 || y - h / 2 > height) return;
    ctx.save(); ctx.translate(body.x, y);
    ctx.scale(Math.cos(elapsed * .85 + enemy.phase) > 0 ? -1 : 1, 1);
    ctx.drawImage(rasterSprite(frame, body.width, h), -body.width / 2, -h / 2, body.width, h);
    ctx.restore();
  }

  function collideWithPiranha(enemy, previousFeet, currentFeet, dt, previousX = player.x) {
    const body = piranhaGeometry(enemy), previous = piranhaGeometry(enemy, elapsed - dt);
    const horizontal = Math.abs(player.x - body.x);
    const top = body.y + body.ry;
    const crossedTop = movingLanding(previousFeet, currentFeet, previous.y + previous.ry, top,
      previousX, enemy.previousX ?? body.x, body.x, body.rx * 2);
    if (player.vy < 0 && crossedTop) {
      enemy.dead = true;
      frags += 1;
      player.y = top + player.height / 2;
      player.vy = 810;
      protectBounce();
      somersault = null; openingJump = false;
      effects.push({ index: 10, x: body.x, y: top, age: 0, duration: .32, size: 42 });
      return true;
    }
    // Only the fish's body is solid. Wing motion never expands the hitbox.
    const dx = horizontal / (body.rx + player.width * .29);
    const dy = (player.y - body.y) / (body.ry + player.height * .34);
    if (invulnerableTimer <= 0 && dx * dx + dy * dy < 1) return "hit";
    return false;
  }

  function updateBabyKimi(dt) {
    kimiBoost = Math.max(0, kimiBoost - dt);
    if (!forgottenPaddock || antarctica || summit || !art.babyKimi) return false;
    if (!babyKimi) {
      kimiWait -= dt;
      if (kimiWait <= 0 && rocketTimer <= 0 && kimiBoost <= 0) {
        babyKimi = { x: clamp(player.x, 70, width - 70), y: cameraY + height * .72,
          age: 0, state: "waiting", hold: 0 };
      }
      return false;
    }
    const kimi = babyKimi;
    kimi.age += dt;
    if (kimi.state === "holding") {
      kimi.hold += dt;
      const reach = clamp(kimi.hold / .22, 0, 1);
      const shaking = kimi.hold > .22 && kimi.hold < .95;
      const shake = shaking ? Math.sin((kimi.hold - .22) * Math.PI * 12) : 0;
      player.x = kimi.grabX + (kimi.x + 28 - kimi.grabX) * reach + shake * 9;
      player.y = kimi.grabY + (kimi.y + 12 - kimi.grabY) * reach + shake * 5
        + Math.max(0, kimi.hold - .95) * 65;
      player.vx = 0;
      player.vy = 0;
      invulnerableTimer = Math.max(invulnerableTimer, 5);
      if (kimi.hold >= 1.15) {
        kimi.state = "launched";
        kimi.leaveAt = kimi.age + .65;
        kimiBoost = 2.3;
        player.vy = 1400;
        invulnerableTimer = 4.3;
      }
      return true;
    }
    if (kimi.state === "waiting" && rocketTimer <= 0 && kimiBoost <= 0
      && Math.abs(player.x - kimi.x) < 48 && Math.abs(player.y - kimi.y) < 58) {
      kimi.state = "holding";
      kimi.grabX = player.x;
      kimi.grabY = player.y;
      invulnerableTimer = Math.max(invulnerableTimer, 5);
      return true;
    }
    if (kimi.age > 12 || kimi.y < cameraY - 90 || (kimi.leaveAt && kimi.age >= kimi.leaveAt)) {
      babyKimi = null;
      kimiWait = 35 + Math.random() * 20;
    }
    return false;
  }

  function drawBabyKimi() {
    if (!babyKimi || !art.babyKimi) return;
    const kimi = babyKimi;
    const bob = kimi.state === "waiting" ? Math.sin(elapsed * 2.5) * 4 : 0;
    const size = kimi.state === "holding" ? 83 : kimi.state === "launched" ? 92 : 88;
    const drawWidth = size * art.babyKimi.sw / art.babyKimi.sh;
    ctx.save();
    ctx.translate(kimi.x, worldToScreen(kimi.y + bob));
    ctx.rotate(kimi.state === "holding" ? Math.sin(kimi.hold * Math.PI * 12) * .045
      : kimi.state === "launched" ? -.12 : Math.sin(elapsed * 1.5) * .025);
    ctx.drawImage(rasterSprite(art.babyKimi, drawWidth, size), -drawWidth / 2, -size / 2, drawWidth, size);
    ctx.restore();
    const y = worldToScreen(kimi.y);
    if (y > 0 && y < height) {
      ctx.save();
      ctx.font = "bold 10px system-ui";
      ctx.textAlign = "center";
      ctx.fillStyle = "#ffe4a0";
      ctx.fillText(kimi.state === "holding" ? "ПОЙМАЛ!" : "BABY KIMI ↑", kimi.x, y - 52);
      ctx.restore();
    }
  }

  function collideWithEnemy(previousFeet, currentFeet, dt, previousX = player.x) {
    let harmfulContact = false;
    for (const enemy of enemies) {
      if (enemy.dead) continue;
      if (enemy.type === "piranha") {
        const contact = collideWithPiranha(enemy, previousFeet, currentFeet, dt, previousX);
        if (contact === true) return true;
        if (contact === "hit") harmfulContact = true;
        continue;
      }
      const targetEnemyWidth = enemyWidth();
      const frame = enemyFrame(enemy);
      const enemyHeight = spriteSize(frame, targetEnemyWidth);
      const enemyY = enemy.y + Math.sin(elapsed * 4 + enemy.phase) * 4;
      const horizontalReach = targetEnemyWidth / 2 + player.width * .31 + Math.abs(player.x - previousX) + Math.abs(enemy.x - (enemy.previousX ?? enemy.x));
      const verticalReach = enemyHeight / 2 + player.height / 2 + Math.abs(player.vy) * dt + 4;
      if (Math.abs(player.x - enemy.x) > horizontalReach || Math.abs(player.y - enemyY) > verticalReach) continue;

      let enemyTop = enemyY + enemyHeight / 2;
      let crossedTop = false;
      if (player.vy < 0) {
        const previousEnemyY = enemy.y + Math.sin((elapsed - dt) * 4 + enemy.phase) * 4;
        const landing = spriteLanding(frame, enemy.x, enemyY, targetEnemyWidth, enemyHeight,
          enemy.previousX ?? enemy.x, previousEnemyY, previousFeet, currentFeet, previousX);
        crossedTop = landing !== null;
        if (crossedTop) enemyTop = landing;
      }
      const targetRx = player.width * .31;
      const targetRy = player.height * .37;
      const overlaps = spriteOverlapsEllipse(frame, enemy.x, enemyY, targetEnemyWidth, enemyHeight,
        player.x, player.y, targetRx, targetRy);
      if (player.vy < 0 && crossedTop) {
        enemy.dead = true;
        frags += 1;
        player.y = enemyTop + player.height / 2;
        player.vy = 810;
        protectBounce();
        somersault = null;
        openingJump = false;
        effects.push({ index: 7, x: enemy.x, y: enemyTop, age: 0, duration: .42, size: 42 * visualScale() });
        effects.push({ index: 10, x: enemy.x, y: enemyTop, age: 0, duration: .42, size: 56 * visualScale() });
        effects.push({ index: 10, x: enemy.x, y: enemyTop, age: 0, duration: .28, size: 42 * visualScale() });
        return true;
      }
      if (overlaps && invulnerableTimer <= 0) {
        harmfulContact = true;
      }
    }
    // Array/spawn order must not turn a valid stomp into an adjacent side hit.
    if (harmfulContact && invulnerableTimer <= 0) { endGame(); return true; }
    return false;
  }

  function cameraTrackingOffset() {
    return logicalViewportWidth === 390 ? visibleWorldHeight * .38 : height * .42;
  }

  function followPlayerCamera(dt) {
    const target = Math.max(cameraY, player.y - cameraTrackingOffset());
    cameraY += (target - cameraY) * (1 - Math.exp(-(logicalViewportWidth === 390 ? 12 : 8) * dt));
  }

  function update(dt) {
    if (!streamWorldAssets()) return;
    elapsed += dt;
    if (forgottenPaddock && !antarctica && !summit && !antarcticaScene && !portalTransition && runScore() >= 8000) beginAntarcticaScene();
    if (antarcticaScene) {
      antarcticaScene.age += dt;
      if (antarcticaScene.age >= controlSceneDuration) enterAntarctica();
      return;
    }
    if (antarcticaArrival) {
      antarcticaArrival.age += dt;
      if (antarcticaArrival.age >= caveSceneDuration) finishAntarcticaArrival();
      return;
    }
    if (antarctica && winterMemoryStartedAt === null && runScore() >= antarcticaEntryScore + 100) winterMemoryStartedAt = elapsed;
    if (somersault) {
      somersault.age += dt;
      if (somersault.age >= .54) somersault = null;
    }
    if (!forgottenPaddock && !portalTransition && runScore() >= 5000) beginPortal();
    if (updatePortal(dt)) return;
    if (forgottenPaddock && !antarctica && elapsed < arrivalUntil - 3.4) return;
    invulnerableTimer = Math.max(0, invulnerableTimer - dt);
    rocketTimer = Math.max(0, rocketTimer - dt);
    if (antarctica && !sidBossCleared && !sidBoss && runScore() >= 10000) beginSidBoss();
    if (updateSidBoss(dt)) return;
    if (updateSpaceEvents(dt)) { somersault = null; return; }
    if (updateBabyKimi(dt)) { somersault = null; openingJump = false; return; }
    updateSkyDetails(dt);
    const direction = Number(held.right) - Number(held.left);
    const previousPlayerX = player.x;
    const targetVx = direction * Math.min(440, width * .62) * 1.2 + (winterWind > 0 ? winterWindDirection * 100 : 0);
    const traction = winterSlide > 0 ? (direction ? 8 : 1.8) : 10;
    player.vx += (targetVx - player.vx) * Math.min(1, traction * dt);
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
    if (kimiBoost > 0) player.vy = 1400;
    player.y += player.vy * dt;
    if (sidBoss) {
      const arenaH = sidArenaHeight();
      const ceiling = cameraY + arenaH - Math.min(72, arenaH * .18) - player.height / 2;
      if (player.y > ceiling) { player.y = ceiling; player.vy = Math.min(0, player.vy); }
    }
    const currentFeet = player.y - player.height / 2;
    if (!sidBoss) peakY = Math.max(peakY, player.y);

    for (const platform of platforms) {
      platform.previousX = platform.x;
      if (platform.kind === "moving" && !platform.broken) {
        platform.x = Math.max(platform.width * .55, Math.min(width - platform.width * .55,
          platform.originX + Math.sin(elapsed * 1.65 + platform.phase) * platform.range));
      }
    }

    for (const enemy of enemies) {
      enemy.previousX = enemy.x;
      const fish = enemy.type === "piranha";
      enemy.x = Math.max(38, Math.min(width - 38,
        enemy.baseX + Math.sin(elapsed * (fish ? .85 : 1.25) + enemy.phase) * Math.min(fish ? 90 : 54, width * (fish ? .21 : .14))));
    }

    updateWinterEncounter(dt, previousFeet, currentFeet, previousPlayerX);
    if (mode !== "running") return;
    updateSummitCommentator(dt, previousFeet, currentFeet, previousPlayerX);
    updateSummitGoats(dt, previousFeet, currentFeet, previousPlayerX);
    updateSummitEnemies(dt, previousFeet, currentFeet, previousPlayerX);
    if (mode !== "running") return;
    collideSidShots(dt, previousFeet, currentFeet, previousPlayerX);
    if (mode !== "running" || sidBoss?.phase === "victory") return;
    collideWithSpaceEvents(previousFeet, currentFeet, dt, previousPlayerX);
    if (mode !== "running" || spacePitHold) return;
    collideWithSpaceBoss(previousFeet, currentFeet, previousPlayerX);
    collideWithEnemy(previousFeet, currentFeet, dt, previousPlayerX);
    if (mode !== "running") return;
    collideSkyDucks(previousFeet, currentFeet, dt, previousPlayerX);

    if (player.vy < 0) {
      const platform = landingPlatform(previousFeet, currentFeet, previousPlayerX, player.x);
      if (platform) {
        if (platform.kind === "break") platform.broken = true;
        // Snap the sprite's feet to the exact contact plane; otherwise one frame of
        // downward travel makes the character visibly sink into the platform.
        player.y = platform.y + player.height / 2;
        player.vy = platform.kind === "spring" ? 930 : platform.summitKind === "purple" ? 780 : 720;
        if (softBootJumps > 0) { player.vy = Math.max(player.vy, 930); softBootJumps -= 1; }
        if (antarctica && platform.frozenUntil > elapsed) winterSlide = 1.1;
        openingJump = false;
        somersault = null;
        if (elapsed >= nextSomersaultAt && !freeFlight && Math.random() < .14) {
          somersault = { age: 0, direction: facing };
          nextSomersaultAt = elapsed + 6;
        }
        if (platform.kind === "spring") {
          effects.push({ index: 10, x: player.x, y: platform.y, age: 0, duration: .3, size: 46 * visualScale() });
        }
      }
    }
    if (mode !== "running") return;

    for (const powerup of powerups) {
      if (powerup.collected || kimiBoost > 0) continue;
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
      ) + Math.abs(player.vx) * dt;
      const verticalReach = hitbox.height / 2 + player.height / 2
        + (Math.abs(player.vy) + hazard.speed) * dt + 4;
      if (Math.abs(player.x - hitbox.x) > horizontalReach || Math.abs(player.y - hitbox.y) > verticalReach) continue;

      // Feet crossing the surface is sufficient: requiring torso overlap as
      // well misses shallow landings and lets a fast descent tunnel through.
      if (hazard.bouncy && player.vy < 0) {
        const hazardTop = spriteLanding(hitbox.sprite, hitbox.x, hitbox.y, hitbox.width, hitbox.height,
          hitbox.x, previousHazardY, previousFeet, currentFeet, previousPlayerX);
        if (hazardTop !== null) {
          hazard.dead = true;
          player.y = hazardTop + player.height / 2;
          player.vy = 880;
          protectBounce();
          somersault = null;
          openingJump = false;
          effects.push({ index: 10, x: player.x, y: hazardTop, age: 0, duration: .34, size: 48 * visualScale() });
          continue;
        }
      }
      if (invulnerableTimer > 0) continue;
      const overlaps = sweptHazardContact(hitbox, previousHazardY, previousPlayerX,
        previousFeet + player.height / 2);
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
    if (rocketTimer > 0 || kimiBoost > 0 || freeFlight) {
      openingJump = false;
      somersault = null;
    }
    if (!openingJump && !sidBoss) {
      followPlayerCamera(dt);
    }
    if (updateHawks(dt, previousFeet, currentFeet, previousPlayerX)) return;
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
    // Reset the compositor before the opaque backdrop paints the entire frame.
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
    // Keep an explicit physical-pixel clear for restored WebKit contexts;
    // mobile regressions here previously left trails across scene changes.
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (mode === "intro" && intro) { drawIntro(); return; }
    drawBackdrop();
    if (antarcticaScene) { drawAntarcticaScene(); return; }
    if (antarcticaArrival) { drawAntarcticaArrival(); return; }

    for (const platform of platforms) {
      if (platform.broken) continue;
      if (platform.spaceService === spaceEncounter && spaceEncounter?.type === "pitstop") continue;
      const garagePlatform = forgottenPaddock && art.garagePlatforms && art.garagePlatforms[platform.spriteIndex];
      if (platform.commentator) {
        drawCommentatorPlatform(platform);
      } else if (summit) {
        drawSummitPlatform(platform);
      } else if (antarctica) {
        drawIcePlatform(platform);
      } else if (garagePlatform) {
        drawFrame(garagePlatform, platform.x, platform.y, platform.spriteWidth, "platform");
      } else {
        drawSprite(platform.spriteIndex, platform.x, platform.y, platform.spriteWidth, "platform", platform.height);
      }
    }
    for (const enemy of enemies) {
      if (enemy.dead) continue;
      if (enemy.type === "piranha") { drawPiranha(enemy); continue; }
      const bobY = enemy.y + Math.sin(elapsed * 4 + enemy.phase) * 4;
      drawFrame(enemyFrame(enemy), enemy.x, bobY, enemyWidth());
    }

    for (const hazard of hazards) {
      if (!hazard.dead) drawHazard(hazard);
    }
    drawHawks();
    drawSkyDucks();
    drawSpaceBoss();
    drawSpaceEvents();
    drawBabyKimi();
    drawSummitCommentator();
    drawSummitEnemies();
    drawWinterEncounter();
    drawSidBoss();
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

    drawPortal();
    if (player) {
      if (rocketTimer > 0 && drawRocketRide()) {
        drawInvulnerabilityShield();
      } else {
        const screenY = worldToScreen(player.y);
        ctx.save();
        if (portalTransition) {
          const t = clamp(portalTransition.age / 2.7, 0, 1);
          const ease = t * t * (3 - 2 * t);
          ctx.translate(width * (portalTransition.x + (.5 - portalTransition.x) * ease),
            height * (portalTransition.y + (.26 - portalTransition.y) * ease));
          ctx.rotate(t * Math.PI * 4);
          ctx.scale(1 - ease * .98, 1 - ease * .98);
          ctx.globalAlpha = 1 - ease;
        } else {
          ctx.translate(player.x, screenY);
        }
        ctx.rotate(Math.max(-.08, Math.min(.08, -player.vx / Math.max(1, width) * .1)));
        if (somersault && !portalTransition) {
          const t = clamp(somersault.age / .54, 0, 1);
          ctx.rotate(somersault.direction * Math.PI * 2 * t * t * (3 - 2 * t));
        }
        if (babyKimi && babyKimi.state === "holding") {
          ctx.rotate(Math.sin(babyKimi.hold * Math.PI * 12) * .16);
        }
        ctx.scale(facing, 1);
        const heroSprite = somersault ? art.heroFrames[0] : currentHeroSprite();
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

    if (babyKimi && babyKimi.state === "holding") {
      // Small hands follow the captured torso, making the grip visible on top
      // of the player sprite while both characters shake together.
      const gripY = worldToScreen(player.y) + player.height * .1;
      ctx.save();
      ctx.strokeStyle = "#dfc5a2";
      ctx.lineWidth = 5;
      for (const side of [-1, 1]) {
        const gripX = player.x + side * player.width * .35;
        ctx.beginPath();
        ctx.moveTo(babyKimi.x + side * 9, worldToScreen(babyKimi.y) + 4);
        ctx.lineTo(gripX, gripY);
        ctx.stroke();
        ctx.fillStyle = "#edb88d";
        ctx.fillRect(gripX - 3, gripY - 3, 6, 7);
      }
      ctx.restore();
    }

    if (mode === "running") {
      if (kimiBoost > 0) {
        ctx.save();
        ctx.fillStyle = "#ffe4a0";
        ctx.font = "bold 13px system-ui";
        ctx.textAlign = "center";
        ctx.fillText("KIMI LAUNCH ↑", width / 2, height * .27);
        ctx.restore();
      }
      if (forgottenPaddock && elapsed < arrivalUntil) {
        ctx.save();
        ctx.fillStyle = "rgba(5, 14, 20, .85)";
        ctx.fillRect(0, height * .25, width, 64);
        ctx.fillStyle = "#baf3df";
        ctx.font = "bold 19px system-ui";
        ctx.textAlign = "center";
        ctx.fillText(antarctica ? "АНТАРКТИДА" : "ЗАБЫТЫЙ ПАДДОК", width / 2, height * .25 + 39);
        ctx.restore();
      }
      if (elapsed < bossVictoryUntil) {
        ctx.save();
        ctx.fillStyle = "#c4f4cf";
        ctx.font = "bold 17px system-ui";
        ctx.textAlign = "center";
        ctx.fillText("ТОТО ПОБЕЖДЁН  +300", width / 2, height * .3);
        ctx.restore();
      } else if (elapsed < bonusNoticeUntil) {
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
    if (softBootJumps > 0) {
      ctx.save(); ctx.textAlign = "right"; ctx.font = "bold 10px monospace";
      ctx.fillStyle = "#efb2a2"; ctx.strokeStyle = "#111c2d"; ctx.lineWidth = 3;
      ctx.strokeText(`SOFT ×${softBootJumps}`, width - 15, 94);
      ctx.fillText(`SOFT ×${softBootJumps}`, width - 15, 94); ctx.restore();
    }
    if (antarctica) drawWinterMemory(true);
    const blackout = portalTransition
      ? clamp((portalTransition.age - 2.65) / .35, 0, 1)
      : forgottenPaddock ? clamp((arrivalUntil - elapsed - 3.4) / .6, 0, 1) : 0;
    if (blackout > 0) {
      ctx.save();
      ctx.globalAlpha = blackout;
      ctx.fillStyle = antarctica ? "#d9edff" : "#020207";
      ctx.fillRect(0, 0, width, height);
      ctx.restore();
    }
  }

  function loop(now) {
    if (mode !== "running" && mode !== "intro") return;
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
    while (updateAccumulator >= fixedStep && (mode === "running" || mode === "intro")) {
      if (mode === "intro") updateIntro(fixedStep);
      else update(fixedStep);
      updateAccumulator -= fixedStep;
    }
    const renderInterval = 1000 / 60;
    if (now - lastRenderTime >= renderInterval - .5 || (mode !== "running" && mode !== "intro")) {
      draw();
      if (waitingForStage) {
        ctx.save();
        const boxWidth = Math.min(width - 32, 310);
        ctx.fillStyle = "rgba(8, 15, 22, .9)";
        ctx.fillRect((width - boxWidth) / 2, height * .45, boxWidth, 58);
        ctx.fillStyle = "#f5eee2";
        ctx.textAlign = "center";
        ctx.font = "bold 13px monospace";
        ctx.fillText(`Загружаем: ${stageNames[waitingForStage]}`, width / 2, height * .45 + 23);
        ctx.font = "11px monospace";
        ctx.fillText("Игра на паузе · прогресс сохранён", width / 2, height * .45 + 43);
        ctx.restore();
      }
      lastRenderTime += renderInterval * Math.max(1,
        Math.floor((now - lastRenderTime + .5) / renderInterval));
    }
    if (mode === "running" || mode === "intro") frame = requestAnimationFrame(loop);
  }

  function resize() {
    const bounds = wrap.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const nextViewportKey = `${bounds.width}:${bounds.height}:${window.devicePixelRatio}:${artReady}`;
    if (nextViewportKey === viewportKey) return;
    viewportKey = nextViewportKey;
    const previousWidth = width;
    const previousHeight = height;
    const previousArenaHeight = sidArenaHeight();
    // Keep horizontal world geometry stable; reveal more/less vertical scenery
    // to fill the viewport with one uniform scale, never stretching sprites.
    width = logicalViewportWidth;
    const mobileViewport = logicalViewportWidth === 390;
    height = mobileViewport ? width * mobileWorldAspect : width * bounds.height / bounds.width;
    // Cover the mobile viewport without stretching or exposing extra world at zoom-out.
    // Desktop keeps its deliberately bounded playfield. Crop only excess scenery.
    const displayScale = mobileViewport
      ? Math.max(bounds.width / width, bounds.height / height)
      : Math.min(bounds.width / width, bounds.height / height);
    visibleWorldHeight = Math.min(height, bounds.height / displayScale);
    canvas.style.width = `${width * displayScale}px`;
    canvas.style.height = `${height * displayScale}px`;
    canvas.style.left = "50%";
    // Browser chrome may shorten a phone viewport: keep the floor/start pad
    // visible and crop only the distant area above, never the player's footing.
    canvas.style.top = mobileViewport ? "auto" : "50%";
    canvas.style.bottom = mobileViewport ? "0" : "auto";
    canvas.style.transform = mobileViewport ? "translateX(-50%)" : "translate(-50%, -50%)";
    // Render above CSS resolution on high-density screens while keeping fill
    // rate bounded: mobile gets extra sprite detail, desktop stays economical.
    const maxDpr = mobileViewport ? 3 : 2;
    // Large desktop displays often report DPR=1. Supersample at 2x there so
    // fine face/hat detail survives subpixel movement and rotation at 900px.
    const minDpr = mobileViewport ? 1 : 2;
    dpr = displayScale * Math.min(maxDpr, Math.max(minDpr, window.devicePixelRatio || 1));
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.imageSmoothingEnabled = false;
    rasterCache = new WeakMap();
    sceneryCache = new WeakMap();
    if (!artReady) {
      // The HTML poster remains visible until the first complete game frame.
      return;
    }
    touchBounds = null;
    cacheBackground();
    // Warm all four hero poses at display resolution before play, including
    // the tucked pose used by the somersault. Source pixels stay untouched.
    const heroHeight = 70 * visualScale();
    for (const pose of art.heroFrames) rasterSprite(pose, heroHeight * pose.sw / pose.sh, heroHeight);
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
      if (sidBoss && previousArenaHeight !== sidArenaHeight()) buildSidArena(previousArenaHeight);
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
    // Let Space activate settings and admin preview buttons normally.
    if (event.target?.closest?.("#doodle-intro-preference, .doodle-test-controls")) return;
    const key = event.key.toLowerCase();
    if (key === "escape" && isGameFullscreen() && !document.fullscreenElement && !document.webkitFullscreenElement) {
      event.preventDefault();
      toggleFullscreen();
      return;
    }
    if (["arrowleft", "arrowright", " ", "a", "d", "ф", "в"].includes(key)) event.preventDefault();
    if (key === " " && !event.repeat) {
      if (mode === "intro") finishIntro();
      else if (mode !== "running") startGame();
    }
    if (mode === "intro") return;
    if (key === "arrowleft" || key === "a" || key === "ф") setDirection("left", true);
    if (key === "arrowright" || key === "d" || key === "в") setDirection("right", true);
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
  startButton.addEventListener("click", () => {
    if (assetLoadFailed) window.location.reload();
    else startGame();
  });
  if (bossTestButton) bossTestButton.addEventListener("click", startTotoBossTest);
  document.getElementById("doodle-antarctica-test")?.addEventListener("click", startAntarcticaTest);
  document.getElementById("doodle-antarctica-arrival-test")?.addEventListener("click", () => startAntarcticaPreview(true));
  document.getElementById("doodle-winter-biome-test")?.addEventListener("click", startWinterBiomeTest);
  document.getElementById("doodle-sid-boss-test")?.addEventListener("click", startSidBossTest);
  document.getElementById("doodle-sid-victory-test")?.addEventListener("click", startSidVictoryTest);
  document.getElementById("doodle-commentator-test")?.addEventListener("click", startCommentatorTest);
  document.getElementById("doodle-marmot-test")?.addEventListener("click", () => startSummitEnemyTest("marmot"));
  document.getElementById("doodle-drone-test")?.addEventListener("click", () => startSummitEnemyTest("drone"));
  for (const kind of ["carbon", "satellite", "pitstop", "alonso"]) {
    document.getElementById(`doodle-space-${kind}-test`)?.addEventListener("click", () => startSpaceEventTest(kind));
  }
  for (const kind of ["iceman", "strategist", "steward"]) {
    document.getElementById(`doodle-winter-${kind}-test`)?.addEventListener("click", async () => {
      await startWinterBiomeTest();
      if (!antarctica || !adminBossTestMode || mode !== "running") return;
      resetWinterEncounters();
      spawnWinterEncounter(kind);
      if (bossTestStatus) bossTestStatus.textContent = "Враг выше экрана — допрыгните до него · тест без сохранения результата";
      draw();
    });
  }
  if (introSkipButton) introSkipButton.addEventListener("click", finishIntro);
  introPreferenceButton?.addEventListener("click", () => {
    alwaysSkipIntro = !alwaysSkipIntro;
    try { localStorage.setItem(introStorageKey, alwaysSkipIntro ? "1" : "0"); } catch (error) { /* Keep the choice for this page session. */ }
    syncIntroPreference();
    if (alwaysSkipIntro && mode === "intro") finishIntro();
  });
  if (adminSandbox && flightButton) {
    flightButton.addEventListener("click", () => {
      freeFlight = !freeFlight;
      flightButton.setAttribute("aria-pressed", String(freeFlight));
      flightButton.textContent = `Свободный полёт: ${freeFlight ? "вкл." : "выкл."}`;
      if (freeFlight && mode !== "running") startGame(true);
      if (freeFlight && player) player.vy = 720;
      canvas.focus({ preventScroll: true });
    });
  }
  const portalTestButton = document.getElementById("doodle-portal-test");
  if (adminSandbox && portalTestButton) {
    portalTestButton.addEventListener("click", async () => {
      if (!artReady) return;
      if (!await preparePreview(["garage"])) return;
      if (mode !== "running") startGame(true);
      beginPortal();
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
    if (mode === "intro") {
      event.preventDefault();
      finishIntro();
      return;
    }
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

  canvas.addEventListener("contextlost", (event) => {
    event.preventDefault();
    cancelAnimationFrame(frame);
    releaseTouchControls();
  });
  canvas.addEventListener("contextrestored", () => {
    viewportKey = "";
    garageCache = null;
    winterSeamCache = null;
    resize();
    previousTime = lastRenderTime = performance.now();
    updateAccumulator = 0;
    if (mode === "running" || mode === "intro") frame = requestAnimationFrame(loop);
  });

  function checkedFrames(frames, count) {
    if (frames.length !== count || frames.some((pose) => !pose)) throw new Error("Invalid animation frames");
    return frames;
  }

  function stageAssets(name) {
    const single = (key) => (sheet) => ({ [key]: checkedFrames(splitSpriteSheet(sheet, 1), 1)[0] });
    if (name === "summit") return [
      ["summitPlatformsSrc", sheet => ({summitPlatforms:summitPlatformFrames(sheet)})],
      ["summitBackgroundSrc", (sheet) => ({ summit: sheet })],
      ["summitCommentatorSrc", (sheet) => ({ summitCommentator: checkedFrames(splitSpriteSheet(sheet, 4, null, true, true), 4) })],
      ["summitGoatSrc", (sheet) => ({ summitGoat: checkedFrames(splitSpriteSheet(sheet, 4, null, true, true), 4) })],
      ["summitCableCarSrc", single("summitCableCar")],
      ["summitMarmotSrc", sheet => ({summitMarmot:summitEnemyFrames(sheet)})],
      ["summitDroneSrc", sheet => ({summitDrone:summitEnemyFrames(sheet)})],
      ["summitDroneBrokenSrc", single("summitDroneBroken")],
    ];
    if (name === "sky") return [
      ["backgroundCloudSrc", (sheet) => ({ cloud: sheet })],
      ["hawkSheetSrc", (sheet) => ({ hawkFrames: checkedFrames(splitSpriteSheet(sheet, 4), 4) })],
      ["totoCloudSrc", (sheet) => ({ totoCloud: checkedFrames(splitSpriteSheet(sheet, 1, null, false), 1)[0] })],
      ["duckSheetSrc", (sheet) => ({ duckFrames: checkedFrames(splitSpriteSheet(sheet, 4), 4),
        duckCellWidth: sheet.naturalWidth / 4, duckBodyY: sheet.naturalHeight * .61 })],
    ];
    if (name === "space") return [
      ["backgroundSpaceSrc", (sheet) => ({ space: sheet })],
      ["spaceBossSrc", single("spaceBoss")],
      ["bossWheelSrc", single("bossWheel")],
      ["spaceCarbonSrc", (sheet) => ({ spaceCarbon: checkedFrames(splitSpriteSheet(sheet, 4, [0, .42, .718, .86, 1]), 4) })],
      ["spaceSatelliteSrc", (sheet) => ({ spaceSatellite: checkedFrames(splitSpriteSheet(sheet, 4, null, false), 4) })],
      ["spacePitstopSrc", (sheet) => ({ spacePitstop: checkedFrames(splitSpriteSheet(sheet, 4, null, false), 4) })],
      ["spaceAlonsoSrc", (sheet) => ({ spaceAlonso: checkedFrames(splitSpriteSheet(sheet, 4), 4) })],
    ];
    if (name === "garage") return [
      ["garageSrc", (sheet) => ({ garage: sheet })],
      ["garagePlatformsSrc", (sheet) => ({ garagePlatforms: checkedFrames(splitSpriteSheet(sheet, 4, [0, .26, .535, .80, 1]), 4) })],
      ["babyKimiSrc", single("babyKimi")],
    ];
    if (name === "winter") return [
      ["antarcticaSrc", (sheet) => ({ antarctica: sheet })],
      ["controlConsoleSrc", (sheet) => ({ controlConsole: checkedFrames(splitSpriteSheet(sheet, 1, null, false), 1)[0] })],
      ["caveArrivalSrc", (sheet) => ({ caveArrival: sheet })],
      ["sidSheetSrc", (sheet) => ({ sidFrames: checkedFrames(storyFrames(sheet, 4), 4) })],
      ["totoStorySrc", (sheet) => ({ totoStoryFrames: checkedFrames(storyFrames(sheet, 4, [0, .19, .51, .83, 1]), 4) })],
      ["heroStorySrc", (sheet) => ({ heroStoryFrames: checkedFrames(storyFrames(sheet, 6), 6) })],
      ["walkSheetSrc", (sheet) => ({ walkFrames: checkedFrames(walkFrames(sheet), 8) })],
      ["piranhaSheetSrc", (sheet) => ({ piranhaFrames: checkedFrames(piranhaFrames(sheet), 4) })],
      ["winterPlatformsSrc", (sheet) => ({ winterPlatforms: checkedFrames(splitSpriteSheet(sheet, 4, null, false), 4) })],
      ["winterPortraitSrc", (sheet) => ({ winterPortrait: checkedFrames(splitSpriteSheet(sheet, 1, null, false), 1)[0] })],
      ["winterIcemanSrc", (sheet) => ({ winterIceman: checkedFrames(splitSpriteSheet(sheet, 4, [0, .237, .491, .79, 1], false), 4) })],
      ["winterStrategistSrc", (sheet) => ({ winterStrategist: checkedFrames(splitSpriteSheet(sheet, 4, [0, .217, .499, .794, 1], false), 4) })],
      ["winterStewardSrc", (sheet) => ({ winterSteward: checkedFrames(splitSpriteSheet(sheet, 4, [0, .242, .489, .795, 1], false), 4) })],
      ["sidBossAttackSrc", (sheet) => ({ sidBossAttack: checkedFrames(splitSpriteSheet(sheet, 4, [0, .248, .474, .741, 1], false), 4) })],
      ["sidBossFinaleSrc", (sheet) => ({ sidBossFinale: checkedFrames(splitSpriteSheet(sheet, 4, [0, .233, .462, .707, 1], false), 4) })],
      ["sidBossPropsSrc", (sheet) => ({ sidBossProps: checkedFrames(splitSpriteSheet(sheet, 4, [0, .208, .422, .741, 1]), 4) })],
    ];
    throw new Error(`Unknown asset stage: ${name}`);
  }

  prepareAssets([
    ["atlasSrc", (sheet) => { cropSprites(sheet); return {}; }],
    ["heroSheetSrc", (sheet) => ({ heroFrames: checkedFrames(splitHeroSheet(sheet), 4) })],
    ["backgroundJourneySrc", (sheet) => ({ journey: sheet })],
    ["platformSheetSrc", (sheet) => {
      checkedFrames(splitSpriteSheet(sheet, 4, [0, .26, .536, .806, 1]), 4)
        .forEach((sprite, index) => { sprites[index] = sprite; });
      for (let i = 0; i < sprites.length; i += 1) sprites[i] = bakeSprite(sprites[i]);
      return {};
    }],
    ["rocketSrc", (sheet) => ({ rocketRide: bakeSprite(checkedFrames(splitSpriteSheet(sheet, 1, null, false), 1)[0], 768) })],
    ["rocketEmptySrc", (sheet) => ({ powerupFrames: { rocket: bakeSprite(checkedFrames(splitSpriteSheet(sheet, 1), 1)[0], 384) } })],
    ["wheelCompoundsSrc", (sheet) => {
      const frames = checkedFrames(splitSpriteSheet(sheet, 3, null, true, true), 3).map((pose) => bakeSprite(pose));
      return { wheelFrames: { soft: frames[0], medium: frames[1], hard: frames[2] } };
    }],
    ["marshalSrc", (sheet) => ({ marshal: checkedFrames(splitSpriteSheet(sheet, 1), 1)[0] })],
    ["enemyVariantsSrc", (sheet) => ({ enemyVariants: checkedFrames(splitSpriteSheet(sheet, 4, null, true, true), 4) })],
    ["introScaffoldSrc", (sheet) => ({ introScaffold: checkedFrames(splitSpriteSheet(sheet, 1, null, false), 1)[0] })],
    ["introDriverSrc", (sheet) => ({ introDriver: checkedFrames(splitSpriteSheet(sheet, 1, null, false), 1)[0] })],
    ["introHeroSrc", (sheet) => ({ introHeroFrames: checkedFrames(splitSpriteSheet(sheet, 3, null, false), 3) })],
  ]).then((prepared) => {
    Object.assign(art, prepared);
    artReady = true;
    assetLoadFailed = false;
    startButton.disabled = false;
    resize();
    setOverlay("ready");
    machine.classList.remove("is-loading");
  }).catch(showAssetError);

  if ("ResizeObserver" in window) {
    new ResizeObserver(resize).observe(wrap);
  } else {
    window.addEventListener("resize", resize);
  }
})();
