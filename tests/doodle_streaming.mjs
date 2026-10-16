// Run: CANVAS_MODULE=/path/to/@napi-rs/canvas/index.js node tests/doodle_streaming.mjs
// Native Canvas exercises real sprite decoding/cropping without a browser DOM.
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const canvasLib = require(process.env.CANVAS_MODULE || "@napi-rs/canvas");
const root = fileURLToPath(new URL("../", import.meta.url));
const template = await fs.readFile(path.join(root, "league/templates/arcade_doodle_jump.html"), "utf8");
const originalSource = await fs.readFile(path.join(root, "league/static/league/doodle-jump.js"), "utf8");
assert.ok(template.indexOf('class="doodle-test-controls"') < template.indexOf('class="doodle-machine is-loading"'),
  "Admin testing controls must precede, not overlay, the game window");
const dataset = {};
for (const m of template.matchAll(/data-([\w-]+)-src="\{% static '([^']+)' %\}/g)) {
  dataset[(m[1] + "-src").replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = path.join(root, "league/static", m[2]);
}
const decoded = new Map(await Promise.all(Object.values(dataset).map(async (src) => [src, await canvasLib.loadImage(src)])));
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(predicate) {
  const start = performance.now();
  while (!predicate()) {
    assert.ok(performance.now() - start < 15000, "Timed out waiting for assets");
    await delay(10);
  }
}

async function harness(mobile, failStartup = false) {
  let bounds = { left: 0, top: 0, width: mobile ? 390 : 1000, height: mobile ? 844 : 800 };
  const elements = new Map(), events = new Map(), requests = new Map(), blocked = new Set(), failures = new Set(), calls = [];
  if (failStartup) failures.add(dataset.backgroundJourneySrc);
  const element = (id) => ({ dataset: {}, style: {}, textContent: "", hidden: false,
    classList: { items: new Set(), add(...v) { v.forEach((x) => this.items.add(x)); }, remove(...v) { v.forEach((x) => this.items.delete(x)); }, contains(v) { return this.items.has(v); } },
    addEventListener(type, handler) { events.set(`${id}:${type}`, handler); },
    setAttribute() {}, focus() {}, replaceChildren() {}, append() {}, getBoundingClientRect() { return bounds; } });
  const get = (id) => { if (!elements.has(id)) elements.set(id, element(id)); return elements.get(id); };
  const canvas = Object.assign(canvasLib.createCanvas(1, 1), element("doodle-canvas"));
  canvas.dataset = { ...dataset, adminFlight: "1", startUrl: "/start", finishUrl: "/finish" };
  canvas.closest = () => get("machine");
  elements.set("doodle-canvas", canvas);
  function LoadedImage() {
    return { set src(url) {
      const base = url.split("?")[0];
      requests.set(base, (requests.get(base) || 0) + 1);
      this.native = decoded.get(base);
      const deliver = () => {
        if (blocked.has(base)) { setTimeout(deliver, 5); return; }
        if (failures.has(base)) this.onerror?.(); else this.onload?.();
      };
      queueMicrotask(deliver);
    }, get naturalWidth() { return this.native?.width || 0; }, get naturalHeight() { return this.native?.height || 0; } };
  }
  const document = { getElementById: get, querySelector: () => element("csrf"), body: element("body"), hidden: false,
    createElement: (tag) => tag === "canvas" ? canvasLib.createCanvas(1, 1) : element(tag),
    addEventListener(type, handler) { events.set(`document:${type}`, handler); } };
  const window = { matchMedia: () => ({ matches: mobile }), devicePixelRatio: mobile ? 3 : 2,
    addEventListener() {}, location: { reload() { calls.push("reload"); } } };
  let api;
  const source = originalSource.replace("resolve(img)", "resolve(img.native)")
    .replace(/\}\)\(\);\s*$/, `expose({ art, assetStages, loadStage, streamWorldAssets, draw, drawAntarctica, drawWinterMemory,
      startGame, startTotoBossTest, startAntarcticaPreview, startWinterBiomeTest, update, resize, endGame,
      spawnWinterEncounter, updateWinterEncounter, resetWinterEncounters, winterEnemyGeometry, drawWinterEncounter,
      state:()=>({artReady, assetLoadFailed, mode, elapsed, score:runScore(), waitingForStage, antarctica, antarcticaScene,
        antarcticaArrival, spaceBoss, adminBossTestMode, winterSeamCache, player, cameraY,
        winterEncounter, winterProjectiles, winterSlide, winterWind, platforms, enemies, invulnerableTimer}),
      stage(y, score=0, garage=false){cameraY=y;peakY=startY+score*11;forgottenPaddock=garage;},
      retry(name){assetStages.get(name).retryAt=0;},
      drawWinter(){antarctica=true;drawAntarctica();},
      enemyCase(kind, phase="idle"){resetWinterEncounters();spawnWinterEncounter(kind);winterEncounter.phase=phase;winterEncounter.phaseAge=0;winterEncounter.age=1;},
      tickEnemy(dt){elapsed+=dt;const feet=player.y-player.height/2;updateWinterEncounter(dt,feet,feet);},
      enemyLanding(){const b=winterEnemyGeometry();player.x=b.x;player.y=b.y+b.ry+player.height/2-2;player.vy=-300;
        updateWinterEncounter(0,b.y+b.ry+4,b.y+b.ry-2);},
      aimPenalty(shield=false){invulnerableTimer=shield?2:0;winterProjectiles=[{type:"penalty",x:player.x,y:player.y,vx:0,vy:-112,age:0}];},
      aimGust(){invulnerableTimer=0;winterProjectiles=[{type:"gust",x:player.x,y:player.y,vx:115,vy:0,age:0}];},
      freezeLanding(){const p=platforms.find(p=>!p.broken);p.kind="normal";p.frozenUntil=elapsed+7;
        p.y=cameraY+height*.35;player.x=p.x;player.y=p.y+player.height/2+1;player.vy=-300;winterEncounter=null;winterProjectiles=[];winterEncounterWait=100;},
    });})();`);
  new Function("document", "window", "Image", "localStorage", "requestAnimationFrame", "cancelAnimationFrame", "fetch", "expose", source)(
    document, window, LoadedImage, { getItem: () => null, setItem() {} }, () => 1, () => {},
    async (url) => { calls.push(url); return { ok: true, json: async () => ({ attempt_id: "one" }) }; }, (a) => { api = a; });
  await until(() => api.state().artReady || api.state().assetLoadFailed);
  return { api, requests, blocked, failures, calls, canvas, events,
    resize(w, h) { bounds = { ...bounds, width: w, height: h }; api.resize(); } };
}

