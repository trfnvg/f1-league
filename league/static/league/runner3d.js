import * as THREE from "./vendor/three/three.module.min.js";

(() => {
  "use strict";

  const canvas = document.getElementById("runner3d-canvas");
  const viewport = document.getElementById("runner3d-viewport");
  const overlay = document.getElementById("runner3d-overlay");
  const warning = document.getElementById("runner3d-webgl-warning");
  const startButton = document.getElementById("runner3d-start");
  if (!canvas || !viewport || !overlay || !startButton) return;

  const distanceOutput = document.getElementById("runner3d-distance");
  const bestOutput = document.getElementById("runner3d-best");
  const stateOutput = document.getElementById("runner3d-state");
  const overlayKicker = document.getElementById("runner3d-overlay-kicker");
  const overlayTitle = document.getElementById("runner3d-overlay-title");
  const overlayCopy = document.getElementById("runner3d-overlay-copy");
  const laneCenters = [-3.05, 0, 3.05];
  const playerZ = 5;
  const recordKey = "f1-pit-lane-rush-3d-record-v1";
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let renderer;

  try {
    renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: window.devicePixelRatio <= 1.5,
      powerPreference: "high-performance",
      alpha: false,
    });
  } catch (error) {
    warning.hidden = false;
    overlay.classList.add("is-hidden");
    console.warn("Pit Lane Rush could not initialize WebGL 2.", error);
    return;
  }

  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.65));

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x79b9e9);
  scene.fog = new THREE.Fog(0x8ac0e8, 92, 185);

  const camera = new THREE.PerspectiveCamera(58, 1, 0.1, 220);
  camera.position.set(0, 6.2, 14.5);
  camera.lookAt(0, 1.4, -20);

  scene.add(new THREE.HemisphereLight(0xdaf1ff, 0x43533c, 2.0));
  const sunlight = new THREE.DirectionalLight(0xfff3d9, 2.1);
  sunlight.position.set(-16, 28, 18);
  scene.add(sunlight);

  const backgroundLoader = new THREE.TextureLoader();
  backgroundLoader.load(
    canvas.dataset.backgroundSrc,
    (texture) => {
      texture.colorSpace = THREE.SRGBColorSpace;
      scene.background = texture;
    },
    undefined,
    () => {
      scene.background = new THREE.Color(0x83bde7);
    },
  );

  const materials = {
    grass: new THREE.MeshStandardMaterial({ color: 0x315c3f, roughness: 1 }),
    asphalt: new THREE.MeshStandardMaterial({ color: 0x30353b, roughness: 0.95 }),
    lane: new THREE.MeshStandardMaterial({ color: 0xe8edf0, roughness: 0.8 }),
    curbRed: new THREE.MeshStandardMaterial({ color: 0xd92c2b, roughness: 0.85 }),
    curbWhite: new THREE.MeshStandardMaterial({ color: 0xe7e5dc, roughness: 0.85 }),
    tire: new THREE.MeshStandardMaterial({ color: 0x111519, roughness: 0.9 }),
    tireSide: new THREE.MeshStandardMaterial({ color: 0x343b40, roughness: 0.8 }),
    orange: new THREE.MeshStandardMaterial({ color: 0xff642b, roughness: 0.75 }),
    yellow: new THREE.MeshStandardMaterial({ color: 0xffcf3a, roughness: 0.7 }),
    black: new THREE.MeshStandardMaterial({ color: 0x15191e, roughness: 0.82 }),
    tree: new THREE.MeshStandardMaterial({ color: 0x397752, roughness: 1, flatShading: true }),
    trunk: new THREE.MeshStandardMaterial({ color: 0x78553b, roughness: 1 }),
    red: new THREE.MeshStandardMaterial({ color: 0xd71920, roughness: 0.65, metalness: 0.12 }),
    redLight: new THREE.MeshStandardMaterial({ color: 0xf23b34, roughness: 0.62, metalness: 0.12 }),
    white: new THREE.MeshStandardMaterial({ color: 0xe8edf2, roughness: 0.55, metalness: 0.08 }),
    carbon: new THREE.MeshStandardMaterial({ color: 0x111821, roughness: 0.68, metalness: 0.18 }),
    glass: new THREE.MeshStandardMaterial({ color: 0x7bc8e9, roughness: 0.23, metalness: 0.12 }),
    helmet: new THREE.MeshStandardMaterial({ color: 0xf5c83a, roughness: 0.38, metalness: 0.04 }),
  };

  function addMesh(parent, geometry, material, position, scale, rotation) {
    const mesh = new THREE.Mesh(geometry, material);
    if (position) mesh.position.set(position[0], position[1], position[2]);
    if (scale) mesh.scale.set(scale[0], scale[1], scale[2]);
    if (rotation) mesh.rotation.set(rotation[0], rotation[1], rotation[2]);
    parent.add(mesh);
    return mesh;
  }

  const ground = addMesh(
    scene,
    new THREE.PlaneGeometry(280, 260),
    materials.grass,
    [0, -0.18, -75],
    null,
    [-Math.PI / 2, 0, 0],
  );
  ground.receiveShadow = false;

  addMesh(
    scene,
    new THREE.PlaneGeometry(12.4, 250),
    materials.asphalt,
    [0, -0.07, -70],
    null,
    [-Math.PI / 2, 0, 0],
  );

  const roadMarkings = [];
  const markerGeometry = new THREE.BoxGeometry(0.075, 0.025, 4.2);
  const curbGeometry = new THREE.BoxGeometry(0.52, 0.08, 3.2);
  for (let index = 0; index < 22; index += 1) {
    const z = 8 - index * 10;
    [-1.95, 1.95].forEach((x) => {
      roadMarkings.push(addMesh(scene, markerGeometry, materials.lane, [x, -0.04, z]));
    });
    [-6.03, 6.03].forEach((x, edgeIndex) => {
      const curbMaterial = (index + edgeIndex) % 2 ? materials.curbRed : materials.curbWhite;
      roadMarkings.push(addMesh(scene, curbGeometry, curbMaterial, [x, -0.01, z]));
    });
  }

  const scenery = [];
  const trunkGeometry = new THREE.CylinderGeometry(0.2, 0.32, 3.8, 6);
  const crownGeometry = new THREE.ConeGeometry(1.3, 3.2, 6);
  for (let index = 0; index < 12; index += 1) {
    [-1, 1].forEach((side) => {
      const tree = new THREE.Group();
      addMesh(tree, trunkGeometry, materials.trunk, [0, 1.8, 0]);
      addMesh(tree, crownGeometry, materials.tree, [0, 4.1, 0]);
      tree.position.set(side * (9.2 + (index % 2) * 1.8), -0.15, 7 - index * 18);
      tree.scale.setScalar(0.82 + (index % 3) * 0.14);
      scene.add(tree);
      scenery.push(tree);
    });
  }

  function createCar() {
    const car = new THREE.Group();
    addMesh(car, new THREE.BoxGeometry(1.36, 0.36, 2.1), materials.red, [0, 0.53, 0.18]);
    addMesh(
      car,
      new THREE.ConeGeometry(0.42, 1.55, 5),
      materials.redLight,
      [0, 0.51, -1.22],
      null,
      [-Math.PI / 2, 0, 0],
    );
    addMesh(car, new THREE.BoxGeometry(1.62, 0.13, 0.34), materials.carbon, [0, 0.33, -1.7]);
    addMesh(car, new THREE.BoxGeometry(1.8, 0.12, 0.32), materials.carbon, [0, 0.39, 1.15]);
    addMesh(car, new THREE.BoxGeometry(0.88, 0.12, 0.28), materials.red, [0, 0.51, 1.28]);
    addMesh(
      car,
      new THREE.SphereGeometry(0.38, 10, 7),
      materials.glass,
      [0, 0.9, 0.36],
      [1, 0.72, 0.9],
    );
    addMesh(car, new THREE.SphereGeometry(0.32, 10, 7), materials.helmet, [0, 1.21, 0.35], [1, 1.05, 0.92]);
    addMesh(car, new THREE.BoxGeometry(0.48, 0.055, 0.055), materials.black, [0, 1.19, 0.055]);

    const tireGeometry = new THREE.TorusGeometry(0.32, 0.16, 7, 12);
    [-0.79, 0.79].forEach((x) => {
      [-0.68, 0.87].forEach((z) => {
        addMesh(car, tireGeometry, materials.tire, [x, 0.37, z], null, [0, Math.PI / 2, 0]);
        addMesh(
          car,
          new THREE.CylinderGeometry(0.15, 0.15, 0.04, 8),
          materials.tireSide,
          [x + Math.sign(x) * 0.1, 0.37, z],
          null,
          [0, 0, Math.PI / 2],
        );
      });
    });
    return car;
  }

  const player = createCar();
  player.position.set(0, 0, playerZ);
  scene.add(player);

  const obstacles = [];
  const obstacleConeGeometry = new THREE.ConeGeometry(0.58, 1.48, 5);
  const obstacleBaseGeometry = new THREE.CylinderGeometry(0.66, 0.72, 0.16, 6);
  const barrierBodyGeometry = new THREE.BoxGeometry(2.55, 0.62, 0.48);
  const barrierSupportGeometry = new THREE.BoxGeometry(0.16, 0.92, 0.18);
  const tireObstacleGeometry = new THREE.TorusGeometry(0.48, 0.2, 7, 12);

  function createObstacle(kind, laneIndex, z) {
    const obstacle = new THREE.Group();
    obstacle.userData.kind = kind;
    obstacle.userData.laneIndex = laneIndex;
    obstacle.position.set(laneCenters[laneIndex], 0, z);

    if (kind === "barrier") {
      addMesh(obstacle, barrierBodyGeometry, materials.yellow, [0, 0.64, 0]);
      addMesh(obstacle, barrierSupportGeometry, materials.black, [-1.05, 0.43, 0]);
      addMesh(obstacle, barrierSupportGeometry, materials.black, [1.05, 0.43, 0]);
      for (let segment = 0; segment < 5; segment += 1) {
        addMesh(
          obstacle,
          new THREE.BoxGeometry(0.27, 0.66, 0.5),
          segment % 2 ? materials.black : materials.orange,
          [-0.96 + segment * 0.48, 0.65, -0.015],
        );
      }
    } else if (kind === "tires") {
      [-0.48, 0, 0.48].forEach((x, index) => {
        addMesh(
          obstacle,
          tireObstacleGeometry,
          materials.tire,
          [x, 0.55 + (index % 2) * 0.22, 0],
          null,
          [0, Math.PI / 2, 0],
        );
      });
      addMesh(obstacle, new THREE.BoxGeometry(1.2, 0.12, 0.35), materials.red, [0, 0.17, 0]);
    } else {
      addMesh(obstacle, obstacleBaseGeometry, materials.orange, [0, 0.1, 0]);
      addMesh(obstacle, obstacleConeGeometry, materials.orange, [0, 0.82, 0]);
      addMesh(obstacle, new THREE.CylinderGeometry(0.36, 0.42, 0.1, 5), materials.white, [0, 0.77, 0]);
    }

    scene.add(obstacle);
    obstacles.push(obstacle);
  }

  let gameState = "ready";
  let laneIndex = 1;
  let jumpTime = 0;
  let jumpHeight = 0;
  let distanceTravelled = 0;
  let bestDistance = readBest();
  let spawnClock = 0;
  let spawnIndex = 0;
  let previousFrame = 0;

  function readBest() {
    try {
      const saved = Number(window.localStorage.getItem(recordKey));
      return Number.isFinite(saved) && saved > 0 ? Math.floor(saved) : 0;
    } catch (_) {
      return 0;
    }
  }

  function saveBest() {
    try {
      window.localStorage.setItem(recordKey, String(bestDistance));
    } catch (_) {
      // The current run remains playable if browser storage is unavailable.
    }
  }

  function syncHud() {
    const distance = Math.floor(distanceTravelled);
    distanceOutput.innerHTML = `${distance} <span>м</span>`;
    bestOutput.innerHTML = `${bestDistance} <span>м</span>`;
  }

  function setOverlay(state) {
    overlay.classList.remove("is-hidden");
    if (state === "ready") {
      overlayKicker.textContent = "ПРОТОТИП · ЗАЕЗД 01";
      overlayTitle.textContent = "На трассу?";
      overlayCopy.innerHTML = "← → или A / D — смена полосы<br>Пробел или ↑ — прыжок";
      startButton.innerHTML = 'Старт заезда <span aria-hidden="true">→</span>';
      stateOutput.textContent = "ГОТОВ";
    } else {
      overlayKicker.textContent = "ЗАЕЗД ЗАВЕРШЁН";
      overlayTitle.textContent = "Контакт с барьером";
      overlayCopy.innerHTML = `Дистанция: <strong>${Math.floor(distanceTravelled)} м</strong><br>Пробел — сразу новый заезд`;
      startButton.innerHTML = 'Ещё круг <span aria-hidden="true">↻</span>';
      stateOutput.textContent = "ФИНИШ";
    }
  }

  function startRun() {
    obstacles.forEach((obstacle) => scene.remove(obstacle));
    obstacles.length = 0;
    laneIndex = 1;
    player.position.set(0, 0, playerZ);
    jumpTime = 0;
    jumpHeight = 0;
    distanceTravelled = 0;
    spawnClock = 1.1;
    spawnIndex = 0;
    gameState = "running";
    stateOutput.textContent = "В ЗАЕЗДЕ";
    syncHud();
    overlay.classList.add("is-hidden");
    canvas.focus({ preventScroll: true });
  }

  function finishRun() {
    if (gameState !== "running") return;
    gameState = "over";
    const finalDistance = Math.floor(distanceTravelled);
    if (finalDistance > bestDistance) {
      bestDistance = finalDistance;
      saveBest();
    }
    syncHud();
    setOverlay("over");
  }

  function shiftLane(direction) {
    if (gameState !== "running") return;
    laneIndex = THREE.MathUtils.clamp(laneIndex + direction, 0, laneCenters.length - 1);
  }

  function jump() {
    if (gameState !== "running") return;
    if (jumpTime <= 0) jumpTime = 0.82;
  }

  function spawnWave() {
    const safeLane = Math.floor(Math.random() * laneCenters.length);
    const blockTwo = spawnIndex > 1 && spawnIndex % 3 === 2;
    const lanesToBlock = laneCenters.map((_, index) => index).filter((index) => index !== safeLane);
    if (blockTwo) {
      createObstacle("barrier", lanesToBlock[0], -105);
      createObstacle(Math.random() < 0.5 ? "tires" : "cone", lanesToBlock[1], -105);
    } else {
      const lane = lanesToBlock[Math.floor(Math.random() * lanesToBlock.length)];
      const roll = Math.random();
      createObstacle(roll < 0.36 ? "barrier" : roll < 0.68 ? "tires" : "cone", lane, -105);
    }
    spawnIndex += 1;
  }

  function handleInput(action) {
    if (gameState !== "running") {
      startRun();
      return;
    }
    if (action === "left") shiftLane(-1);
    if (action === "right") shiftLane(1);
    if (action === "jump") jump();
  }

  startButton.addEventListener("click", startRun);
  document.addEventListener("keydown", (event) => {
    const actionByKey = {
      ArrowLeft: "left",
      KeyA: "left",
      ArrowRight: "right",
      KeyD: "right",
      ArrowUp: "jump",
      Space: "jump",
    };
    const action = actionByKey[event.code];
    if (!action) return;
    event.preventDefault();
    handleInput(action);
  });

  document.querySelectorAll("[data-runner3d-action]").forEach((button) => {
    button.addEventListener("click", () => handleInput(button.dataset.runner3dAction));
  });

  let pointerStart = null;
  canvas.addEventListener("pointerdown", (event) => {
    pointerStart = { x: event.clientX, y: event.clientY };
  });
  canvas.addEventListener("pointerup", (event) => {
    if (!pointerStart || gameState !== "running") {
      pointerStart = null;
      return;
    }
    const deltaX = event.clientX - pointerStart.x;
    const deltaY = event.clientY - pointerStart.y;
    pointerStart = null;
    if (Math.max(Math.abs(deltaX), Math.abs(deltaY)) < 24) return;
    if (Math.abs(deltaX) > Math.abs(deltaY)) handleInput(deltaX < 0 ? "left" : "right");
    else if (deltaY < 0) handleInput("jump");
  });
  canvas.addEventListener("pointercancel", () => {
    pointerStart = null;
  });

  function resize() {
    const bounds = viewport.getBoundingClientRect();
    const width = Math.max(1, Math.floor(bounds.width));
    const height = Math.max(1, Math.floor(bounds.height));
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.fov = width < 600 ? 64 : 58;
    camera.updateProjectionMatrix();
  }

  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(viewport);
  window.addEventListener("orientationchange", resize, { passive: true });
  resize();
  syncHud();

  function animate(time) {
    const rawDelta = previousFrame ? (time - previousFrame) / 1000 : 0;
    previousFrame = time;
    const delta = Math.min(rawDelta, 0.045);

    if (gameState === "running") {
      distanceTravelled += delta * (18 + Math.min(19, distanceTravelled * 0.012));
      const worldSpeed = 18 + Math.min(19, distanceTravelled * 0.012);
      spawnClock -= delta;
      if (spawnClock <= 0) {
        spawnWave();
        spawnClock = Math.max(0.78, 1.65 - distanceTravelled * 0.00012) + Math.random() * 0.2;
      }

      if (jumpTime > 0) {
        jumpTime = Math.max(0, jumpTime - delta);
        jumpHeight = Math.sin((1 - jumpTime / 0.82) * Math.PI) * 2.5;
      } else {
        jumpHeight = 0;
      }

      const targetX = laneCenters[laneIndex];
      player.position.x = THREE.MathUtils.damp(player.position.x, targetX, 11, delta);
      player.position.y = jumpHeight;
      player.rotation.z = THREE.MathUtils.damp(player.rotation.z, (targetX - player.position.x) * -0.035, 7, delta);

      roadMarkings.forEach((marking) => {
        marking.position.z += worldSpeed * delta;
        if (marking.position.z > 18) marking.position.z -= 220;
      });
      scenery.forEach((tree) => {
        tree.position.z += worldSpeed * delta;
        if (tree.position.z > 20) tree.position.z -= 216;
      });

      for (let index = obstacles.length - 1; index >= 0; index -= 1) {
        const obstacle = obstacles[index];
        obstacle.position.z += worldSpeed * delta;
        const withinCollisionDepth = Math.abs(obstacle.position.z - playerZ) < 1.25;
        const withinCollisionLane = Math.abs(obstacle.position.x - player.position.x) < 1.2;
        const jumpedBarrier = obstacle.userData.kind === "barrier" && jumpHeight > 1.12;
        if (withinCollisionDepth && withinCollisionLane && !jumpedBarrier) finishRun();
        if (obstacle.position.z > 18) {
          scene.remove(obstacle);
          obstacles.splice(index, 1);
        }
      }

      syncHud();
    } else if (!reducedMotion) {
      player.rotation.y = Math.sin(time * 0.00055) * 0.025;
    }

    renderer.render(scene, camera);
    window.requestAnimationFrame(animate);
  }

  setOverlay("ready");
  window.requestAnimationFrame(animate);
})();
