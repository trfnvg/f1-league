(() => {
  "use strict";

  const canvas = document.getElementById("arcade-canvas");
  const wrap = document.getElementById("arcade-canvas-wrap");
  const overlay = document.getElementById("arcade-overlay");
  const startButton = document.getElementById("arcade-start");
  const scoreOutput = document.getElementById("run-score");
  const recordOutput = document.getElementById("personal-record");
  const boardRecordOutput = document.getElementById("board-record");
  const overlayTitle = document.getElementById("arcade-overlay-title");
  const overlayCopy = document.getElementById("arcade-overlay-copy");
  const overlayMark = document.getElementById("arcade-overlay-mark");
  const resetRecordButton = document.getElementById("arcade-reset-record");
  if (!canvas || !wrap || !overlay || !startButton) return;

  const context = canvas.getContext("2d", { alpha: false });
  const WORLD_WIDTH = 960;
  const WORLD_HEIGHT = 540;
  const CAR_X = 235;
  const CAR_RADIUS = 22;
  const OBSTACLE_WIDTH = 88;
  const GAP_HEIGHT = 196;
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
  let best = readRecord();
  let elapsed = 0;
  let spawnTimer = 0;
  let trackOffset = 0;
  let obstacles = [];
  let overlayTimer = 0;

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
  }

  function resize() {
    const rect = wrap.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    width = Math.max(1, rect.width);
    height = Math.max(1, rect.height);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    context.setTransform(
      ratio * width / WORLD_WIDTH,
      0,
      0,
      ratio * height / WORLD_HEIGHT,
      0,
      0,
    );
  }

  function startGame() {
    window.clearTimeout(overlayTimer);
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
    canvas.focus({ preventScroll: true });
  }

  function endGame() {
    if (state !== "playing") return;
    state = "gameover";
    if (score > best) {
      best = score;
      saveRecord(best);
      overlayMark.textContent = "НОВЫЙ РЕКОРД";
      overlayTitle.textContent = "Новый личный рекорд!";
      overlayCopy.textContent = `Чистый пилотаж: пройдено ${score} ворот. Готов снова выехать на трассу?`;
    } else {
      overlayMark.textContent = "ЗАЕЗД ЗАВЕРШЁН";
      overlayTitle.textContent = "Болид в боксах";
      overlayCopy.textContent = `Пройдено ворот: ${score}. Ещё один круг — и рекорд может пасть.`;
    }
    startButton.innerHTML = 'Ещё круг <span aria-hidden="true">↻</span>';
    syncScores();
    overlayTimer = window.setTimeout(() => { overlay.hidden = false; }, 280);
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
    const margin = 115 + GAP_HEIGHT * 0.5;
    const gapCenter = margin + Math.random() * (WORLD_HEIGHT - margin * 2);
    obstacles.push({ x: WORLD_WIDTH + 40, gapCenter, passed: false });
  }

  function intersectsObstacle(obstacle) {
    const closestX = Math.max(obstacle.x, Math.min(CAR_X, obstacle.x + OBSTACLE_WIDTH));
    const dx = CAR_X - closestX;
    if (Math.abs(dx) > CAR_RADIUS + 8) return false;
    const topEnd = obstacle.gapCenter - GAP_HEIGHT * 0.5;
    const bottomStart = obstacle.gapCenter + GAP_HEIGHT * 0.5;
    return carY - CAR_RADIUS < topEnd || carY + CAR_RADIUS > bottomStart;
  }

  function update(delta) {
    if (state !== "playing") return;
    elapsed += delta;
    trackOffset = (trackOffset + delta * 210) % 120;
    carVelocity += GRAVITY * delta;
    carY += carVelocity * delta;
    spawnTimer -= delta;
    if (spawnTimer <= 0) {
      spawnObstacle();
      spawnTimer = Math.max(1.28, 1.68 - elapsed * 0.008);
    }
    const speed = Math.min(390, 285 + elapsed * 3.2);
    for (const obstacle of obstacles) {
      obstacle.x -= speed * delta;
      if (!obstacle.passed && obstacle.x + OBSTACLE_WIDTH < CAR_X - 18) {
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
    if (carY - CAR_RADIUS < 26 || carY + CAR_RADIUS > WORLD_HEIGHT - 35) endGame();
  }

  function roundedRect(x, y, w, h, radius) {
    const r = Math.min(radius, w / 2, h / 2);
    context.beginPath();
    context.moveTo(x + r, y);
    context.arcTo(x + w, y, x + w, y + h, r);
    context.arcTo(x + w, y + h, x, y + h, r);
    context.arcTo(x, y + h, x, y, r);
    context.arcTo(x, y, x + w, y, r);
    context.closePath();
  }

  function drawBackground(time) {
    const sky = context.createLinearGradient(0, 0, 0, WORLD_HEIGHT);
    sky.addColorStop(0, "#101c29");
    sky.addColorStop(.58, "#172735");
    sky.addColorStop(1, "#0b1119");
    context.fillStyle = sky;
    context.fillRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT);

    const glow = context.createRadialGradient(710, 125, 10, 710, 125, 360);
    glow.addColorStop(0, "rgba(255,67,54,.13)");
    glow.addColorStop(1, "rgba(255,67,54,0)");
    context.fillStyle = glow;
    context.fillRect(300, 0, 660, 400);

    context.save();
    context.globalAlpha = .36;
    for (let index = 0; index < 42; index += 1) {
      const x = (index * 197 + 73) % WORLD_WIDTH;
      const y = (index * 83 + 29) % 330;
      const pulse = .35 + .65 * Math.abs(Math.sin(time * .001 + index));
      context.fillStyle = index % 6 === 0 ? `rgba(255,111,96,${pulse})` : `rgba(215,230,246,${pulse})`;
      context.fillRect(x, y, index % 5 === 0 ? 3 : 2, index % 5 === 0 ? 3 : 2);
    }
    context.restore();

    context.fillStyle = "rgba(22,34,47,.8)";
    for (let index = 0; index < 15; index += 1) {
      const buildingX = index * 76 - (trackOffset * .22 % 76);
      const buildingHeight = 65 + (index * 41 % 105);
      context.fillRect(buildingX, 330 - buildingHeight, 44, buildingHeight);
      context.fillStyle = "rgba(255,115,91,.18)";
      for (let row = 0; row < 3; row += 1) context.fillRect(buildingX + 8 + row * 10, 344 - buildingHeight, 3, 3);
      context.fillStyle = "rgba(22,34,47,.8)";
    }

    context.fillStyle = "#0b1118";
    context.fillRect(0, 365, WORLD_WIDTH, WORLD_HEIGHT - 365);
    context.fillStyle = "rgba(203,216,231,.07)";
    for (let index = 0; index < 11; index += 1) {
      const x = index * 120 - trackOffset;
      context.beginPath();
      context.moveTo(x, 365);
      context.lineTo(x - 185, WORLD_HEIGHT);
      context.lineTo(x - 176, WORLD_HEIGHT);
      context.lineTo(x + 6, 365);
      context.fill();
    }

    const floor = WORLD_HEIGHT - 34;
    context.fillStyle = "#eef2f4";
    context.fillRect(0, floor, WORLD_WIDTH, 4);
    for (let index = 0; index < 28; index += 1) {
      const x = (index * 52 - trackOffset * 1.4) % WORLD_WIDTH;
      context.fillStyle = index % 2 ? "#f0f2f4" : "#e33b31";
      context.fillRect(x, floor + 4, 27, 5);
    }
  }

  function drawGate(obstacle) {
    const x = obstacle.x;
    const gapTop = obstacle.gapCenter - GAP_HEIGHT * .5;
    const gapBottom = obstacle.gapCenter + GAP_HEIGHT * .5;
    const sections = [
      { y: 0, h: gapTop, capY: gapTop - 19, capDirection: -1 },
      { y: gapBottom, h: WORLD_HEIGHT - gapBottom, capY: gapBottom, capDirection: 1 },
    ];
    for (const section of sections) {
      const bodyGradient = context.createLinearGradient(x, 0, x + OBSTACLE_WIDTH, 0);
      bodyGradient.addColorStop(0, "#394b5e");
      bodyGradient.addColorStop(.14, "#df4238");
      bodyGradient.addColorStop(.5, "#fa5548");
      bodyGradient.addColorStop(1, "#842d2b");
      context.fillStyle = bodyGradient;
      context.fillRect(x, section.y, OBSTACLE_WIDTH, section.h);

      context.save();
      context.beginPath();
      context.rect(x, section.y, OBSTACLE_WIDTH, section.h);
      context.clip();
      context.globalAlpha = .4;
      for (let stripe = -WORLD_HEIGHT; stripe < WORLD_HEIGHT * 2; stripe += 36) {
        context.fillStyle = "#fff0e9";
        context.beginPath();
        context.moveTo(x + 8, stripe);
        context.lineTo(x + 30, stripe);
        context.lineTo(x - 35, stripe + 85);
        context.lineTo(x - 57, stripe + 85);
        context.closePath();
        context.fill();
      }
      context.restore();

      const capY = section.capY;
      context.fillStyle = "#d9e0e6";
      roundedRect(x - 7, capY, OBSTACLE_WIDTH + 14, 19, 4);
      context.fill();
      context.fillStyle = "#e9453a";
      context.fillRect(x - 4, capY + 3, OBSTACLE_WIDTH + 8, 5);
      context.fillStyle = "#263747";
      context.fillRect(x - 4, capY + 12, OBSTACLE_WIDTH + 8, 4);
      context.fillStyle = "rgba(7,10,14,.45)";
      for (let bolt = 0; bolt < 4; bolt += 1) {
        context.beginPath();
        context.arc(x + 8 + bolt * 24, capY + 9, 1.7, 0, Math.PI * 2);
        context.fill();
      }
    }
    context.fillStyle = "rgba(238,244,249,.72)";
    context.font = "800 13px Manrope, sans-serif";
    context.textAlign = "center";
    context.fillText("DRS", x + OBSTACLE_WIDTH / 2, obstacle.gapCenter + 5);
  }

  function drawCar(time) {
    const idleBounce = state === "playing" ? 0 : Math.sin(time * .002) * 7;
    const rotation = state === "playing" ? Math.max(-.34, Math.min(.48, carVelocity / 1050)) : Math.sin(time * .0015) * .025;
    context.save();
    context.translate(CAR_X, carY + idleBounce);
    context.rotate(rotation);

    const flame = context.createLinearGradient(-52, 0, -18, 0);
    flame.addColorStop(0, "rgba(255,188,75,0)");
    flame.addColorStop(.65, "rgba(255,98,54,.75)");
    flame.addColorStop(1, "rgba(255,212,113,.9)");
    context.fillStyle = flame;
    context.beginPath();
    context.moveTo(-43, -4);
    context.lineTo(-62 - Math.sin(time * .03) * 5, 0);
    context.lineTo(-43, 4);
    context.closePath();
    context.fill();

    context.fillStyle = "rgba(0,0,0,.35)";
    context.beginPath();
    context.ellipse(-2, 19, 53, 7, 0, 0, Math.PI * 2);
    context.fill();

    context.fillStyle = "#080b10";
    roundedRect(-34, 8, 19, 23, 6); context.fill();
    roundedRect(24, 8, 19, 23, 6); context.fill();
    context.fillStyle = "#788391";
    context.fillRect(-31, 12, 13, 4);
    context.fillRect(27, 12, 13, 4);
    context.fillRect(-31, 24, 13, 3);
    context.fillRect(27, 24, 13, 3);

    context.fillStyle = "#fa4034";
    context.beginPath();
    context.moveTo(-48, 5);
    context.lineTo(-41, -1);
    context.lineTo(-24, -2);
    context.lineTo(-14, -16);
    context.lineTo(7, -19);
    context.lineTo(22, -8);
    context.lineTo(43, -5);
    context.lineTo(54, 2);
    context.lineTo(40, 6);
    context.lineTo(29, 8);
    context.lineTo(-28, 8);
    context.closePath();
    context.fill();

    context.fillStyle = "#f3f6f8";
    context.beginPath();
    context.moveTo(-48, 2); context.lineTo(-67, 2); context.lineTo(-67, 7); context.lineTo(-45, 8); context.fill();
    context.fillRect(-44, -4, 16, 4);
    context.fillRect(39, -5, 17, 4);

    context.fillStyle = "#ffb7a9";
    context.beginPath();
    context.ellipse(-1, -11, 16, 12, 0, Math.PI, Math.PI * 2);
    context.fill();
    context.fillStyle = "#e8edf2";
    context.beginPath();
    context.arc(0, -15, 9, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = "#243548";
    context.beginPath();
    context.arc(2, -16, 7, Math.PI * 1.08, Math.PI * 1.95);
    context.lineTo(9, -13); context.lineTo(2, -13); context.closePath(); context.fill();
    context.fillStyle = "#ffcc59";
    context.fillRect(-3, -13, 7, 2);

    context.fillStyle = "rgba(255,255,255,.92)";
    context.font = "900 10px Manrope, sans-serif";
    context.textAlign = "center";
    context.fillText("F1", 18, 3);

    context.restore();
  }

  function draw(time) {
    context.clearRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT);
    drawBackground(time);
    for (const obstacle of obstacles) drawGate(obstacle);
    context.fillStyle = "rgba(255,255,255,.16)";
    context.fillRect(CAR_X - 10, 53, 1, WORLD_HEIGHT - 105);
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

  startButton.addEventListener("click", startGame);
  canvas.addEventListener("pointerdown", (event) => {
    if (state !== "playing") return;
    event.preventDefault();
    flap();
  });
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("resize", resize, { passive: true });
  if ("ResizeObserver" in window) new ResizeObserver(resize).observe(wrap);
  document.addEventListener("visibilitychange", () => { previousTime = 0; });
  resetRecordButton.addEventListener("click", () => {
    best = 0;
    saveRecord(best);
    syncScores();
  });

  resize();
  syncScores();
  draw(0);
  animationFrame = window.requestAnimationFrame(frame);

  window.addEventListener("pagehide", () => {
    if (animationFrame) window.cancelAnimationFrame(animationFrame);
  }, { once: true });
})();