for (const mobile of [true, false]) {
  const h = await harness(mobile), a = h.api;
  assert.equal(h.requests.size, 12, "Only startup artwork should load before playing");
  assert.equal(a.art.space, undefined);
  assert.equal(a.art.antarctica, undefined);
  const bytes = (await Promise.all([...h.requests.keys()].map(async (src) => (await fs.stat(src)).size))).reduce((sum, n) => sum + n, 0);
  console.log(`${mobile ? "Mobile" : "Desktop"}: startup ${h.requests.size}/${Object.keys(dataset).length} files, ${(bytes / 1048576).toFixed(2)} MiB`);
  a.startGame(true, { adminTest: true });
  const skyPath = dataset.backgroundCloudSrc;
  h.blocked.add(skyPath);
  a.stage(1300); a.streamWorldAssets();
  assert.ok(h.requests.has(skyPath), "Sky should prefetch before it appears");
  const pendingSky = a.loadStage("sky");
  a.loadStage("sky");
  assert.equal(h.requests.get(skyPath), 1, "Concurrent loads must be deduplicated");
  a.stage(2750);
  const before = a.state();
  a.update(1 / 60);
  assert.equal(a.state().elapsed, before.elapsed);
  assert.equal(a.state().score, before.score);
  assert.equal(a.state().waitingForStage, "sky");
  assert.equal(a.art.cloud, undefined, "Incomplete stages must never be published");
  a.startGame(true, { forceRestart: true, adminTest: true });
  assert.equal(a.state().waitingForStage, null, "Restart must clear the previous chapter wait");
  h.blocked.delete(skyPath);
  assert.equal(await pendingSky, true);
  a.update(1 / 60);
  assert.ok(a.state().elapsed > before.elapsed);
  assert.equal(a.state().waitingForStage, null);
  a.stage(7100); a.streamWorldAssets();
  await a.loadStage("space");
  assert.ok(a.art.spaceBoss && a.art.bossWheel);
  a.stage(20000, 4100); a.streamWorldAssets();
  await a.loadStage("garage");
  assert.ok(a.art.garage && a.art.babyKimi);
  // Failed late assets don't break the already playable starting chapters.
  h.failures.add(dataset.antarcticaSrc);
  a.stage(60000, 6600, true); a.streamWorldAssets();
  assert.equal(await a.loadStage("winter"), false);
  assert.equal(a.art.antarctica, undefined);
  a.stage(70000, 7950, true);
  const timeBeforeRetry = a.state().elapsed;
  a.update(1 / 60);
  assert.equal(a.state().elapsed, timeBeforeRetry);
  h.failures.delete(dataset.antarcticaSrc); a.retry("winter");
  assert.equal(await a.loadStage("winter"), true);
  assert.equal(a.art.walkFrames.length, 8);
  assert.equal(a.art.piranhaFrames.length, 4);
  for (const key of ["winterIceman", "winterStrategist", "winterSteward"]) assert.equal(a.art[key].length, 4);
  await a.startWinterBiomeTest();
  assert.equal(a.state().antarctica, true);
  assert.equal(a.state().adminBossTestMode, true);
  const quotePainter = h.canvas.getContext("2d");
  const originalFill = quotePainter.fill.bind(quotePainter), originalRect = quotePainter.fillRect.bind(quotePainter);
  const originalText = quotePainter.fillText.bind(quotePainter);
  let panels = 0;
  const lettering = [];
  quotePainter.fill = (...args) => { panels += 1; return originalFill(...args); };
  quotePainter.fillRect = (...args) => { panels += 1; return originalRect(...args); };
  quotePainter.fillText = (...args) => { lettering.push({ font: quotePainter.font, color: quotePainter.fillStyle }); return originalText(...args); };
  a.drawWinterMemory(false); a.drawWinterMemory(true);
  assert.equal(panels, 0, "Winter quotation must have no background panel");
  assert.ok(lettering.length >= 3);
  assert.ok(lettering.every(({ font, color }) => parseFloat(font.match(/[\d.]+(?=px)/)[0]) <= 12 && color === "#27385f"));
  quotePainter.fill = originalFill; quotePainter.fillRect = originalRect; quotePainter.fillText = originalText;
  const painter = h.canvas.getContext("2d"), nativeDrawImage = painter.drawImage.bind(painter);
  let drawCalls = 0;
  painter.drawImage = (...args) => { drawCalls += 1; return nativeDrawImage(...args); };
  a.drawWinter(); drawCalls = 0; a.drawWinter();
  assert.ok(drawCalls < 15, `Winter backdrop should reuse its precomposited seam, got ${drawCalls} image draws`);
  for (const [w, height] of mobile ? [[390, 844], [844, 390], [390, 844]] : [[1000, 800], [900, 1000]]) {
    h.resize(w, height); a.draw(); a.drawWinter();
    const seam = a.state().winterSeamCache;
    a.drawWinter(); assert.equal(a.state().winterSeamCache, seam, "Reuse the seam instead of recompositing every frame");
    assert.equal(seam.width, h.canvas.width, "Seam retains native display resolution");
    const pixels = h.canvas.getContext("2d").getImageData(0, 0, h.canvas.width, h.canvas.height).data;
    assert.ok(pixels.some((value, i) => i % 4 !== 3 && value !== pixels[i % 4]), "Winter background must not be blank");
  }
  if (process.env.DOODLE_PREVIEW_DIR) {
    a.draw();
    await fs.writeFile(path.join(process.env.DOODLE_PREVIEW_DIR, `doodle-streaming-${mobile ? "mobile" : "desktop"}.png`), await h.canvas.encode("png"));
  }
  a.endGame();
  await a.startTotoBossTest(); a.update(1 / 60);
  assert.equal(a.state().spaceBoss.phase, "arrival");
  a.endGame();
  assert.deepEqual(h.calls, [], "Admin previews must never save attempts or results");
  // Cropping removes transparent padding, not artwork pixels or resolution.
  for (const pose of [...a.art.enemyVariants, ...a.art.hawkFrames, ...a.art.winterPlatforms]) {
    assert.equal(pose.sx, 0); assert.equal(pose.sy, 0);
    assert.equal(pose.image.width, pose.sw); assert.equal(pose.image.height, pose.sh);
  }
  // The trimmed sprites retain the original source resolution and pixels.
  const original = decoded.get(dataset.enemyVariantsSrc);
  const sectionWidth = Math.round(original.width / 4);
  const reference = canvasLib.createCanvas(sectionWidth, original.height);
  reference.getContext("2d").drawImage(original, 0, 0, sectionWidth, original.height, 0, 0, sectionWidth, original.height);
  const refPixels = reference.getContext("2d").getImageData(0, 0, sectionWidth, original.height).data;
  let left = sectionWidth, top = original.height, right = 0, bottom = 0;
  for (let y = 0; y < original.height; y += 1) for (let x = 0; x < sectionWidth; x += 1) {
    if (refPixels[(y * sectionWidth + x) * 4 + 3] <= 18) continue;
    left = Math.min(left, x); right = Math.max(right, x); top = Math.min(top, y); bottom = Math.max(bottom, y);
  }
  const pose = a.art.enemyVariants[0];
  assert.equal(pose.sw, right - left + 1); assert.equal(pose.sh, bottom - top + 1);
  const expected = canvasLib.createCanvas(pose.sw, pose.sh);
  expected.getContext("2d").drawImage(reference, left, top, pose.sw, pose.sh, 0, 0, pose.sw, pose.sh);
  assert.deepEqual(pose.image.getContext("2d").getImageData(0, 0, pose.sw, pose.sh).data,
    expected.getContext("2d").getImageData(0, 0, pose.sw, pose.sh).data, "Cropping must preserve pixels exactly");
  console.log(`${mobile ? "Mobile" : "Desktop"}: prefetch, pause/resume, failure/retry, atomic publication, previews, resize and full-resolution seam passed`);

  await a.startWinterBiomeTest();
  a.resetWinterEncounters(); a.tickEnemy(7.9);
  assert.equal(a.state().winterEncounter,null,"No new enemies during initial winter grace period");
  a.tickEnemy(.2); assert.ok(a.state().winterEncounter,"Winter enemies must spawn without admin buttons");
  for (const kind of ["iceman", "strategist", "steward"]) {
    a.enemyCase(kind);
    assert.equal(a.spawnWinterEncounter("steward"), false, "Only one encounter can be active");
    a.tickEnemy(1.2); assert.equal(a.state().winterEncounter.phase, "warning");
    assert.equal(a.state().winterProjectiles.length, 0, "No attack before warning finishes");
    a.tickEnemy(1.61); assert.equal(a.state().winterEncounter.phase, "attack");
    if (kind === "strategist") {
      assert.ok(a.state().platforms.some(p=>p.frozenUntil>0), "Ferrari strategist must really freeze a platform");
    } else assert.equal(a.state().winterProjectiles.length, 1);
    a.draw();
    a.tickEnemy(.66); assert.equal(a.state().winterEncounter.phase, "open");
    a.enemyLanding();
    assert.equal(a.state().winterEncounter.phase, "defeated");
    assert.equal(a.state().player.vy, 830);
    assert.equal(a.state().winterProjectiles.length, 0, "Defeat clears lingering attacks");
    a.draw();
    a.tickEnemy(.9); assert.equal(a.state().winterEncounter, null);
    if (process.env.DOODLE_PREVIEW_DIR) {
      a.enemyCase(kind, "warning"); a.draw();
      await fs.writeFile(path.join(process.env.DOODLE_PREVIEW_DIR, `doodle-${kind}-${mobile ? "mobile" : "desktop"}.png`), await h.canvas.encode("png"));
    }
  }
  a.resetWinterEncounters(); a.freezeLanding(); a.update(1/60);
  assert.ok(a.state().winterSlide>0 && a.state().player.vy>0, "Frozen platforms preserve bounce and enable sliding");
  a.resetWinterEncounters(); a.aimGust(); a.tickEnemy(.01);
  assert.ok(a.state().winterWind>0 && a.state().mode==="running", "Wind pushes but does not kill");
  a.aimPenalty(true); a.tickEnemy(.01); assert.equal(a.state().mode,"running", "Rocket shield protects against penalty boards");
  a.aimPenalty(false); a.tickEnemy(.01); assert.equal(a.state().mode,"over", "Penalty boards have real collision");
  await a.startWinterBiomeTest(); a.enemyCase("iceman");
  a.startGame(true,{forceRestart:true,adminTest:true});
  assert.equal(a.state().winterEncounter,null);assert.equal(a.state().winterProjectiles.length,0);
  assert.equal(a.state().winterSlide,0);assert.equal(a.state().winterWind,0);
  assert.equal(a.spawnWinterEncounter("iceman"),false,"Winter encounters must not spawn in other biomes");
  for (const kind of ["iceman", "strategist", "steward"]) {
    await h.events.get(`doodle-winter-${kind}-test:click`)();
    assert.equal(a.state().winterEncounter.type,kind);
    assert.equal(a.state().adminBossTestMode,true);
  }
  assert.deepEqual(h.calls,[],"New admin enemy previews must remain unscored");
  console.log(`${mobile ? "Mobile" : "Desktop"}: winter warnings, attack patterns, stomp, sliding, shield, collisions and restart passed`);
}

// Admin deep links must load their own resources from a cold startup too.
const cold = await harness(true);
await cold.api.startAntarcticaPreview(true);
assert.equal(cold.api.state().antarctica, true);
assert.ok(cold.api.art.garage && cold.api.art.sidFrames.length === 4);
assert.equal(cold.requests.has(dataset.backgroundSpaceSrc), false);
assert.deepEqual(cold.calls, []);
console.log("Cold admin cinematic preview passed; irrelevant chapters were not loaded");
const portal = await harness(true);
await portal.events.get("doodle-portal-test:click")();
assert.ok(portal.api.art.garage);
assert.equal(portal.requests.has(dataset.backgroundSpaceSrc), false);
assert.deepEqual(portal.calls, []);
console.log("Cold admin portal preview passed");
const failed = await harness(true, true);
assert.equal(failed.api.state().artReady, false);
assert.equal(failed.requests.get(dataset.backgroundJourneySrc), 3);
assert.ok(failed.events.get("doodle-start:click"));
failed.events.get("doodle-start:click")({ preventDefault() {} });
assert.deepEqual(failed.calls, ["reload"]);
console.log("Startup failure: bounded image retries and reload action passed");
