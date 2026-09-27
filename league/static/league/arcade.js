(() => {
  "use strict";

  const canvas = document.getElementById("arcade-canvas");
  const wrap = document.getElementById("arcade-canvas-wrap");
  const overlay = document.getElementById("arcade-overlay");
  const bananaSpeech = document.getElementById("arcade-banana-speech");
  const startButton = document.getElementById("arcade-start");
  const scoreOutput = document.getElementById("run-score");
  const recordOutput = document.getElementById("personal-record");
  const boardRecordOutput = document.getElementById("board-record");
  const overlayTitle = document.getElementById("arcade-overlay-title");
  const overlayCopy = document.getElementById("arcade-overlay-copy");
  const overlayMark = document.getElementById("arcade-overlay-mark");
  const resetRecordButton = document.getElementById("arcade-reset-record");
  const levelOutput = document.getElementById("arcade-level");
  if (!canvas || !wrap || !overlay || !startButton) return;

  const context = canvas.getContext("2d", { alpha: false });
  context.imageSmoothingEnabled = false;
  const bananaSprite = new Image();
  bananaSprite.src = canvas.dataset.spriteSrc;
  const trackImages = canvas.dataset.trackSrcs.split(",").map((source) => {
    const image = new Image();
    image.src = source.trim();
    return image;
  });
  const isAuthenticated = canvas.dataset.authenticated === "true";
  const board = document.getElementById("arcade-leaderboard-list");
  const boardStatus = document.getElementById("arcade-board-status");
  const csrfToken = document.querySelector("#arcade-csrf-form input[name=csrfmiddlewaretoken]")?.value || "";
  const WORLD_WIDTH = 960;
  let WORLD_HEIGHT = 540;
  const CAR_X = 235;
  let playerScale = 1;
  let isMobileGame = false;
  const PLAYER_WIDTH = 36;
  const PLAYER_HEIGHT = 74;
  const PLAYER_COLLISION_SCALE = 0.78;
  const OBSTACLE_WIDTH = 70;
  const BASE_GAP_HEIGHT = 170;
  const BACKGROUND_SCENE_DURATION = 6.5;
  const BACKGROUND_FADE_DURATION = 1.2;
  const BACKGROUND_OVERSCAN = 1.16;
  const GRAVITY = 1320;
  const FLAP_VELOCITY = -445;
  const STORAGE_KEY = "f1-pit-lane-flight-record-v1";
  let width = 0;
  let height = 0;
  let previousTime = 0;
  let animationFrame = 0;
  let state = "ready";
  let carY = WORLD_HEIGHT * 0.5;
  let carVelocity = 0;
  let score = 0;
  let best = isAuthenticated ? Number(canvas.dataset.record || 0) : readRecord();
  let elapsed = 0;
  let spawnTimer = 0;
  let trackOffset = 0;
  let obstacles = [];
  let overlayTimer = 0;
  let attemptId = null;
  let refreshingBoard = false;

  function readRecord() {
    try {
      const value = Number(window.localStorage.getItem(STORAGE_KEY));
      return Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
    } catch (_) {
      return 0;
    }
  }

  function saveRecord(value) {
    try {
      window.localStorage.setItem(STORAGE_KEY, String(value));
    } catch (_) {
      // The round remains playable when browser storage is disabled.
    }
  }

  function syncScores() {
    scoreOutput.textContent = String(score).padStart(2, "0");
    recordOutput.textContent = String(best);
    boardRecordOutput.textContent = String(best).padStart(2, "0");
    if (levelOutput) levelOutput.textContent = String(getLevel()).padStart(2, "0");
  }

  function getLevel() {
    return Math.floor(score / 5) + 1;
  }

  function getSpeed() {
    const speed = Math.min(520, 250 + score * 8 + elapsed * 3.5);
    return speed * (isMobileGame ? 0.9 : 1);
  }

  function getPlayerHalfWidth() {
    return PLAYER_WIDTH * playerScale * PLAYER_COLLISION_SCALE * 0.5;
  }

  function getPlayerHalfHeight() {
    return PLAYER_HEIGHT * playerScale * PLAYER_COLLISION_SCALE * 0.5;
  }

  function resize() {
    const rect = wrap.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const previousWorldHeight = WORLD_HEIGHT;
    width = Math.max(1, rect.width);
    height = Math.max(1, rect.height);
    isMobileGame = width <= 620 || window.matchMedia("(pointer: coarse)").matches;
    playerScale = isMobileGame ? 1.4 : 1;
    WORLD_HEIGHT = Math.min(900, Math.max(540, Math.round(WORLD_WIDTH * height / width)));
    if (WORLD_HEIGHT !== previousWorldHeight) {
      if (state === "ready") {
        carY = WORLD_HEIGHT * 0.5;
      } else {
        const heightScale = WORLD_HEIGHT / previousWorldHeight;
        carY *= heightScale;
        for (const obstacle of obstacles) obstacle.gapCenter *= heightScale;
      }
    }
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    context.imageSmoothingEnabled = false;
    context.setTransform(
      ratio * width / WORLD_WIDTH,
      0,
      0,
      ratio * height / WORLD_HEIGHT,
      0,
      0,
    );
    positionBananaSpeech();
  }

  function positionBananaSpeech() {
    if (!bananaSpeech || bananaSpeech.hidden || !height) return;
    const bubbleHeight = bananaSpeech.getBoundingClientRect().height * WORLD_HEIGHT / height;
    const gap = 14 * WORLD_HEIGHT / height;
    const playerTop = carY - getPlayerHalfHeight();
    const top = Math.max(3, Math.min(78, (playerTop - bubbleHeight - gap) / WORLD_HEIGHT * 100));
    bananaSpeech.style.top = `${top}%`;
  }

  async function startGame() {
    window.clearTimeout(overlayTimer);
    bananaSpeech.hidden = true;
    overlay.classList.remove("is-gameover");
    startButton.disabled = true;
    startButton.innerHTML = 'На старт <span aria-hidden="true">…</span>';
    attemptId = null;
    if (isAuthenticated) {
      try {
        const response = await fetch(canvas.dataset.startUrl, {
          method: "POST",
          headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" },
          credentials: "same-origin",
        });
        if (response.ok) {
          attemptId = (await response.json()).attempt_id;
        } else if (boardStatus) {
          boardStatus.textContent = "Заезд можно пройти, но сейчас он не сохранится в таблице.";
        }
      } catch (_) {
        // Let players continue even if the leaderboard service is temporarily unavailable.
        if (boardStatus) boardStatus.textContent = "Нет связи с таблицей рекордов — заезд всё равно доступен.";
      }
    }
    state = "playing";
    score = 0;
    elapsed = 0;
    spawnTimer = 0.8;
    trackOffset = 0;
    carY = WORLD_HEIGHT * 0.5;
    carVelocity = FLAP_VELOCITY;
    obstacles = [];
    syncScores();
    overlay.hidden = true;
    startButton.disabled = false;
    startButton.innerHTML = 'На старт <span aria-hidden="true">→</span>';
    canvas.focus({ preventScroll: true });
  }

  function endGame() {
    if (state !== "playing") return;
    state = "gameover";
    overlay.classList.add("is-gameover");
    if (bananaSpeech) {
      bananaSpeech.hidden = false;
      bananaSpeech.setAttribute("aria-label", 'Банан Леклер говорит: "i am stupid..."');
      positionBananaSpeech();
    }
    if (score > best && (!isAuthenticated || attemptId)) {
      best = score;
      if (!isAuthenticated) saveRecord(best);
      overlayMark.textContent = "НОВЫЙ РЕКОРД";
      overlayTitle.textContent = "Новый личный рекорд!";
      overlayCopy.textContent = `Чистый пилотаж: пройдено ${score} ворот. Готов снова выехать на трассу?`;
    } else {
      overlayMark.textContent = "ЗАЕЗД ЗАВЕРШЁН";
      overlayTitle.textContent = "Болид в боксах";
      overlayCopy.textContent = `Пройдено ворот: ${score}. Ещё один круг — и рекорд может пасть.`;
    }
    if (score > 0 && attemptId) submitResult(attemptId, score);
    attemptId = null;
    startButton.innerHTML = 'Ещё круг <span aria-hidden="true">↻</span>';
    syncScores();
    overlayTimer = window.setTimeout(() => { overlay.hidden = false; }, 280);
  }

  function renderLeaderboard(rows) {
    if (!board) return;
    board.replaceChildren();
    if (!rows.length) {
      const empty = document.createElement("li");
      empty.className = "arcade-board-empty";
      empty.textContent = "Пока нет рекордов — первым в таблице можешь стать ты.";
      board.append(empty);
      return;
    }
    for (const row of rows) {
      const item = document.createElement("li");
      if (row.is_current_user) item.classList.add("is-you");
      const place = document.createElement("span");
      place.className = "arcade-rank";
      place.textContent = String(row.rank).padStart(2, "0");
      const name = document.createElement("span");
      name.className = "arcade-driver-name";
      name.textContent = row.username;
      const scoreValue = document.createElement("strong");
      scoreValue.textContent = String(row.score);
      const unit = document.createElement("small");
      unit.textContent = "ворот";
      item.append(place, name, scoreValue, unit);
      board.append(item);
    }
  }

  function syncOwnRank(result) {
    if (!isAuthenticated) return;
    const ownRankLine = document.getElementById("arcade-own-rank-line");
    if (!ownRankLine) return;
    ownRankLine.hidden = !result.rank || result.rank <= 10;
    ownRankLine.replaceChildren(document.createTextNode("Твоё место: "));
    const rankValue = document.createElement("strong");
    rankValue.textContent = String(result.rank || "—");
    ownRankLine.append(rankValue, document.createTextNode(" · рекорд "));
    const ownScore = document.createElement("strong");
    ownScore.textContent = String(result.record || 0);
    ownRankLine.append(ownScore);
  }

  async function refreshLeaderboard() {
    if (refreshingBoard || document.hidden) return;
    refreshingBoard = true;
    try {
      const response = await fetch(canvas.dataset.boardUrl, { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) return;
      const result = await response.json();
      renderLeaderboard(result.records || []);
      syncOwnRank(result);
      if (isAuthenticated) {
        best = Number(result.record || 0);
        canvas.dataset.record = String(best);
        syncScores();
      }
    } catch (_) {
      // The page keeps the last known leaderboard if polling is temporarily unavailable.
    } finally {
      refreshingBoard = false;
    }
  }

  async function submitResult(runId, runScore) {
    if (boardStatus) boardStatus.textContent = "Проверяем результат заезда…";
    try {
      const response = await fetch(canvas.dataset.finishUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
          "X-Requested-With": "XMLHttpRequest",
        },
        credentials: "same-origin",
        body: JSON.stringify({ attempt_id: runId, score: runScore }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Не удалось сохранить рекорд.");
      best = result.record;
      saveRecord(best);
      canvas.dataset.record = String(best);
      syncScores();
      renderLeaderboard(result.records || []);
      syncOwnRank(result);
      if (boardStatus) boardStatus.textContent = result.is_record
        ? `Новый рекорд сохранён · место ${result.rank}`
        : `Твоё место в таблице: ${result.rank}`;
    } catch (error) {
      if (isAuthenticated) {
        best = Number(canvas.dataset.record || 0);
        syncScores();
      }
      if (boardStatus) boardStatus.textContent = error.message || "Не удалось обновить таблицу рекордов.";
    }
  }

  function flap() {
    if (state === "playing") carVelocity = FLAP_VELOCITY;
  }

  function onKeyDown(event) {
    if (event.code !== "Space" && event.code !== "ArrowUp") return;
    if (event.repeat) return;
    const target = event.target;
    if (target instanceof HTMLElement && target.closest("button, a, input, select, textarea")) return;
    if (state !== "playing") return;
    event.preventDefault();
    flap();
  }

  function spawnObstacle() {
    const baseGap = isMobileGame ? 188 : BASE_GAP_HEIGHT;
    const minimumGap = isMobileGame ? 160 : 132;
    const gapHeight = Math.max(minimumGap, baseGap - (getLevel() - 1) * 5);
    const margin = 115 + gapHeight * 0.5;
    const highestCenter = WORLD_HEIGHT - margin;
    const previousObstacle = obstacles[obstacles.length - 1];
    const maxShift = isMobileGame ? 95 : 120;
    const proposedCenter = previousObstacle
      ? previousObstacle.gapCenter + (Math.random() * 2 - 1) * maxShift
      : margin + Math.random() * (highestCenter - margin);
    const gapCenter = Math.max(margin, Math.min(highestCenter, proposedCenter));
    obstacles.push({ x: WORLD_WIDTH + 40, gapCenter, gapHeight, passed: false });
  }

  function intersectsObstacle(obstacle) {
    const playerHalfWidth = getPlayerHalfWidth();
    const playerHalfHeight = getPlayerHalfHeight();
    const carLeft = CAR_X - playerHalfWidth;
    const carRight = CAR_X + playerHalfWidth;
    if (carRight < obstacle.x - 7 || carLeft > obstacle.x + OBSTACLE_WIDTH + 7) return false;
    const topEnd = obstacle.gapCenter - obstacle.gapHeight * 0.5;
    const bottomStart = obstacle.gapCenter + obstacle.gapHeight * 0.5;
    return carY - playerHalfHeight < topEnd + 4 || carY + playerHalfHeight > bottomStart;
  }

  function update(delta) {
    if (state !== "playing") return;
    elapsed += delta;
    const speed = getSpeed();
    trackOffset = (trackOffset + delta * speed) % (WORLD_WIDTH + 180);
    carVelocity += GRAVITY * delta;
    carY += carVelocity * delta;
    spawnTimer -= delta;
    if (spawnTimer <= 0) {
      spawnObstacle();
      const interval = isMobileGame ? 1.9 : 1.72;
      const minimumInterval = isMobileGame ? 1.25 : 1.05;
      spawnTimer = Math.max(minimumInterval, interval - score * 0.015 - elapsed * 0.003);
    }
    for (const obstacle of obstacles) {
      obstacle.x -= speed * delta;
      if (!obstacle.passed && obstacle.x + OBSTACLE_WIDTH < CAR_X - getPlayerHalfWidth()) {
        obstacle.passed = true;
        score += 1;
        syncScores();
      }
      if (intersectsObstacle(obstacle)) {
        endGame();
        return;
      }
    }
    obstacles = obstacles.filter((obstacle) => obstacle.x > -OBSTACLE_WIDTH - 20);
    const playerHalfHeight = getPlayerHalfHeight();
    if (carY - playerHalfHeight < 26 || carY + playerHalfHeight > WORLD_HEIGHT - 35) endGame();
  }

  function drawBackgroundScene(image, panProgress) {
    if (!image?.complete || !image.naturalWidth) return false;
    const backgroundScale = Math.max(
      WORLD_WIDTH / image.naturalWidth,
      WORLD_HEIGHT / image.naturalHeight,
    );
    const backgroundWidth = Math.max(
      WORLD_WIDTH * BACKGROUND_OVERSCAN,
      image.naturalWidth * backgroundScale,
    );
    const backgroundHeight = image.naturalHeight * backgroundScale;
    const panDistance = Math.max(0, backgroundWidth - WORLD_WIDTH);
    context.drawImage(
      image,
      -panDistance * panProgress,
      (WORLD_HEIGHT - backgroundHeight) * 0.5,
      backgroundWidth,
      backgroundHeight,
    );
    return true;
  }

  function drawBackground(time) {
    const scenePosition = (state === "playing" || state === "gameover" ? elapsed : 0) / BACKGROUND_SCENE_DURATION;
    const sceneIndex = Math.floor(scenePosition) % trackImages.length;
    const sceneProgress = scenePosition % 1;
    const currentScene = trackImages[sceneIndex];
    const loadedFallback = trackImages.find((image) => image.complete && image.naturalWidth);
    if (!drawBackgroundScene(currentScene, sceneProgress)) {
      if (!drawBackgroundScene(loadedFallback, sceneProgress)) {
        context.fillStyle = "#6fb9f2";
        context.fillRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT);
      }
    }

    const fadeStart = 1 - BACKGROUND_FADE_DURATION / BACKGROUND_SCENE_DURATION;
    if (sceneProgress > fadeStart) {
      const nextScene = trackImages[(sceneIndex + 1) % trackImages.length];
      if (nextScene.complete && nextScene.naturalWidth) {
        const fadeProgress = (sceneProgress - fadeStart) / (1 - fadeStart);
        context.save();
        context.globalAlpha = fadeProgress * fadeProgress * (3 - 2 * fadeProgress);
        drawBackgroundScene(nextScene, 0);
        context.restore();
      }
    }

    context.save();
    context.globalAlpha = 0.28;
    const streakWidth = Math.min(48, Math.round(getSpeed() * 0.075));
    for (let index = 0; index < 12; index += 1) {
      const x = ((index * 137 - trackOffset * 1.7) % (WORLD_WIDTH + 64) + WORLD_WIDTH + 64) % (WORLD_WIDTH + 64) - 64;
      const y = WORLD_HEIGHT * 0.72 + (index * 29 % Math.round(WORLD_HEIGHT * 0.16));
      context.fillStyle = index % 3 === 0 ? "#ffbd4a" : "#8fe8ff";
      context.fillRect(x, y, streakWidth, 3);
    }
    context.restore();
  }

  function drawGate(obstacle) {
    const x = obstacle.x;
    const gapTop = obstacle.gapCenter - obstacle.gapHeight * .5;
    const gapBottom = obstacle.gapCenter + obstacle.gapHeight * .5;
    const sections = [
      { y: 0, h: gapTop, capY: gapTop - 18 },
      { y: gapBottom, h: WORLD_HEIGHT - gapBottom, capY: gapBottom },
    ];
    for (const section of sections) {
      context.fillStyle = "#10182e";
      context.fillRect(x, section.y, OBSTACLE_WIDTH, section.h);
      context.fillStyle = "#ff455b";
      context.fillRect(x + 6, section.y, 7, section.h);
      context.fillStyle = "#273554";
      context.fillRect(x + 13, section.y, 5, section.h);
      for (let stripeY = section.y + 8; stripeY < section.y + section.h; stripeY += 30) {
        context.fillStyle = "#ff455b";
        context.fillRect(x + 14, stripeY, OBSTACLE_WIDTH - 28, 12);
        context.fillStyle = "#ffbd4a";
        context.fillRect(x + 14, stripeY + 12, OBSTACLE_WIDTH - 28, 5);
      }

      const capY = section.capY;
      context.fillStyle = "#090f20";
      context.fillRect(x - 7, capY, OBSTACLE_WIDTH + 14, 22);
      context.fillStyle = "#ffbd4a";
      context.fillRect(x - 5, capY + 2, OBSTACLE_WIDTH + 10, 18);
      const checkerWidth = (OBSTACLE_WIDTH + 10) / 10;
      for (let cell = 0; cell < 10; cell += 1) {
        const checkerX = x - 5 + cell * checkerWidth;
        if (cell % 2 === 0) {
          context.fillStyle = "#f34458";
          context.fillRect(checkerX, capY + 2, checkerWidth, 8);
          context.fillStyle = "#fff0bb";
          context.fillRect(checkerX, capY + 12, checkerWidth, 8);
        } else {
          context.fillStyle = "#fff0bb";
          context.fillRect(checkerX, capY + 2, checkerWidth, 8);
          context.fillStyle = "#f34458";
          context.fillRect(checkerX, capY + 12, checkerWidth, 8);
        }
      }
    }
  }

  function drawCar(time) {
    const idleBounce = state === "playing" ? 0 : Math.sin(time * .002) * 7;
    const rotation = state === "playing" ? Math.max(-.34, Math.min(.48, carVelocity / 1050)) : Math.sin(time * .0015) * .025;
    context.save();
    context.translate(CAR_X, carY + idleBounce);
    context.rotate(rotation);
    context.scale(-playerScale, playerScale);
    if (bananaSprite.complete && bananaSprite.naturalWidth) {
      context.drawImage(
        bananaSprite,
        155,
        41,
        207,
        430,
        -PLAYER_WIDTH * 0.5,
        -PLAYER_HEIGHT * 0.5,
        PLAYER_WIDTH,
        PLAYER_HEIGHT,
      );
    } else {
      context.fillStyle = "#ffd92e";
      context.beginPath();
      context.ellipse(0, 0, 16, 34, -.12, 0, Math.PI * 2);
      context.fill();
      context.fillStyle = "#644329";
      context.fillRect(-4, -40, 8, 6);
      context.fillStyle = "#25233a";
      context.fillRect(-5, -5, 2, 2);
      context.fillRect(3, -5, 2, 2);
    }

    context.restore();
  }

  function draw(time) {
    context.clearRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT);
    drawBackground(time);
    for (const obstacle of obstacles) drawGate(obstacle);
    drawCar(time);

    if (state === "ready") {
      context.fillStyle = "rgba(226,235,244,.68)";
      context.font = "800 13px Manrope, sans-serif";
      context.textAlign = "center";
      context.fillText("ПРОЙДИ МЕЖДУ ВОРОТАМИ", CAR_X, WORLD_HEIGHT - 64);
    }
  }

  function frame(time) {
    if (!previousTime) previousTime = time;
    const delta = Math.min(.034, (time - previousTime) / 1000);
    previousTime = time;
    update(delta);
    draw(time);
    animationFrame = window.requestAnimationFrame(frame);
  }

  startButton.addEventListener("click", () => { void startGame(); });
  canvas.addEventListener("pointerdown", (event) => {
    if (state !== "playing") return;
    event.preventDefault();
    flap();
  });
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("resize", resize, { passive: true });
  if ("ResizeObserver" in window) new ResizeObserver(resize).observe(wrap);
  document.addEventListener("visibilitychange", () => {
    previousTime = 0;
    if (!document.hidden) void refreshLeaderboard();
  });
  resetRecordButton?.addEventListener("click", () => {
    if (isAuthenticated) return;
    best = 0;
    saveRecord(best);
    syncScores();
  });

  resize();
  syncScores();
  draw(0);
  void refreshLeaderboard();
  const leaderboardTimer = window.setInterval(() => { void refreshLeaderboard(); }, 15000);
  animationFrame = window.requestAnimationFrame(frame);

  window.addEventListener("pagehide", () => {
    if (animationFrame) window.cancelAnimationFrame(animationFrame);
    window.clearInterval(leaderboardTimer);
  }, { once: true });
})();
