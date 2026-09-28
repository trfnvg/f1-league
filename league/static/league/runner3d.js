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
  const bananaOutput = document.getElementById("runner3d-bananas");
  const pitStopOutput = document.getElementById("runner3d-pit-stops");
  const drsLabel = document.getElementById("runner3d-drs-label");
  const drsFill = document.getElementById("runner3d-drs-fill");
  const drsMeter = document.querySelector(".runner3d-drs-meter");
  const radioPanel = document.getElementById("runner3d-radio");
  const radioCopy = document.getElementById("runner3d-radio-copy");
  const boostFlash = document.getElementById("runner3d-boost-flash");
  const mobileBoostButton = document.getElementById("runner3d-mobile-boost");
  const stateOutput = document.getElementById("runner3d-state");
  const overlayKicker = document.getElementById("runner3d-overlay-kicker");
  const overlayTitle = document.getElementById("runner3d-overlay-title");
  const overlayCopy = document.getElementById("runner3d-overlay-copy");
  const laneCenters = [-3.05, 0, 3.05];
  const playerZ = 5;
  const laneNames = ["ЛЕВЫЙ", "ЦЕНТРАЛЬНЫЙ", "ПРАВЫЙ"];
  const recordKey = "f1-box-box-panic-3d-record-v1";
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
    console.warn("Box Box Panic could not initialize WebGL 2.", error);
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
  const bananaCrewTexture = backgroundLoader.load(canvas.dataset.bananaSrc);
  bananaCrewTexture.colorSpace = THREE.SRGBColorSpace;
  const bananaCrewMaterial = new THREE.SpriteMaterial({ map: bananaCrewTexture, transparent: true, depthWrite: false });

  const materials = {
    concrete: new THREE.MeshStandardMaterial({ color: 0xaaa9a2, roughness: 0.96 }),
    apron: new THREE.MeshStandardMaterial({ color: 0x777d80, roughness: 0.96 }),
    asphalt: new THREE.MeshStandardMaterial({ color: 0x30353b, roughness: 0.95 }),
    lane: new THREE.MeshStandardMaterial({ color: 0xe8edf0, roughness: 0.8 }),
    curbRed: new THREE.MeshStandardMaterial({ color: 0xd92c2b, roughness: 0.85 }),
    curbWhite: new THREE.MeshStandardMaterial({ color: 0xe7e5dc, roughness: 0.85 }),
    tire: new THREE.MeshStandardMaterial({ color: 0x111519, roughness: 0.9 }),
    tireSide: new THREE.MeshStandardMaterial({ color: 0x343b40, roughness: 0.8 }),
    orange: new THREE.MeshStandardMaterial({ color: 0xff642b, roughness: 0.75 }),
    yellow: new THREE.MeshStandardMaterial({ color: 0xffcf3a, roughness: 0.7 }),
    black: new THREE.MeshStandardMaterial({ color: 0x15191e, roughness: 0.82 }),
    red: new THREE.MeshStandardMaterial({ color: 0xd71920, roughness: 0.65, metalness: 0.12 }),
    redLight: new THREE.MeshStandardMaterial({ color: 0xf23b34, roughness: 0.62, metalness: 0.12 }),
    mint: new THREE.MeshStandardMaterial({ color: 0x8be0b8, roughness: 0.48, metalness: 0.08 }),
    mintGlow: new THREE.MeshStandardMaterial({ color: 0x76efb2, emissive: 0x278953, emissiveIntensity: 0.8, roughness: 0.42 }),
    pitBoxFloor: new THREE.MeshStandardMaterial({ color: 0x64e6a1, emissive: 0x37b979, emissiveIntensity: 0.68, transparent: true, opacity: 0.44, roughness: 0.48 }),
    banana: new THREE.MeshStandardMaterial({ color: 0xffd642, emissive: 0x765000, emissiveIntensity: 0.12, roughness: 0.42 }),
    bananaTip: new THREE.MeshStandardMaterial({ color: 0x68422a, roughness: 0.95 }),
    garageDark: new THREE.MeshStandardMaterial({ color: 0x1c2834, roughness: 0.82 }),
    garageRed: new THREE.MeshStandardMaterial({ color: 0xb92c2e, roughness: 0.72, metalness: 0.1 }),
    garageBlue: new THREE.MeshStandardMaterial({ color: 0x26718a, roughness: 0.72, metalness: 0.1 }),
    garageMint: new THREE.MeshStandardMaterial({ color: 0x28745e, roughness: 0.72, metalness: 0.1 }),
    garageGold: new THREE.MeshStandardMaterial({ color: 0xc18d36, roughness: 0.72, metalness: 0.1 }),
    led: new THREE.MeshStandardMaterial({ color: 0xffdd82, emissive: 0xff9c34, emissiveIntensity: 1.25, roughness: 0.28 }),
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

  addMesh(
    scene,
    new THREE.PlaneGeometry(280, 260),
    materials.concrete,
    [0, -0.22, -75],
    null,
    [-Math.PI / 2, 0, 0],
  );

  addMesh(scene, new THREE.PlaneGeometry(3.2, 250), materials.apron, [-7.8, -0.16, -70], null, [-Math.PI / 2, 0, 0]);
  addMesh(scene, new THREE.PlaneGeometry(3.2, 250), materials.apron, [7.8, -0.16, -70], null, [-Math.PI / 2, 0, 0]);

  addMesh(
    scene,
    new THREE.PlaneGeometry(12.4, 250),
    materials.asphalt,
    [0, -0.07, -70],
    null,
    [-Math.PI / 2, 0, 0],
  );

  const roadMarkings = [];
  const markerGeometry = new THREE.BoxGeometry(0.065, 0.025, 4.5);
  const curbGeometry = new THREE.BoxGeometry(0.52, 0.08, 3.2);
  const edgeLineGeometry = new THREE.BoxGeometry(0.12, 0.035, 250);
  [-5.72, 5.72].forEach((x) => addMesh(scene, edgeLineGeometry, materials.lane, [x, -0.035, -70]));
  for (let index = 0; index < 28; index += 1) {
    const z = 8 - index * 9;
    [-2.03, 2.03].forEach((x) => {
      const marking = addMesh(scene, markerGeometry, materials.lane, [x, -0.035, z]);
      marking.userData.initialZ = z;
      roadMarkings.push(marking);
    });
    [-6.05, 6.05].forEach((x, edgeIndex) => {
      const curbMaterial = (index + edgeIndex) % 2 ? materials.curbRed : materials.curbWhite;
      const curb = addMesh(scene, curbGeometry, curbMaterial, [x, -0.01, z]);
      curb.userData.initialZ = z;
      roadMarkings.push(curb);
    });
  }

  const pitlaneSegments = [];
  const segmentLength = 34;
  const segmentCount = 8;
  const segmentLoopLength = segmentLength * segmentCount;
  const tireStackGeometry = new THREE.TorusGeometry(0.43, 0.16, 8, 14);
  const garageSlatGeometry = new THREE.BoxGeometry(0.055, 0.045, 11.5);
  const trolleyWheelGeometry = new THREE.CylinderGeometry(0.12, 0.12, 0.08, 8);

  function makeGarageSign(index) {
    const signCanvas = document.createElement("canvas");
    signCanvas.width = 512;
    signCanvas.height = 128;
    const context = signCanvas.getContext("2d");
    context.fillStyle = "#15212d";
    context.fillRect(0, 0, signCanvas.width, signCanvas.height);
    context.fillStyle = ["#f34a43", "#7be1b3", "#e4b24e", "#56b7d2"][index % 4];
    context.fillRect(0, 0, 18, signCanvas.height);
    context.font = "800 62px system-ui, sans-serif";
    context.fillStyle = "#f4f7fa";
    context.textBaseline = "middle";
    context.fillText(`BOX ${String(index + 1).padStart(2, "0")}`, 42, 67);
    const texture = new THREE.CanvasTexture(signCanvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    return new THREE.MeshStandardMaterial({ map: texture, roughness: 0.68, emissive: 0x17212b, emissiveIntensity: 0.2 });
  }

  function addGarageSide(segment, index, side) {
    const accent = [materials.garageRed, materials.garageMint, materials.garageGold, materials.garageBlue][index % 4];
    const inward = side * 6.25;
    addMesh(segment, new THREE.BoxGeometry(5.4, 4.8, segmentLength), materials.garageDark, [side * 9.05, 2.35, 0]);
    addMesh(segment, new THREE.BoxGeometry(0.12, 3.1, 12), accent, [inward, 1.72, 0]);
    addMesh(segment, new THREE.BoxGeometry(0.2, 0.18, 17.8), accent, [side * 6.55, 3.88, 0]);
    addMesh(segment, new THREE.BoxGeometry(0.24, 0.16, segmentLength), materials.garageDark, [side * 9.05, 4.82, 0]);
    const slats = new THREE.InstancedMesh(garageSlatGeometry, materials.white, 9);
    const slatTransform = new THREE.Object3D();
    for (let slat = 0; slat < 9; slat += 1) {
      slatTransform.position.set(0, slat * 0.3, 0);
      slatTransform.updateMatrix();
      slats.setMatrixAt(slat, slatTransform.matrix);
    }
    slats.position.set(inward - side * 0.085, 0.45, 0);
    slats.instanceMatrix.needsUpdate = true;
    segment.add(slats);
    addMesh(segment, new THREE.BoxGeometry(0.09, 0.13, 14.5), materials.led, [side * 6.38, 3.55, 0]);

    const sign = new THREE.Mesh(new THREE.PlaneGeometry(3.6, 0.9), makeGarageSign(index));
    sign.position.set(inward - side * 0.12, 4.35, 0);
    sign.rotation.y = side > 0 ? -Math.PI / 2 : Math.PI / 2;
    segment.add(sign);

    const tireRack = new THREE.InstancedMesh(tireStackGeometry, materials.tire, 4);
    const tireTransform = new THREE.Object3D();
    let tireIndex = 0;
    [-7, 7].forEach((z) => {
      [0, 1].forEach((level) => {
        tireTransform.position.set(side * 6.72, 0.5 + level * 0.38, z);
        tireTransform.rotation.set(0, Math.PI / 2, 0);
        tireTransform.updateMatrix();
        tireRack.setMatrixAt(tireIndex, tireTransform.matrix);
        tireIndex += 1;
      });
    });
    tireRack.instanceMatrix.needsUpdate = true;
    segment.add(tireRack);

    if (index % 4 === 2 && side === 1) {
      const bananaCrew = new THREE.Sprite(bananaCrewMaterial);
      bananaCrew.position.set(side * 6.08, 1.35, -12);
      bananaCrew.scale.set(2.2, 2.5, 1);
      segment.add(bananaCrew);
    }

    const trolley = new THREE.Group();
    addMesh(trolley, new THREE.BoxGeometry(0.8, 0.65, 1.05), index % 2 ? materials.garageBlue : materials.red, [0, 0.55, 0]);
    addMesh(trolley, new THREE.BoxGeometry(0.86, 0.09, 1.12), materials.black, [0, 0.91, 0]);
    const trolleyWheels = new THREE.InstancedMesh(trolleyWheelGeometry, materials.tire, 4);
    const wheelTransform = new THREE.Object3D();
    let wheelIndex = 0;
    [-1, 1].forEach((wheelSide) => {
      [-1, 1].forEach((wheelEnd) => {
        wheelTransform.position.set(wheelSide * 0.37, 0.16, wheelEnd * 0.39);
        wheelTransform.rotation.set(0, 0, Math.PI / 2);
        wheelTransform.updateMatrix();
        trolleyWheels.setMatrixAt(wheelIndex, wheelTransform.matrix);
        wheelIndex += 1;
      });
    });
    trolleyWheels.instanceMatrix.needsUpdate = true;
    trolley.add(trolleyWheels);
    trolley.position.set(side * 6.78, 0, 10);
    segment.add(trolley);
  }

  function createPitlaneSegment(index) {
    const segment = new THREE.Group();
    addGarageSide(segment, index, -1);
    addGarageSide(segment, index, 1);
    if (index % 3 === 1) {
      [-6.4, 6.4].forEach((x) => addMesh(segment, new THREE.BoxGeometry(0.24, 4.9, 0.32), materials.garageDark, [x, 4.35, 0]));
      addMesh(segment, new THREE.BoxGeometry(13.2, 0.34, 0.55), materials.garageDark, [0, 6.65, 0]);
      addMesh(segment, new THREE.BoxGeometry(4.2, 0.72, 0.58), materials.red, [0, 6.62, 0]);
      for (let light = 0; light < 5; light += 1) {
        addMesh(segment, new THREE.SphereGeometry(0.14, 8, 6), light < 3 ? materials.led : materials.mintGlow, [-0.55 + light * 0.28, 6.18, 0.12]);
      }
    }
    segment.position.z = 12 - index * segmentLength;
    scene.add(segment);
    pitlaneSegments.push(segment);
  }

  for (let index = 0; index < segmentCount; index += 1) createPitlaneSegment(index);

  function createCar() {
    const car = new THREE.Group();
    const sections = [
      { z: -2.2, width: 0.14, bottom: 0.29, top: 0.39 },
      { z: -1.78, width: 0.31, bottom: 0.28, top: 0.48 },
      { z: -1.2, width: 0.49, bottom: 0.27, top: 0.58 },
      { z: -0.48, width: 0.63, bottom: 0.27, top: 0.69 },
      { z: 0.35, width: 0.74, bottom: 0.27, top: 0.7 },
      { z: 1.02, width: 0.66, bottom: 0.25, top: 0.63 },
      { z: 1.52, width: 0.43, bottom: 0.25, top: 0.49 },
    ];
    const ring = (section) => [
      [-section.width * 0.62, section.bottom],
      [-section.width, section.bottom + 0.08],
      [-section.width, section.top - 0.15],
      [-section.width * 0.62, section.top],
      [section.width * 0.62, section.top],
      [section.width, section.top - 0.15],
      [section.width, section.bottom + 0.08],
      [section.width * 0.62, section.bottom],
    ];
    const bodyVertices = [];
    const bodyIndices = [];
    sections.forEach((section) => {
      ring(section).forEach(([x, y]) => bodyVertices.push(x, y, section.z));
    });
    for (let sectionIndex = 0; sectionIndex < sections.length - 1; sectionIndex += 1) {
      for (let edge = 0; edge < 8; edge += 1) {
        const nextEdge = (edge + 1) % 8;
        const a = sectionIndex * 8 + edge;
        const b = sectionIndex * 8 + nextEdge;
        const c = (sectionIndex + 1) * 8 + edge;
        const d = (sectionIndex + 1) * 8 + nextEdge;
        bodyIndices.push(a, b, c, b, d, c);
      }
    }
    const bodyGeometry = new THREE.BufferGeometry();
    bodyGeometry.setAttribute("position", new THREE.Float32BufferAttribute(bodyVertices, 3));
    bodyGeometry.setIndex(bodyIndices);
    bodyGeometry.computeVertexNormals();
    const bodyMaterial = materials.red.clone();
    bodyMaterial.side = THREE.DoubleSide;
    addMesh(car, bodyGeometry, bodyMaterial);

    // The center tub and sculpted sidepods make the silhouette read as an open-wheel racer.
    addMesh(car, new THREE.BoxGeometry(0.92, 0.18, 2.55), materials.carbon, [0, 0.29, 0.03]);
    [-1, 1].forEach((side) => {
      addMesh(
        car,
        new THREE.SphereGeometry(1, 10, 7),
        materials.redLight,
        [side * 0.65, 0.47, 0.28],
        [0.43, 0.24, 0.78],
      );
      addMesh(car, new THREE.BoxGeometry(0.055, 0.065, 0.98), materials.mint, [side * 0.91, 0.48, 0.28]);
      addMesh(car, new THREE.BoxGeometry(0.07, 0.42, 0.82), materials.carbon, [side * 0.91, 0.34, -0.02]);
    });

    // Layered front and rear wings, with simple endplates and uprights.
    addMesh(car, new THREE.BoxGeometry(2.72, 0.12, 0.36), materials.carbon, [0, 0.31, -2.08]);
    addMesh(car, new THREE.BoxGeometry(2.42, 0.075, 0.2), materials.redLight, [0, 0.4, -2.13]);
    [-1, 1].forEach((side) => {
      addMesh(car, new THREE.BoxGeometry(0.1, 0.42, 0.42), materials.white, [side * 1.31, 0.48, -2.06]);
      addMesh(car, new THREE.BoxGeometry(0.11, 0.83, 0.16), materials.carbon, [side * 0.43, 0.91, 1.46]);
    });
    addMesh(car, new THREE.BoxGeometry(2.5, 0.14, 0.3), materials.red, [0, 1.34, 1.48]);
    addMesh(car, new THREE.BoxGeometry(2.42, 0.075, 0.26), materials.carbon, [0, 1.48, 1.5]);
    [-1, 1].forEach((side) => {
      addMesh(car, new THREE.BoxGeometry(0.1, 0.5, 0.32), materials.redLight, [side * 1.23, 1.29, 1.48]);
    });

    // Cockpit, driver helmet, and protective halo.
    addMesh(car, new THREE.SphereGeometry(0.42, 10, 7), materials.carbon, [0, 0.81, 0.14], [0.84, 0.54, 0.98]);
    addMesh(car, new THREE.SphereGeometry(0.27, 10, 8), materials.helmet, [0, 1.08, 0.02], [1, 1.08, 1.08]);
    addMesh(car, new THREE.BoxGeometry(0.38, 0.09, 0.06), materials.glass, [0, 1.1, -0.2]);
    const haloCurve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(-0.5, 0.88, 0.42),
      new THREE.Vector3(-0.47, 1.18, 0.2),
      new THREE.Vector3(-0.28, 1.32, -0.02),
      new THREE.Vector3(0, 1.36, -0.06),
      new THREE.Vector3(0.28, 1.32, -0.02),
      new THREE.Vector3(0.47, 1.18, 0.2),
      new THREE.Vector3(0.5, 0.88, 0.42),
    ]);
    addMesh(car, new THREE.TubeGeometry(haloCurve, 16, 0.045, 5, false), materials.white);
    addMesh(car, new THREE.BoxGeometry(0.075, 0.25, 0.075), materials.white, [0, 1.12, -0.38]);

    // Exposed wheels and suspension links.
    const wheels = [];
    const tireGeometry = new THREE.TorusGeometry(0.39, 0.17, 8, 14);
    const hubGeometry = new THREE.CylinderGeometry(0.21, 0.21, 0.055, 10);
    const rodGeometry = new THREE.CylinderGeometry(0.035, 0.05, 1, 5);
    const vectorUp = new THREE.Vector3(0, 1, 0);
    function addSuspensionRod(from, to) {
      const start = new THREE.Vector3(...from);
      const end = new THREE.Vector3(...to);
      const direction = end.clone().sub(start);
      const rod = new THREE.Mesh(rodGeometry, materials.carbon);
      rod.position.copy(start.add(end).multiplyScalar(0.5));
      rod.quaternion.setFromUnitVectors(vectorUp, direction.clone().normalize());
      rod.scale.y = direction.length();
      car.add(rod);
    }

    [-1, 1].forEach((side) => {
      [-1.3, 1.12].forEach((z, axleIndex) => {
        const x = side * (axleIndex === 0 ? 1.08 : 1.0);
        const wheel = addMesh(car, tireGeometry, materials.tire, [x, 0.4, z], null, [0, Math.PI / 2, 0]);
        wheels.push(wheel);
        addMesh(
          car,
          hubGeometry,
          materials.mint,
          [x + side * 0.16, 0.4, z],
          null,
          [0, 0, Math.PI / 2],
        );
        const anchorX = side * 0.64;
        addSuspensionRod([anchorX, 0.33, z - 0.35], [x, 0.4, z]);
        addSuspensionRod([anchorX, 0.46, z + 0.34], [x, 0.4, z]);
      });
    });
    car.userData.wheels = wheels;
    return car;
  }

  const player = createCar();
  player.position.set(0, 0, playerZ);
  scene.add(player);

  const obstacles = [];
  const pickups = [];
  const pitStops = [];
  const obstacleConeGeometry = new THREE.ConeGeometry(0.58, 1.48, 5);
  const obstacleBaseGeometry = new THREE.CylinderGeometry(0.66, 0.72, 0.16, 6);
  const barrierBodyGeometry = new THREE.BoxGeometry(2.55, 0.62, 0.48);
  const barrierSupportGeometry = new THREE.BoxGeometry(0.16, 0.92, 0.18);
  const tireObstacleGeometry = new THREE.TorusGeometry(0.48, 0.2, 7, 12);
  const sharedDynamicGeometries = new Set([
    obstacleConeGeometry,
    obstacleBaseGeometry,
    barrierBodyGeometry,
    barrierSupportGeometry,
    tireObstacleGeometry,
    tireStackGeometry,
  ]);
  const bananaCurve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(-0.38, 0.02, 0),
    new THREE.Vector3(-0.34, 0.42, 0),
    new THREE.Vector3(-0.02, 0.62, 0),
    new THREE.Vector3(0.29, 0.43, 0),
    new THREE.Vector3(0.38, 0.12, 0),
  ]);
  const bananaBodyGeometry = new THREE.TubeGeometry(bananaCurve, 12, 0.12, 7, false);
  const bananaStemGeometry = new THREE.ConeGeometry(0.11, 0.2, 6);
  const bananaTailGeometry = new THREE.ConeGeometry(0.1, 0.16, 6);
  const bananaRingGeometry = new THREE.TorusGeometry(0.59, 0.035, 6, 20);
  sharedDynamicGeometries.add(bananaBodyGeometry);
  sharedDynamicGeometries.add(bananaStemGeometry);
  sharedDynamicGeometries.add(bananaTailGeometry);
  sharedDynamicGeometries.add(bananaRingGeometry);

  function removeDynamicObject(object) {
    scene.remove(object);
    object.traverse((child) => {
      if (child.isMesh && child.geometry && !sharedDynamicGeometries.has(child.geometry)) {
        child.geometry.dispose();
      }
    });
  }
  const worldForward = new THREE.Vector3(1, 0, 0);

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
    } else if (kind === "cart") {
      addMesh(obstacle, new THREE.BoxGeometry(1.15, 0.72, 1.18), materials.red, [0, 0.72, 0]);
      addMesh(obstacle, new THREE.BoxGeometry(1.22, 0.12, 1.26), materials.black, [0, 1.12, 0]);
      addMesh(obstacle, new THREE.BoxGeometry(1.3, 0.08, 0.1), materials.white, [0, 0.82, -0.56]);
      [-1, 1].forEach((side) => {
        [-1, 1].forEach((end) => addMesh(obstacle, new THREE.CylinderGeometry(0.15, 0.15, 0.1, 8), materials.tire, [side * 0.48, 0.18, end * 0.43], null, [0, 0, Math.PI / 2]));
      });
      addMesh(obstacle, new THREE.CylinderGeometry(0.13, 0.15, 0.48, 7), materials.mint, [-0.2, 1.46, 0.12]);
    } else {
      addMesh(obstacle, obstacleBaseGeometry, materials.orange, [0, 0.1, 0]);
      addMesh(obstacle, obstacleConeGeometry, materials.orange, [0, 0.82, 0]);
      addMesh(obstacle, new THREE.CylinderGeometry(0.36, 0.42, 0.1, 5), materials.white, [0, 0.77, 0]);
    }

    scene.add(obstacle);
    obstacles.push(obstacle);
  }

  function createBananaPickup(lane, z) {
    const banana = new THREE.Group();
    addMesh(banana, bananaBodyGeometry, materials.banana);
    addMesh(banana, bananaStemGeometry, materials.bananaTip, [-0.38, 0.03, 0], null, [0, 0, Math.PI / 2]);
    addMesh(banana, bananaTailGeometry, materials.bananaTip, [0.38, 0.12, 0], null, [0, 0, -Math.PI / 2]);
    addMesh(banana, bananaRingGeometry, materials.mintGlow, [0, 0.14, -0.03], null, [Math.PI / 2, 0, 0]);
    banana.position.set(laneCenters[lane], 0.95, z);
    banana.userData.kind = "banana";
    banana.userData.lane = lane;
    scene.add(banana);
    pickups.push(banana);
    return banana;
  }

  function createPitBox(lane, z) {
    const box = new THREE.Group();
    addMesh(box, new THREE.BoxGeometry(2.65, 0.055, 8.6), materials.pitBoxFloor, [0, 0.035, 0]);
    [-1.14, 1.14].forEach((x) => addMesh(box, new THREE.BoxGeometry(0.1, 0.09, 8.3), materials.mintGlow, [x, 0.08, 0]));
    [-3.25, 0, 3.25].forEach((zMark) => addMesh(box, new THREE.BoxGeometry(2.12, 0.035, 0.12), materials.white, [0, 0.08, zMark]));
    [-1, 1].forEach((side) => {
      addMesh(box, new THREE.BoxGeometry(0.22, 1.3, 0.22), materials.garageDark, [side * 1.48, 0.68, -3.55]);
      addMesh(box, new THREE.SphereGeometry(0.2, 8, 6), materials.mintGlow, [side * 1.48, 1.43, -3.55]);
    });
    addMesh(box, new THREE.BoxGeometry(2.85, 0.72, 0.2), materials.garageDark, [0, 2.05, -3.55]);
    addMesh(box, new THREE.BoxGeometry(0.08, 0.44, 0.08), materials.mintGlow, [-0.85, 2.06, -3.42]);
    addMesh(box, new THREE.BoxGeometry(0.72, 0.08, 0.08), materials.mintGlow, [-0.53, 2.06, -3.42]);
    addMesh(box, new THREE.BoxGeometry(0.08, 0.44, 0.08), materials.mintGlow, [-0.2, 2.06, -3.42]);
    addMesh(box, new THREE.BoxGeometry(0.08, 0.44, 0.08), materials.mintGlow, [0.18, 2.06, -3.42]);
    addMesh(box, new THREE.BoxGeometry(0.72, 0.08, 0.08), materials.mintGlow, [0.5, 2.06, -3.42]);
    addMesh(box, new THREE.BoxGeometry(0.08, 0.44, 0.08), materials.mintGlow, [0.83, 2.06, -3.42]);
    box.position.set(laneCenters[lane], 0, z);
    box.userData.kind = "pitstop";
    box.userData.lane = lane;
    box.userData.resolved = false;
    scene.add(box);
    pitStops.push(box);
    return box;
  }

  let gameState = "ready";
  let laneIndex = 1;
  let jumpTime = 0;
  let jumpHeight = 0;
  let distanceTravelled = 0;
  let bestScore = readBest();
  let bananasCollected = 0;
  let cleanPitStops = 0;
  let drsCharge = 0;
  let boostTime = 0;
  let radioTimer = 0;
  let radioPriority = 0;
  let spawnClock = 0;
  let spawnIndex = 0;
  let nextPitStopDistance = 430;
  let nextRadioDistance = 760;
  let activePitStop = null;
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
      window.localStorage.setItem(recordKey, String(bestScore));
    } catch (_) {
      // The current run remains playable if browser storage is unavailable.
    }
  }

  function currentScore() {
    return Math.floor(distanceTravelled + bananasCollected * 75 + cleanPitStops * 250);
  }

  function syncHud() {
    const distance = Math.floor(distanceTravelled);
    distanceOutput.innerHTML = `${distance} <span>м</span>`;
    document.getElementById("runner3d-score").textContent = currentScore().toLocaleString("ru-RU");
    bestOutput.textContent = bestScore.toLocaleString("ru-RU");
    bananaOutput.textContent = String(bananasCollected);
    pitStopOutput.textContent = String(cleanPitStops);
    drsFill.style.width = `${drsCharge}%`;
    drsMeter.classList.toggle("is-ready", drsCharge >= 100);
    mobileBoostButton.classList.toggle("is-ready", drsCharge >= 100);
    mobileBoostButton.disabled = drsCharge < 100 || boostTime > 0;
    drsLabel.textContent = boostTime > 0
      ? `DRS активен · ${boostTime.toFixed(1)} с`
      : drsCharge >= 100
        ? "Готов! Shift / X"
        : `Заряд ${Math.floor(drsCharge)}%`;
  }

  function showRadio(message, duration = 3.2, priority = 1) {
    if (radioTimer > 0 && priority < radioPriority) return;
    radioCopy.textContent = message;
    radioPanel.hidden = false;
    radioPanel.classList.remove("is-visible");
    window.requestAnimationFrame(() => radioPanel.classList.add("is-visible"));
    radioTimer = duration;
    radioPriority = priority;
  }

  function setOverlay(state) {
    overlay.classList.remove("is-hidden");
    if (state === "ready") {
      overlayKicker.textContent = "БЕСКОНЕЧНЫЙ ПИТ-ЛЕЙН · ТЕСТ ДЛЯ АДМИНА";
      overlayTitle.textContent = "BOX BOX!";
      overlayCopy.innerHTML = "← → — выбирай полосу и собирай бананы<br>5 бананов заряжают DRS · Shift / X — ускорение<br>↑ / Пробел — перепрыгнуть барьер · попадай в зелёный бокс";
      startButton.innerHTML = 'Выезжаем <span aria-hidden="true">→</span>';
      stateOutput.textContent = "ГОТОВ";
    } else {
      overlayKicker.textContent = "ПИТ-ЛЕЙН ЗАПОМНИТ ЭТОТ ЗАЕЗД";
      overlayTitle.textContent = "i am stupid...";
      overlayCopy.innerHTML = `Счёт: <strong>${currentScore().toLocaleString("ru-RU")}</strong> · дистанция: <strong>${Math.floor(distanceTravelled)} м</strong><br>Бананы: <strong>${bananasCollected}</strong> · чистые боксы: <strong>${cleanPitStops}</strong><br>Пробел — новая попытка`;
      startButton.innerHTML = 'Повторить заезд <span aria-hidden="true">↻</span>';
      stateOutput.textContent = "ФИНИШ";
    }
  }

  function startRun() {
    obstacles.forEach(removeDynamicObject);
    obstacles.length = 0;
    pickups.forEach(removeDynamicObject);
    pickups.length = 0;
    pitStops.forEach(removeDynamicObject);
    pitStops.length = 0;
    pitlaneSegments.forEach((segment, index) => {
      segment.position.z = 12 - index * segmentLength;
    });
    roadMarkings.forEach((marking) => {
      marking.position.z = marking.userData.initialZ;
    });
    laneIndex = 1;
    player.position.set(0, 0, playerZ);
    player.rotation.set(0, 0, 0);
    jumpTime = 0;
    jumpHeight = 0;
    distanceTravelled = 0;
    bananasCollected = 0;
    cleanPitStops = 0;
    drsCharge = 0;
    boostTime = 0;
    radioTimer = 0;
    radioPriority = 0;
    radioPanel.hidden = true;
    boostFlash.classList.remove("is-boosting");
    activePitStop = null;
    nextPitStopDistance = 390 + Math.random() * 110;
    nextRadioDistance = 720 + Math.random() * 180;
    spawnClock = 0.85;
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
    const finalScore = currentScore();
    if (finalScore > bestScore) {
      bestScore = finalScore;
      saveBest();
    }
    boostFlash.classList.remove("is-boosting");
    radioPanel.hidden = true;
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

  function activateDrs() {
    if (gameState !== "running" || boostTime > 0) return;
    if (drsCharge < 100) {
      showRadio("DRS ещё не готов. Срочно ищи бананы!", 2.1);
      return;
    }
    drsCharge = 0;
    boostTime = 3.2;
    boostFlash.classList.add("is-boosting");
    showRadio("DRS открыт. Если что — так и было задумано.", 2.7);
    syncHud();
  }

  function spawnWave() {
    const safeLane = activePitStop
      ? activePitStop.userData.lane
      : Math.floor(Math.random() * laneCenters.length);
    const blockTwo = spawnIndex > 1 && spawnIndex % 4 === 3;
    const lanesToBlock = laneCenters.map((_, index) => index).filter((index) => index !== safeLane);
    const hazardZ = -94 - Math.random() * 8;
    if (blockTwo) {
      createObstacle("barrier", lanesToBlock[0], hazardZ);
      const secondHazard = Math.random();
      createObstacle(secondHazard < 0.36 ? "cart" : secondHazard < 0.68 ? "tires" : "cone", lanesToBlock[1], hazardZ);
    } else {
      const lane = lanesToBlock[Math.floor(Math.random() * lanesToBlock.length)];
      const roll = Math.random();
      createObstacle(roll < 0.36 ? "barrier" : roll < 0.64 ? "tires" : roll < 0.84 ? "cone" : "cart", lane, hazardZ);
    }

    // A short banana line creates an optional risky route and charges a DRS burst.
    const rewardLane = Math.random() < 0.52
      ? safeLane
      : Math.floor(Math.random() * laneCenters.length);
    for (let index = 0; index < 3; index += 1) {
      createBananaPickup(rewardLane, hazardZ - 12 - index * 2.25);
    }
    spawnIndex += 1;
  }

  function preparePitStop() {
    if (activePitStop || distanceTravelled < nextPitStopDistance - 94) return;
    const targetLane = Math.floor(Math.random() * laneCenters.length);
    const remaining = Math.max(2, nextPitStopDistance - distanceTravelled);
    activePitStop = createPitBox(targetLane, playerZ - remaining);
    showRadio(`BOX, BOX! Заезжай в ${laneNames[targetLane]} бокс!`, 4.2, 2);
  }

  function completePitStop(pitStop) {
    if (pitStop.userData.resolved) return;
    pitStop.userData.resolved = true;
    const targetX = laneCenters[pitStop.userData.lane];
    const madeIt = laneIndex === pitStop.userData.lane && Math.abs(player.position.x - targetX) < 1.35;
    if (madeIt) {
      cleanPitStops += 1;
      drsCharge = 100;
      showRadio("Чистый стоп! Полный DRS. Пит-бригада отрицает, что уронила колесо.", 4, 2);
    } else {
      showRadio("Бокс пропущен. Стратегия говорит, что так и планировала.", 3.1, 2);
    }
    activePitStop = null;
    nextPitStopDistance = distanceTravelled + 480 + Math.random() * 240;
    syncHud();
  }

  function handleInput(action) {
    if (gameState !== "running") {
      startRun();
      return;
    }
    if (action === "left") shiftLane(-1);
    if (action === "right") shiftLane(1);
    if (action === "jump") jump();
    if (action === "boost") activateDrs();
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
      ShiftLeft: "boost",
      ShiftRight: "boost",
      KeyX: "boost",
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
    camera.fov = width < 600 ? 70 : 58;
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
      if (boostTime > 0) {
        boostTime = Math.max(0, boostTime - delta);
        if (boostTime === 0) boostFlash.classList.remove("is-boosting");
      }
      if (radioTimer > 0) {
        radioTimer = Math.max(0, radioTimer - delta);
        if (radioTimer === 0) {
          radioPriority = 0;
          radioPanel.classList.remove("is-visible");
          radioPanel.hidden = true;
        }
      }

      const baseSpeed = 19 + Math.min(20, distanceTravelled * 0.0038);
      const worldSpeed = baseSpeed * (boostTime > 0 ? 1.38 : 1);
      distanceTravelled += delta * worldSpeed;
      preparePitStop();
      spawnClock -= delta;
      if (spawnClock <= 0) {
        spawnWave();
        spawnClock = Math.max(1.08, 1.75 - distanceTravelled * 0.00007) + Math.random() * 0.24;
      }

      if (distanceTravelled >= nextRadioDistance) {
        const radioLines = [
          "Копируй. Банан — не официальная часть аэродинамики.",
          "План B: держаться подальше от плана A.",
          "Шины в порядке. Кто-то проверял? Уже не важно.",
          "Бокс, бокс! Шутка. Пока просто не врежься.",
        ];
        showRadio(radioLines[Math.floor(Math.random() * radioLines.length)], 3.4);
        nextRadioDistance += 680 + Math.random() * 260;
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
      player.userData.wheels.forEach((wheel) => {
        wheel.rotateOnWorldAxis(worldForward, delta * worldSpeed * 0.16);
      });

      roadMarkings.forEach((marking) => {
        marking.position.z += worldSpeed * delta;
        if (marking.position.z > 18) marking.position.z -= 252;
      });
      pitlaneSegments.forEach((segment) => {
        segment.position.z += worldSpeed * delta;
        if (segment.position.z > 23) segment.position.z -= segmentLoopLength;
      });

      for (let index = obstacles.length - 1; index >= 0; index -= 1) {
        const obstacle = obstacles[index];
        obstacle.position.z += worldSpeed * delta;
        const withinCollisionDepth = Math.abs(obstacle.position.z - playerZ) < 1.4;
        const withinCollisionLane = Math.abs(obstacle.position.x - player.position.x) < 1.35;
        const jumpedBarrier = obstacle.userData.kind === "barrier" && jumpHeight > 1.12;
        if (withinCollisionDepth && withinCollisionLane && !jumpedBarrier) finishRun();
        if (obstacle.position.z > 18) {
          removeDynamicObject(obstacle);
          obstacles.splice(index, 1);
        }
        if (gameState !== "running") break;
      }

      if (gameState === "running") {
        for (let index = pickups.length - 1; index >= 0; index -= 1) {
          const pickup = pickups[index];
          pickup.position.z += worldSpeed * delta;
          pickup.rotation.y += delta * 1.7;
          pickup.position.y = 0.95 + Math.sin(time * 0.004 + index) * 0.08;
          const canCollect = Math.abs(pickup.position.z - playerZ) < 1.65
            && Math.abs(pickup.position.x - player.position.x) < 1.35;
          if (canCollect) {
            bananasCollected += 1;
            drsCharge = Math.min(100, drsCharge + 20);
            const charged = drsCharge >= 100;
            showRadio(charged ? "DRS заряжен на 100%! Жми Shift / X, когда понадобится." : `Банан в кармане. DRS заряжен на ${drsCharge}%.`, charged ? 3.5 : 2.1);
            removeDynamicObject(pickup);
            pickups.splice(index, 1);
            syncHud();
          } else if (pickup.position.z > 18) {
            removeDynamicObject(pickup);
            pickups.splice(index, 1);
          }
        }

        for (let index = pitStops.length - 1; index >= 0; index -= 1) {
          const pitStop = pitStops[index];
          pitStop.position.z += worldSpeed * delta;
          if (!pitStop.userData.resolved && Math.abs(pitStop.position.z - playerZ) < 2.25) {
            completePitStop(pitStop);
          }
          if (pitStop.position.z > 20) {
            if (!pitStop.userData.resolved) completePitStop(pitStop);
            removeDynamicObject(pitStop);
            pitStops.splice(index, 1);
          }
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
