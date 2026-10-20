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
    assert.ok(performance.now() - start < 45000, "Timed out waiting for assets");
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
      rasterSprite, landingPlatform, alphaMask, spriteOverlapsEllipse, sweptHazardContact,
      updateSkyDetails, drawSkyDucks, drawTotoCloud, cleanSpriteContour, drawCloud,
      updateHawks, spriteTopAtX, spriteSize, spriteLanding, movingLanding, collideWithEnemy, updatePortal,
      spawnSummitCommentator, updateSummitCommentator, drawSummitCommentator,
      decorateSummitPlatform, updateSummitGoats, extendWorld, summitPlatformGap, choosePlatformX,
      spawnSummitEnemy, updateSummitEnemies, drawSummitEnemies,
      sidArenaHeight, sidBossGeometry, summitEnemyPose,
      setBossWarning, extendBossRefuge, updateSpaceBoss, followPlayerCamera,
      startBathBossTest, beginBathJourney, updateBathBoss, bathGeometry, buildBathArena,
      cloudTextures:()=>sceneryCache.get(art.cloud),
      skyState:()=>({skyFlock,totoCloud,hawks}),
      duckLanding(){const pos=skyDuckPosition(0),top=pos.y+7;
        player.x=pos.x;player.y=top+player.height/2-2;player.vy=-300;
        collideSkyDucks(top+3,top-2,1/60,pos.x);},
      cacheSize(sprite){return rasterCache.get(sprite)?.size || 0;},
      spawnWinterEncounter, updateWinterEncounter, resetWinterEncounters, winterEnemyGeometry, drawWinterEncounter,
      startSpaceEventTest, spawnSpaceEncounter, clearSpaceEncounter, updateSpaceEvents, collideWithSpaceEvents, drawSpaceEvents,
      startSidBossTest, beginSidBoss, updateSidBoss, collideSidShots, drawSidBoss, enterSummit, drawSummitBackdrop,
      state:()=>({artReady, assetLoadFailed, mode, elapsed, score:runScore(), waitingForStage, antarctica, antarcticaScene,
        antarcticaArrival, spaceBoss, adminBossTestMode, winterSeamCache, player, cameraY, forgottenPaddock,
        winterEncounter, winterProjectiles, winterSlide, winterWind, platforms, enemies, invulnerableTimer,
        spaceEncounter, spacePitHold, softBootJumps, width, height, sidBoss, sidBossCleared, summit, peakY, summitCommentator, hazards, bossShots,
        summitEntryY, summitGoatNextY, summitCommentatorNextY, summitEncounter, summitShots, summitEnemyNextY, visibleWorldHeight,
        bathBoss,bathBossCleared}),
      stage(y, score=0, garage=false){cameraY=y;peakY=startY+score*11;forgottenPaddock=garage;},
      retry(name){assetStages.get(name).retryAt=0;},
      drawWinter(){antarctica=true;drawAntarctica();},
      enemyCase(kind, phase="idle"){resetWinterEncounters();spawnWinterEncounter(kind);winterEncounter.y=cameraY+height*.65;winterEncounter.phase=phase;winterEncounter.phaseAge=0;winterEncounter.age=1;
        if(kind==="strategist"){player.y=cameraY+height*.4;addPlatform(cameraY+height*.6,width*.5,"normal");}},
      cameraAt(y){cameraY=y;},
      tickEnemy(dt){elapsed+=dt;const feet=player.y-player.height/2;updateWinterEncounter(dt,feet,feet);},
      enemyLanding(){const b=winterEnemyGeometry();player.x=b.x;player.y=b.y+b.ry+player.height/2-2;player.vy=-300;
        updateWinterEncounter(0,b.y+b.ry+4,b.y+b.ry-2);},
      aimPenalty(shield=false){invulnerableTimer=shield?2:0;winterProjectiles=[{type:"penalty",x:player.x,y:player.y,vx:0,vy:-112,age:0}];},
      aimGust(){invulnerableTimer=0;winterProjectiles=[{type:"gust",x:player.x,y:player.y,vx:115,vy:0,age:0}];},
      freezeLanding(){const p=platforms.find(p=>!p.broken);p.kind="normal";p.frozenUntil=elapsed+7;
        p.y=cameraY+height*.35;player.x=p.x;player.y=p.y+player.height/2+1;player.vy=-300;winterEncounter=null;winterProjectiles=[];winterEncounterWait=100;},
      spaceLanding(){const e=spaceEncounter;let x=e.x,top=e.y;
        if(e.type==="pitstop"){const d=spacePitDeck(e);x=d.x;top=d.y;}
        if(e.type==="alonso"){e.x=width*.5;x=e.x;const s=art.spaceAlonso[0];top=spriteTopAtX(s,e.x,e.y,150,spriteSize(s,150),x);}
        if(e.type==="carbon"){e.age=2;const d=e.debris[0];x=d.x;const s=art.spaceCarbon[d.index];top=spriteTopAtX(s,d.x,d.y,72,spriteSize(s,72),x);}
        player.x=x;player.y=top+player.height/2-2;player.vy=-300;
        collideWithSpaceEvents(top+4,top-2,0);},
      hitCarbon(shield=false){const e=spaceEncounter;e.age=2;const d=e.debris.find(d=>d.index>=2);
        for(const other of e.debris)other.dead=other!==d;
        d.x=player.x;d.y=player.y;player.vy=0;invulnerableTimer=shield?2:0;
        const feet=player.y-player.height/2;collideWithSpaceEvents(feet,feet,1/60);},
      forceBoss(){peakY=startY+3500*11;updateSpaceBoss(1/60);},
      seedSpaceObjects(){
        const enemy={x:width*.1,baseX:width*.1,y:cameraY+height*.8,variant:0,phase:0,dead:false};
        const hazard={x:width*.9,y:cameraY+height*.8,spriteIndex:6,size:30,speed:90,dead:false};
        enemies.push(enemy);hazards.push(hazard);return {enemy,hazard};
      },
      portal(){beginPortal();},
      setSpaceAge(age){spaceEncounter.age=age;},
      peakScore(n){peakY=startY+(n-frags*30-marshalBonus-bossBonus)*11;},
      bossShield(){invulnerableTimer=100;},
      expireShield(){invulnerableTimer=0;},
      reflectSidCan(){const shot={kind:"can",x:width*.5,y:cameraY+height*.4,age:1,vy:-90,reflected:false};sidBoss.shots=[shot];
        const top=shot.y+17;player.x=shot.x;player.y=top+player.height/2-2;player.vy=-300;
        collideSidShots(0,top+3,top-2);return shot;},
      impactSidCan(){for(let i=0;i<180&&sidBoss.shots.length;i++){const feet=player.y-player.height/2;collideSidShots(1/60,feet,feet);}},
      sidHazard(kind,shield=false){const shot={kind,x:player.x,y:player.y,age:1,vy:-100,reflected:false};sidBoss.shots=[shot];invulnerableTimer=shield?2:0;player.vy=10;
        const feet=player.y-player.height/2;collideSidShots(1/60,feet,feet);},
      sidPose(phase,timer){sidBoss.phase=phase;sidBoss.timer=timer;draw();},
    });})();`);
  new Function("document", "window", "Image", "localStorage", "requestAnimationFrame", "cancelAnimationFrame", "fetch", "expose", source)(
    document, window, LoadedImage, { getItem: () => null, setItem() {} }, () => 1, () => {},
    async (url) => { calls.push(url); return { ok: true, json: async () => ({ attempt_id: "one" }) }; }, (a) => { api = a; });
  await until(() => api.state().artReady || api.state().assetLoadFailed);
  return { api, requests, blocked, failures, calls, canvas, events,
    setPixelRatio(value){window.devicePixelRatio=value;api.resize();},
    resize(w, h) { bounds = { ...bounds, width: w, height: h }; api.resize(); } };
}

for (const mobile of [true, false]) {
  const h = await harness(mobile), a = h.api;
  assert.equal(h.requests.size, 12, "Only startup artwork should load before playing");
  assert.equal(a.art.space, undefined);
  assert.equal(a.art.antarctica, undefined);
  if(!mobile){
    h.setPixelRatio(1);
    assert.equal(h.canvas.width,2000,"A standard-density desktop should render at 2x CSS width");
    h.setPixelRatio(2);
  }
  const bytes = (await Promise.all([...h.requests.keys()].map(async (src) => (await fs.stat(src)).size))).reduce((sum, n) => sum + n, 0);
  console.log(`${mobile ? "Mobile" : "Desktop"}: startup ${h.requests.size}/${Object.keys(dataset).length} files, ${(bytes / 1048576).toFixed(2)} MiB`);
  a.startGame(true, { adminTest: true });
  // Fast descents must hit the first surface in space, not array order.
  const landingState = a.state();
  const savedPlatforms = [...landingState.platforms];
  const platform = (y, x=100) => ({y, x, hitboxWidth:20, broken:false});
  const low = platform(110), high = platform(130);
  landingState.platforms.splice(0, landingState.platforms.length, low, high);
  assert.equal(a.landingPlatform(140, 100, 100, 100), high);
  assert.equal(a.landingPlatform(100, 140, 100, 100), null, "Ascending feet cannot land");
  landingState.platforms.splice(0, landingState.platforms.length, platform(120));
  assert.ok(a.landingPlatform(140, 100, 80, 120), "Use horizontal position at contact time");
  assert.equal(a.landingPlatform(140,100,landingState.width+5,-5),null,"Screen wrap must not cross middle platforms");
  const moving = {...platform(120,120), previousX:80};
  landingState.platforms.splice(0, landingState.platforms.length, moving);
  assert.equal(a.landingPlatform(140,100,100,100),moving,"Moving platform uses position at contact time");
  landingState.platforms.splice(0, landingState.platforms.length, ...savedPlatforms);
  const pixels = new Uint8ClampedArray(32*32*4);
  for(let y=8;y<24;y++) for(let x=8;x<24;x++) pixels[(y*32+x)*4+3]=255;
  const dirtyContour=pixels.slice();
  dirtyContour[(2*32+2)*4+3]=255;
  dirtyContour[(3*32+30)*4+3]=12;
  a.cleanSpriteContour(dirtyContour,32,32);
  assert.equal(dirtyContour[(2*32+2)*4+3],0,"Detached opaque specks must disappear");
  assert.equal(dirtyContour[(3*32+30)*4+3],0,"Detached faint specks must disappear");
  assert.equal(dirtyContour[(12*32+12)*4+3],255,"Main wheel pixels stay unchanged");
  const masked = {mask:a.alphaMask(pixels,32,0,0,32,32)};
  assert.equal(a.spriteOverlapsEllipse(masked,100,100,32,32,86,100,2,2),false,"Transparent margins cannot kill");
  assert.equal(a.spriteOverlapsEllipse(masked,100,100,32,32,100,100,2,2),true);
  const savedPlayer = {...landingState.player};
  Object.assign(landingState.player,{x:100,y:60,width:8,height:8});
  assert.equal(a.sweptHazardContact({sprite:masked,x:100,y:100,width:32,height:32},100,100,140),true,
    "A fast player crossing a hazard cannot tunnel between frames");
  assert.equal(a.sweptHazardContact({sprite:masked,x:140,y:100,width:32,height:32},100,100,140),false,
    "Swept collision must preserve a safe near miss");
  Object.assign(landingState.player,savedPlayer);
  const cachePose = a.art.heroFrames[0];
  for(let i=0;i<120;i++) a.rasterSprite(cachePose,100+i,150+i);
  assert.ok(a.cacheSize(cachePose)<=9,"Animated sizes must not churn texture allocations");
  const originalTexture=a.rasterSprite(cachePose,800,900);
  assert.equal(originalTexture.width,cachePose.sw,"Fallback preserves original source resolution");
  assert.equal(originalTexture,a.rasterSprite(cachePose,801,901),"Variable sizes reuse original texture");
  a.resize();
  console.log(`${mobile ? "Mobile" : "Desktop"}: swept landings, moving platforms, wrap, alpha contours and bounded animation cache passed`);
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
  a.stage(6500);
  for(let i=0;i<480;i++)a.updateSkyDetails(1/60);
  assert.equal(a.skyState().skyFlock.birds.length,5);
  assert.ok(a.skyState().totoCloud,"Toto should assemble only in the blue sky");
  assert.ok(a.skyState().skyFlock.birds.every(b=>!("number" in b)),"The flock has no racing numbers");
  const existingHawk={x:100,previousX:100,y:6600,size:50,direction:1,speed:150,flapElapsed:0};
  a.skyState().hawks.push(existingHawk);
  a.updateSkyDetails(1/60);
  assert.ok(a.skyState().hawks.includes(existingHawk),"Sky details must not erase existing enemies");
  a.draw();
  const cloudTextures = a.cloudTextures();
  assert.ok(cloudTextures?.size > 0, "Visible clouds have display-resolution textures");
  const cachedClouds = [...cloudTextures.values()];
  for (let i = 0; i < 60; i++) a.draw();
  assert.deepEqual([...a.cloudTextures().values()], cachedClouds,
    "Steady sky rendering must reuse textures without frame-by-frame allocations");
  const count = cloudTextures.size;
  a.drawCloud(0, -10000, 123, 45);
  assert.equal(cloudTextures.size, count, "Offscreen scenery must not allocate textures");
  a.draw();
  if(process.env.DOODLE_PREVIEW_DIR)await fs.writeFile(path.join(process.env.DOODLE_PREVIEW_DIR,`doodle-sky-ducks-${mobile?"mobile":"desktop"}.png`),await h.canvas.encode("png"));
  a.duckLanding();
  assert.equal(a.state().player.vy,820,"Duck backs should bounce the hero");
  assert.equal(a.skyState().skyFlock.birds[0].used,true,"One duck cannot provide unlimited boosts");
  a.stage(13000);a.updateSkyDetails(1/60);
  assert.equal(a.skyState().skyFlock,null,"Flock must leave when entering space");
  assert.equal(a.skyState().totoCloud,null);
  a.startGame(true,{forceRestart:true,adminTest:true});
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
  const portraitDraw = quotePainter.drawImage.bind(quotePainter), portraitAlphas = [];
  quotePainter.drawImage = (...args) => { portraitAlphas.push(quotePainter.globalAlpha); return portraitDraw(...args); };
  let panels = 0;
  const lettering = [];
  quotePainter.fill = (...args) => { panels += 1; return originalFill(...args); };
  quotePainter.fillRect = (...args) => { panels += 1; return originalRect(...args); };
  quotePainter.fillText = (...args) => { lettering.push({ font: quotePainter.font, color: quotePainter.fillStyle }); return originalText(...args); };
  a.drawWinterMemory(false); a.drawWinterMemory(true);
  assert.equal(panels, 0, "Winter quotation must have no background panel");
  assert.ok(lettering.length >= 3);
  assert.ok(lettering.every(({ font, color }) => parseFloat(font.match(/[\d.]+(?=px)/)[0]) <= 12 && color === "#27385f"));
  assert.ok(portraitAlphas.some(alpha=>Math.abs(alpha-.55)<1/255),"Russell portrait should be clearly visible at 55% opacity");
  quotePainter.fill = originalFill; quotePainter.fillRect = originalRect; quotePainter.fillText = originalText;
  quotePainter.drawImage = portraitDraw;
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
  const referenceData = reference.getContext("2d").getImageData(0, 0, sectionWidth, original.height);
  a.cleanSpriteContour(referenceData.data,sectionWidth,original.height);
  reference.getContext("2d").putImageData(referenceData,0,0);
  const refPixels = referenceData.data;
  let left = sectionWidth, top = original.height, right = 0, bottom = 0;
  for (let y = 0; y < original.height; y += 1) for (let x = 0; x < sectionWidth; x += 1) {
    if (refPixels[(y * sectionWidth + x) * 4 + 3] <= 18) continue;
    left = Math.min(left, x); right = Math.max(right, x); top = Math.min(top, y); bottom = Math.max(bottom, y);
  }
  const pose = a.art.enemyVariants[0];
  assert.equal(pose.sw, right - left + 1); assert.equal(pose.sh, bottom - top + 1);
  const expected = canvasLib.createCanvas(pose.sw, pose.sh);
  expected.getContext("2d").drawImage(reference, left, top, pose.sw, pose.sh, 0, 0, pose.sw, pose.sh);
  const actualPixels=pose.image.getContext("2d").getImageData(0,0,pose.sw,pose.sh).data;
  const expectedPixels=expected.getContext("2d").getImageData(0,0,pose.sw,pose.sh).data;
  assert.ok(actualPixels.every((value,i)=>value===expectedPixels[i]),
    "Cropping must preserve main silhouette pixels after isolated-speck cleanup");
  console.log(`${mobile ? "Mobile" : "Desktop"}: prefetch, pause/resume, failure/retry, atomic publication, previews, resize and full-resolution seam passed`);

  await a.startWinterBiomeTest();
  const visibleFish = a.state().enemies.slice();
  a.resetWinterEncounters(); a.spawnWinterEncounter("iceman");
  const entering = a.state().winterEncounter, originalY = entering.y;
  assert.ok(a.state().height-(entering.y-a.state().cameraY)+a.winterEnemyGeometry().height/2<0,
    "New winter mob must be completely above the viewport");
  assert.deepEqual(a.state().enemies,visibleFish,"Starting a winter encounter must not erase existing piranhas");
  a.tickEnemy(20);
  assert.equal(a.state().winterEncounter,entering,"Offscreen mobs must not expire after fifteen seconds");
  assert.equal(entering.phase,"arriving");assert.equal(a.state().winterProjectiles.length,0,"No unseen attacks");
  a.cameraAt(entering.y-a.state().height+a.winterEnemyGeometry().height/2+40);
  a.tickEnemy(0);assert.equal(entering.phase,"idle");
  a.tickEnemy(1.2);assert.equal(entering.phase,"warning");
  assert.equal(entering.y,originalY,"Living winter mobs stay in world space instead of chasing the camera");
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
    a.tickEnemy(.9); assert.ok(a.state().winterEncounter,"Defeated mob falls away instead of vanishing on a timer");
    const savedCamera = a.state().cameraY;
    a.cameraAt(a.state().winterEncounter.y+200);a.tickEnemy(0);
    assert.equal(a.state().winterEncounter,null,"Retire only after fully leaving the viewport");
    a.cameraAt(savedCamera);
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
  for (const kind of ["carbon", "satellite", "pitstop", "alonso"]) {
    await h.events.get(`doodle-space-${kind}-test:click`)();
    assert.equal(a.state().spaceEncounter.type,kind);
    assert.equal(a.state().adminBossTestMode,true);
    assert.equal(a.spawnSpaceEncounter("carbon"),false,"Space events cannot stack");
    if (kind === "carbon") {
      assert.equal(a.state().spaceEncounter.debris.length,3,"Carbon shower must leave one of four lanes clear");
      const debris = a.state().spaceEncounter.debris;
      assert.ok(debris.every(d=>d.y-a.state().cameraY>a.state().height+40),"Carbon starts above the viewport");
      const initialY=debris.map(d=>d.y);
      a.updateSpaceEvents(1/60);
      debris.forEach((d,i)=>{
        assert.ok(d.y<initialY[i],"Carbon falls immediately without a hidden warning phase");
        assert.ok(initialY[i]-d.y<2,"First frame must move smoothly without a teleport");
      });
      a.draw();
      a.spaceLanding(); assert.equal(a.state().player.vy,850);
      assert.ok(a.state().spaceEncounter.debris[0].dead);
    } else if (kind === "satellite") {
      const before = a.state().platforms.slice();
      a.setSpaceAge(4); a.draw();
      assert.deepEqual(a.state().platforms,before,"Holograms must never alter the real reachable path");
      assert.equal(a.state().spaceEncounter.ghosts.length,3);
    } else if (kind === "pitstop") {
      a.spaceLanding(); assert.ok(a.state().spacePitHold);
      a.updateSpaceEvents(.76);
      assert.equal(a.state().spacePitHold,null);
      assert.equal(a.state().player.vy,930); assert.equal(a.state().softBootJumps,2);
      a.spaceLanding(); assert.equal(a.state().player.vy,930); assert.equal(a.state().softBootJumps,1);
      a.spaceLanding(); assert.equal(a.state().player.vy,930); assert.equal(a.state().softBootJumps,0);
      a.spaceLanding(); assert.equal(a.state().player.vy,720,"Only three service-enhanced jumps, never unlimited refills");
      assert.equal(a.state().softBootJumps,0);
    } else {
      const x = a.state().spaceEncounter.x;
      a.updateSpaceEvents(.2); assert.notEqual(a.state().spaceEncounter.x,x,"Alonso shuttle moves horizontally");
      a.spaceLanding(); assert.equal(a.state().player.vy,1080);
      a.spaceLanding(); assert.equal(a.state().player.vy,720,"Repeat landings cannot chain unlimited super boosts");
    }
    a.draw();
    if(process.env.DOODLE_PREVIEW_DIR){
      await a.startSpaceEventTest(kind);
      if(kind==="carbon")a.updateSpaceEvents(2.5);
      if(kind==="satellite")a.setSpaceAge(4);
      if(kind==="alonso")a.updateSpaceEvents(4);
      a.draw();
      await fs.writeFile(path.join(process.env.DOODLE_PREVIEW_DIR,`doodle-space-${kind}-${mobile?"mobile":"desktop"}.png`),await h.canvas.encode("png"));
    }
  }
  await a.startSpaceEventTest("carbon");a.hitCarbon(true);assert.equal(a.state().mode,"running");
  a.hitCarbon(false);assert.equal(a.state().mode,"over","Small carbon shards must be real hazards");
  await a.startSpaceEventTest("pitstop");
  const servicePlatform = a.state().spaceEncounter.platform;
  assert.ok(servicePlatform?.spaceService);
  const existingEvent=a.state().spaceEncounter;
  a.forceBoss();assert.equal(a.state().spaceEncounter,existingEvent);assert.equal(servicePlatform.spaceService,existingEvent);
  assert.equal(a.spawnSpaceEncounter("alonso"),false,"No additional space events during Toto fight");
  await a.startSpaceEventTest("pitstop");a.spaceLanding();a.updateSpaceEvents(.76);
  const portalPlatform=a.state().spaceEncounter.platform;
  a.portal();assert.equal(a.state().spaceEncounter,null);assert.equal(portalPlatform.spaceService,undefined);
  assert.equal(a.state().softBootJumps,2,"Earned boosts survive the portal");
  a.startGame(true,{forceRestart:true,adminTest:true});
  assert.equal(a.state().softBootJumps,0);assert.equal(a.state().spaceEncounter,null);
  assert.equal(a.spawnSpaceEncounter("carbon"),false,"Space events must never appear in the paddock");
  assert.deepEqual(h.calls,[],"Space admin buttons never record attempts");
  await a.startSpaceEventTest("carbon");a.clearSpaceEncounter();
  for(let frame=0;frame<850&&!a.state().spaceEncounter;frame+=1)a.updateSpaceEvents(1/60);
  assert.ok(a.state().spaceEncounter,"Events must spawn naturally without test buttons");
  a.clearSpaceEncounter();assert.equal(a.state().spaceEncounter,null);
  console.log(`${mobile ? "Mobile" : "Desktop"}: all four space events, warnings, safe lane, real hazards, three-jump limit, Toto exclusion and cleanup passed`);
  h.blocked.add(dataset.summitBackgroundSrc);
  await a.startWinterBiomeTest();a.peakScore(9999);a.update(1/60);
  assert.equal(a.state().sidBoss,null,"Sid must not spawn before 10000 points");
  a.peakScore(10000);a.update(1/60);
  assert.equal(a.state().sidBoss.hp,10);assert.equal(a.state().score,10000);
  assert.equal(a.spawnWinterEncounter("iceman"),false,"No other winter encounters during Sid fight");
  const bossCamera=a.state().cameraY, bossScore=a.state().score;
  a.bossShield();for(let i=0;i<100;i++)a.update(1/60);
  assert.equal(a.state().cameraY,bossCamera,"Arena camera must remain locked");
  assert.equal(a.state().score,bossScore,"Arena jumps must not farm score");
  assert.equal(a.state().enemies.length,0);
  a.sidPose("intro",0);a.updateSidBoss(1.81);
  assert.equal(a.state().sidBoss.phase,"ice-warning");
  assert.equal(a.state().sidBoss.lanes.length,2,"At least two safe ice lanes");
  a.updateSidBoss(1.3);assert.ok(a.state().sidBoss.shots.some(s=>s.kind==="ice"));
  a.updateSidBoss(1.71);assert.equal(a.state().sidBoss.phase,"can-warning");
  a.updateSidBoss(1.01);assert.ok(a.state().sidBoss.shots.some(s=>s.kind==="can"));
  for(let hit=1;hit<=10;hit++){
    const shot=a.reflectSidCan();assert.equal(shot.reflected,true);
    assert.equal(a.state().sidBoss.hp,11-hit,"Reflection alone must not count as a hit");
    a.impactSidCan();assert.equal(a.state().sidBoss.hp,10-hit);
    if(hit<10)assert.equal(a.enterSummit(),false,"Cannot bypass Sid before all ten hits");
  }
  assert.equal(a.state().sidBoss.phase,"victory");assert.equal(a.state().summit,false);
  for(const [w,ht]of mobile?[[390,844],[844,390],[390,844]]:[[1000,800],[900,1000]]){
    h.resize(w,ht);assert.ok(a.state().platforms.length>=3);a.sidPose("victory",2.5);
    assert.ok(a.state().player.y>a.state().cameraY,"Player remains in resized arena");
  }
  if(process.env.DOODLE_PREVIEW_DIR){a.draw();await fs.writeFile(path.join(process.env.DOODLE_PREVIEW_DIR,`doodle-sid-wings-${mobile?"mobile":"desktop"}.png`),await h.canvas.encode("png"));}
  a.updateSidBoss(4.4);assert.equal(a.state().summit,false,"Wait for the next chapter artwork instead of showing blank scenery");
  h.blocked.delete(dataset.summitBackgroundSrc);assert.equal(await a.loadStage("summit"),true);
  a.updateSidBoss(0);assert.equal(a.state().summit,true);assert.equal(a.state().sidBossCleared,true);
  assert.equal(a.state().score,bossScore+500);assert.equal(a.state().antarctica,false);
  a.update(1/60);assert.equal(a.state().antarcticaScene,null,"Summit must not retrigger the old Antarctic entrance");a.draw();
  a.drawSummitBackdrop();const summitBefore=await h.canvas.encode("png"), beforeClimb=a.state().cameraY;
  a.cameraAt(beforeClimb+1000);a.drawSummitBackdrop();
  assert.notDeepEqual(await h.canvas.encode("png"),summitBefore,"Summit painting must pan on mobile and desktop, not remain static");
  a.cameraAt(beforeClimb);a.draw();
  if(process.env.DOODLE_PREVIEW_DIR)await fs.writeFile(path.join(process.env.DOODLE_PREVIEW_DIR,`doodle-summit-${mobile?"mobile":"desktop"}.png`),await h.canvas.encode("png"));
  await h.events.get("doodle-sid-boss-test:click")();
  assert.equal(a.state().sidBoss.hp,10);assert.equal(a.state().adminBossTestMode,true);
  a.sidHazard("ice",true);assert.equal(a.state().mode,"running");
  a.sidHazard("ice",false);assert.equal(a.state().mode,"over","Ice boulders have lethal collision");
  await a.startSidBossTest();a.sidHazard("crushed",false);assert.equal(a.state().mode,"over","Crushed cans are not reflectable pickups");
  await a.startSidBossTest();a.sidPose("can-warning",.4);
  if(process.env.DOODLE_PREVIEW_DIR)await fs.writeFile(path.join(process.env.DOODLE_PREVIEW_DIR,`doodle-sid-arena-${mobile?"mobile":"desktop"}.png`),await h.canvas.encode("png"));
  a.startGame(true,{forceRestart:true,adminTest:true});assert.equal(a.state().sidBoss,null);assert.equal(a.state().summit,false);assert.equal(a.state().sidBossCleared,false);
  assert.deepEqual(h.calls,[],"Sid boss admin preview must not submit attempts");
  console.log(`${mobile?"Mobile":"Desktop"}: Sid 10000 gate, ten actual impacts, locked camera/score, telegraphs, shield/death, wing finale, resize, lazy summit transition and restart passed`);
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
const coldSpace = await harness(true);
await coldSpace.api.startSpaceEventTest("alonso");
assert.ok(coldSpace.api.art.spaceAlonso.length===4);
assert.equal(coldSpace.requests.has(dataset.antarcticaSrc),false);
assert.deepEqual(coldSpace.calls,[]);
console.log("Cold space event preview passed without downloading winter assets");
const coldSid=await harness(true);
await coldSid.events.get("doodle-sid-boss-test:click")();
assert.equal(coldSid.api.state().sidBoss.hp,10);assert.equal(coldSid.api.state().adminBossTestMode,true);
assert.deepEqual(coldSid.calls,[]);
console.log("Cold Sid preview loads its artwork without recording a real attempt");
await coldSid.events.get("doodle-sid-victory-test:click")();
assert.equal(coldSid.api.state().sidBoss.phase,"victory");
assert.equal(coldSid.api.state().sidBoss.hp,0);
assert.equal(coldSid.api.state().sidBoss.hits,10);
coldSid.api.updateSidBoss(6.81);
assert.equal(coldSid.api.state().summit,true,"Victory preview must continue into the next biome");
assert.deepEqual(coldSid.calls,[],"Post-Sid preview must not save a public score or attempt");
console.log("Admin post-Sid cinematic and next-biome preview passed");
const failed = await harness(true, true);
assert.equal(failed.api.state().artReady, false);
assert.equal(failed.requests.get(dataset.backgroundJourneySrc), 3);
assert.ok(failed.events.get("doodle-start:click"));
failed.events.get("doodle-start:click")({ preventDefault() {} });
assert.deepEqual(failed.calls, ["reload"]);
console.log("Startup failure: bounded image retries and reload action passed");

for (const mobile of [true, false]) {
  const h = await harness(mobile), a = h.api;
  a.startGame(true, {adminTest:true});
  const p = a.state().player;
  p.vx = 0;
  h.events.get('document:keydown')({code:'ArrowRight',key:'ArrowRight',preventDefault(){}});
  a.update(1/60);
  assert.ok(Math.abs(p.vx - Math.min(440,a.state().width*.62)*1.2/6)<.001,
    'Keyboard movement must be 20% faster on both viewport widths');
  a.stage(6500);
  await a.loadStage('sky');
  for (const direction of [1,-1]) {
    const hawk={x:a.state().width*.5,y:6800,size:60,direction,speed:150};
    a.skyState().hawks.splice(0,a.skyState().hawks.length,hawk);
    p.x=hawk.x; p.vy=-300;
    const pose=a.art.hawkFrames[0], hh=a.spriteSize(pose,hawk.size);
    const top=a.spriteTopAtX(pose,hawk.x,hawk.y,hawk.size,hh,hawk.x);
    p.y=top+p.height/2-4;
    a.updateHawks(1/60,top+6,top-4,p.x);
    assert.equal(p.vy,810,'Landing on either flight direction must bounce');
    assert.equal(a.state().mode,'running');
    assert.ok(p.y>=top+p.height/2-2,'Landing must not sink into the bird');
  }
  const hawk=a.skyState().hawks[0];
  a.expireShield();
  p.x=hawk.x; p.y=hawk.y; p.vy=0;
  a.updateHawks(0,p.y-p.height/2,p.y-p.height/2,p.x);
  assert.equal(a.state().mode,'over','Side contacts remain harmful');
  console.log(`${mobile?'Mobile':'Desktop'}: 20% faster controls, mirrored hawk landings and harmful side contacts passed`);
}

for (const mobile of [true, false]) {
  const {api:a} = await harness(mobile);
  a.startGame(true,{adminTest:true});
  const p=a.state().player;
  await a.loadStage('sky');
  // Real opaque contours, including both mirrored directions and fast descents.
  for (const frame of [...a.art.enemyVariants,...a.art.hawkFrames]) {
    const w=60,h=a.spriteSize(frame,w);
    for (const mirror of [-1,1]) for (const offset of [-.3,0,.3]) {
      const x=180, y=600;
      p.x=x+offset*w; p.vy=-900;
      const top=a.spriteTopAtX(frame,x,y,w,h,x+offset*w*mirror);
      if (!Number.isFinite(top)) continue;
      assert.notEqual(a.spriteLanding(frame,x,y,w,h,x-3,y+2,top+20,top-12,p.x-4,mirror),null,
        'Moving enemy contours must catch descending feet, including edge landings');
      p.vy=300;
      assert.equal(a.spriteLanding(frame,x,y,w,h,x,y,top-15,top+5,p.x,mirror),null,
        'Upward movement is not a stomp');
    }
  }
  const empty={mask:{columns:2,rows:2,bits:new Uint8Array(4),topRows:new Uint8Array([2,2])}};
  p.vy=-500;p.x=180;
  assert.equal(a.spriteTopAtX(empty,180,600,60,60,180),-Infinity);
  assert.equal(a.spriteLanding(empty,180,600,60,60,180,600,650,550,180),null,
    'Transparent sprite columns must never act as surfaces');
  p.x=205;
  assert.ok(a.movingLanding(620,580,600,600,155,180,180,20),
    'Contact uses x at crossing, not only final x');
  p.x=180;p.vy=-500;
  assert.equal(a.spriteLanding(null,180,600,60,60,180,600,600,580,180),null,
    'An impact from below the top stays a side impact');
  for (let variant=0;variant<a.art.enemyVariants.length;variant++) {
    const enemy={x:180,previousX:178,y:600,phase:0,variant};
    a.state().enemies.splice(0,a.state().enemies.length,enemy);
    const frame=a.art.enemyVariants[variant], w=72*.68, h=a.spriteSize(frame,w);
    // Start well above every hat and cross the whole enemy in one step.
    p.x=180;p.vy=-1800;p.y=600+p.height/2;
    a.expireShield();
    a.collideWithEnemy(600+h,600,1/60,178);
    assert.ok(enemy.dead,'Every wheel variant must be stompable on a fast descent');
    assert.equal(p.vy,810);
    assert.equal(a.state().mode,'running');
    assert.ok(a.state().invulnerableTimer>0,'Stomp shields against stale same-step collisions');
  }
  const target={x:180,previousX:180,y:600,phase:0,variant:0};
  const adjacent={x:180,previousX:180,y:600+p.height/2,phase:0,type:'piranha'};
  p.x=180;p.y=600+p.height/2;p.vy=-900;
  a.state().enemies.splice(0,a.state().enemies.length,adjacent,target);
  a.expireShield();
  a.collideWithEnemy(630,600,1/60,180);
  assert.ok(target.dead,'A side contact earlier in the array cannot cancel a valid stomp');
  assert.equal(a.state().mode,'running');
  console.log(`${mobile?'Mobile':'Desktop'}: contour edges, moving targets, fast descents, transparent gaps and upward contacts passed`);
}

const safeArrival = await harness(true), arrivalApi = safeArrival.api;
arrivalApi.startGame(true,{adminTest:true});
const originalView = {width:arrivalApi.state().width,height:arrivalApi.state().height};
for (const bounds of [[195,844],[780,1688],[390,1200],[390,650],[390,844]]) {
  safeArrival.resize(...bounds);
  assert.equal(arrivalApi.state().height, originalView.height,
    'Mobile browser zoom must not reveal more world height');
  assert.equal(arrivalApi.state().width, originalView.width);
  assert.ok(parseFloat(safeArrival.canvas.style.width) >= bounds[0] - .01,
    'Mobile canvas must cover the full width without side strips');
  assert.ok(parseFloat(safeArrival.canvas.style.height) >= bounds[1] - .01);
  assert.equal(safeArrival.canvas.style.bottom,'0','Mobile cropping must retain the floor and start platform');
}
await arrivalApi.loadStage('garage');
arrivalApi.stage(60000,5000);
arrivalApi.portal();
arrivalApi.updatePortal(3);
const arrived = arrivalApi.state();
const arrivalPad = arrived.platforms[0];
assert.equal(arrived.forgottenPaddock,true);
assert.equal(arrivalPad.kind,'normal');
assert.ok(arrivalPad.hitboxWidth>=arrived.width*.5,'Arrival has a broad safe pad');
assert.equal(arrived.player.y,arrivalPad.y+arrived.player.height/2);
assert.equal(arrived.player.vy,0,'No blind jump during blackout');
const arrivalY=arrived.player.y;
for(let i=0;i<25;i++)arrivalApi.update(1/60);
assert.equal(arrivalApi.state().player.y,arrivalY,'Stay on the pad until the fade clears');
for(let i=0;i<120;i++)arrivalApi.update(1/60);
assert.equal(arrivalApi.state().mode,'running','The first arrival jump must remain playable');
assert.ok(arrivalApi.state().platforms.length>=4);
console.log('Mobile zoom keeps world bounds fixed; portal has a safe landing ladder and a held fade');

for (const mobile of [true,false]) {
  const h = await harness(mobile), a = h.api;
  assert.equal(a.art.summitCommentator,undefined,'Commentator art must stay out of startup downloads');
  await h.events.get('doodle-commentator-test:click')();
  assert.equal(a.state().summit,true);
  const npc=a.state().summitCommentator, p=a.state().player;
  assert.equal(npc.phase,'boast');
  assert.equal(a.art.summitCommentator.length,4);
  assert.equal(a.art.summitGoat.length,4);
  a.draw();
  if(process.env.DOODLE_PREVIEW_DIR)await fs.writeFile(path.join(process.env.DOODLE_PREVIEW_DIR,`doodle-commentator-idle-${mobile?'mobile':'desktop'}.png`),await h.canvas.encode('png'));
  p.x=npc.x;
  p.vy=300;
  const pose=a.art.summitCommentator[1], nh=a.spriteSize(pose,npc.w);
  const top=a.spriteTopAtX(pose,npc.x,npc.y+nh/2,npc.w,nh,npc.x);
  a.updateSummitCommentator(0,top-3,top+3,p.x);
  assert.equal(npc.phase,'boast','Jumping upwards cannot trigger the shout');
  p.x=npc.x+npc.w; p.vy=-300;
  a.updateSummitCommentator(0,top+5,top-5,p.x);
  assert.equal(npc.phase,'boast','A near miss must not trigger the shout');
  p.x=npc.x; p.y=top+p.height/2-4; p.vy=-300;
  a.updateSummitCommentator(0,top+5,top-4,p.x);
  assert.equal(npc.phase,'shout');
  assert.equal(p.vy,810,'The racer gets a safe upward bounce');
  assert.equal(p.y,top+p.height/2,'Feet snap to the visible silhouette');
  assert.equal(npc.support.broken,false,'The remaining route stays usable');
  a.draw();
  if(process.env.DOODLE_PREVIEW_DIR)await fs.writeFile(path.join(process.env.DOODLE_PREVIEW_DIR,`doodle-commentator-shout-${mobile?'mobile':'desktop'}.png`),await h.canvas.encode('png'));
  a.updateSummitCommentator(.81,top+5,top-4,p.x);
  assert.equal(npc.phase,'fall');
  p.vy=-200;
  a.updateSummitCommentator(.25,top+5,top-4,p.x);
  assert.equal(p.vy,-200,'The falling bath cannot be farmed for repeated bounces');
  const fallingY=npc.y;
  a.draw();
  assert.ok(fallingY<npc.support.y);
  for(let i=0;i<120;i++)a.updateSummitCommentator(1/60,0,0,p.x);
  assert.equal(a.state().summitCommentator,null,'Fall completes below the camera, without a sudden visible timeout');
  assert.deepEqual(h.calls,[],'Admin encounter preview does not save attempts or scores');
  assert.ok(a.state().summitCommentatorNextY-npc.support.y>=11000,
    'Bath repeats only after a large climb');
  // Sample a long climb, not only one local platform pattern.
  const route = [];
  for(let i=0;i<180;i++) {
    const platform={x:100,originX:100,y:a.state().cameraY+100+i*160,phase:0,broken:false};
    a.decorateSummitPlatform(platform); route.push(platform);
  }
  assert.equal(route.filter(p=>p.summitKind==='purple').length,40);
  assert.equal(route.filter(p=>p.summitKind==='cable').length,20);
  const goats=route.filter(p=>p.goat);
  assert.ok(goats.length>=2 && goats.length<=5,'Goats must be rare over 180 platforms');
  for(let i=1;i<goats.length;i++)assert.ok(goats[i].y-goats[i-1].y>=6500);
  assert.ok(route.filter(p=>p.kind==='break').length>=15,'Fragile footholds add difficulty');
  assert.ok(route.filter(p=>p.kind==='moving').length>=40);
  const plainRoute=route.filter(p=>!p.goat && !p.summitKind);
  assert.ok(plainRoute.at(-1).hitboxWidth<plainRoute[0].hitboxWidth,'Ordinary platforms narrow progressively');
  for(let i=0;i<100;i++){
    const gap=a.summitPlatformGap();
    assert.ok(gap>=108&&gap<=146,'Summit uses the regular platform rhythm');
    assert.ok(gap<720*720/(2*1240),'Gap is below the normal jump apex');
    const from=a.state().width*(.14+Math.random()*.72);
    const to=a.choosePlatformX(from,gap,32);
    const flight=(720+Math.sqrt(720*720-2*1240*gap))/1240;
    // Conservative speed excludes the extra 20% control speed. Reserve both movers.
    assert.ok(Math.abs(to-from)+32<=Math.min(440,a.state().width*.62)*flight*.72+.01);
  }
  const cable=route.find(p=>p.summitKind==='cable');
  cable.y=a.state().cameraY+200;
  a.state().platforms.splice(0,a.state().platforms.length,cable);
  assert.equal(a.landingPlatform(cable.y+10,cable.y-10,100,100),cable);
  const goatPlatform=route.find(p=>p.goat);
  goatPlatform.y=a.state().cameraY+300;
  a.state().platforms.push(goatPlatform);
  const goatFrame=a.art.summitGoat[0],gh=a.spriteSize(goatFrame,48);
  const goatTop=a.spriteTopAtX(goatFrame,100,goatPlatform.y+gh/2,48,gh,100);
  p.x=100;p.y=goatTop+p.height/2-3;p.vy=-200;
  a.updateSummitGoats(0,goatTop+5,goatTop-3,100);
  assert.equal(p.vy,850,'Landing on the goat provides an upward bounce');
  assert.equal(goatPlatform.goat.kicked,true);
  a.updateSummitGoats(1.3,0,0,100);
  assert.equal(goatPlatform.goat.kicked,false,'Goat recovers instead of disappearing');
  a.draw();
  if(process.env.DOODLE_PREVIEW_DIR)await fs.writeFile(path.join(process.env.DOODLE_PREVIEW_DIR,`doodle-summit-route-${mobile?'mobile':'desktop'}.png`),await h.canvas.encode('png'));
  a.startGame(true,{forceRestart:true,adminTest:true});
  assert.equal(a.state().summitCommentator,null,'Restart clears the encounter');
  a.spawnSummitCommentator();
  assert.equal(a.state().summitCommentator,null,'Encounter only belongs to the summit biome');
  console.log(`${mobile?'Mobile':'Desktop'}: summit commentator staged art, top-only trigger, bounce, shout, fall, cleanup and sandbox passed`);
}

for (const mobile of [true,false]) {
  const h=await harness(mobile), a=h.api;
  assert.equal(a.art.summitMarmot,undefined);
  assert.equal(a.art.summitDrone,undefined);
  for (const type of ['marmot','drone']) {
    await h.events.get(`doodle-${type}-test:click`)();
    const mob=a.state().summitEncounter,p=a.state().player;
    assert.equal(mob.type,type);assert.equal(mob.phase,'arriving');
    assert.equal(a.art.summitMarmot.length,4);assert.equal(a.art.summitDrone.length,4);
    assert.equal(a.spawnSummitEnemy(type),false,'Only one attacker can exist');
    p.x=15;p.y=a.state().cameraY+70;p.vy=0;
    const tick=dt=>a.updateSummitEnemies(dt,p.y-p.height/2,p.y-p.height/2,p.x);
    const originalY=mob.y;
    mob.y=a.state().cameraY+a.state().height+300;
    tick(2);
    assert.equal(mob.phase,'arriving','Offscreen enemies do not begin attack timers');
    assert.equal(a.state().summitShots.length,0);
    mob.y=originalY;tick(0);tick(.91);
    assert.equal(mob.phase,'warning');
    const warningX=mob.x;
    tick(1.2);assert.equal(a.state().summitShots.length,0,'Warning must precede the shot');
    assert.equal(mob.x,warningX,'Drone stops tracking during its warning');
    a.draw();
    if(process.env.DOODLE_PREVIEW_DIR)await fs.writeFile(path.join(process.env.DOODLE_PREVIEW_DIR,`doodle-summit-${type}-${mobile?'mobile':'desktop'}.png`),await h.canvas.encode('png'));
    tick(.11);assert.equal(a.state().summitShots.length,1);
    assert.equal(a.state().summitShots[0].type,type==='marmot'?'snow':'nut');
    tick(.51);assert.equal(mob.phase,type==='drone'?'retreat':'open');
    tick(.1);assert.equal(a.state().summitShots.length,1,'No burst of surprise projectiles');
    a.draw();
    // Test swept contact at high relative speed, with and without a shield.
    const shot=a.state().summitShots[0];
    shot.x=p.x;shot.y=p.y;shot.vx=0;shot.vy=0;
    tick(0);
    assert.equal(a.state().mode,'running','Entry shield absorbs projectile contact');
    assert.equal(a.state().summitShots.length,0);
    a.expireShield();
    const pp=a.state().player;
    a.state().summitShots.push({type:'nut',x:pp.x,y:pp.y+30,vx:0,vy:-400,age:0});
    a.updateSummitEnemies(.15,pp.y-pp.height/2,pp.y-pp.height/2,pp.x);
    assert.equal(a.state().mode,'over','Fast projectile contact cannot tunnel through the player');
    assert.deepEqual(h.calls,[]);
  }
  await h.events.get('doodle-marmot-test:click')();
  const mob=a.state().summitEncounter,p=a.state().player;
  mob.direction=-1;
  const pose=a.art.summitMarmot[0];
  p.x=mob.x;
  const top=a.spriteTopAtX(pose,mob.x,mob.y,mob.w,mob.h,p.x);
  p.y=top+p.height/2-3;p.vy=-250;
  a.updateSummitEnemies(0,top+5,top-3,p.x);
  assert.equal(mob.phase,'defeated');assert.equal(p.vy,830);
  assert.equal(a.state().summitShots.length,0,'Stomping before the warning cancels the attack');
  a.updateSummitEnemies(2,0,0,p.x);
  assert.ok(mob.y<top,'Defeated marmot falls visibly');
  assert.equal(a.spawnSummitEnemy(),true);
  assert.equal(a.state().summitEncounter.type,'drone','Natural encounters alternate enemy types');
  assert.ok(a.state().summitEncounter.y>a.state().cameraY+a.state().height,
    'Natural enemies begin above the viewport, never beside the player');
  a.startGame(true,{forceRestart:true,adminTest:true});
  assert.equal(a.state().summitEncounter,null);assert.equal(a.state().summitShots.length,0);
  assert.equal(a.spawnSummitEnemy('drone'),false,'Summit enemies cannot spawn in other biomes');
  console.log(`${mobile?'Mobile':'Desktop'}: summit enemies warnings, one-shot attacks, shield/swept contact, stomp and sandbox cleanup passed`);
}

for (const mobile of [true,false]) {
  const h=await harness(mobile),a=h.api;
  await a.startSidBossTest();
  const viewports=mobile?[[390,650],[390,560],[430,740],[844,390],[390,844]]:[[1000,800],[900,1000]];
  for(const [w,ht]of viewports){
    h.resize(w,ht);
    const b=a.sidBossGeometry(),state=a.state(),arenaH=a.sidArenaHeight();
    assert.equal(arenaH,state.visibleWorldHeight);
    assert.ok(b.feet+b.h<=state.cameraY+arenaH-10,'Entire Sid sprite must fit below visible top');
    assert.ok(b.feet>state.cameraY+arenaH*.4,'Sid remains above the player arena');
    assert.ok(state.player.y+state.player.height/2<=state.cameraY+arenaH,
      'Resize must keep the player inside the visible arena');
    a.draw();
    if(process.env.DOODLE_PREVIEW_DIR && mobile && ht===650){
      const image=canvasLib.createCanvas(390,650),painter=image.getContext('2d');
      const scale=390/state.width;
      const srcHeight=650/(scale*parseFloat(h.canvas.style.width)/390)*h.canvas.width/state.width;
      // In this viewport canvas CSS width is 390: emulate its bottom-aligned CSS crop.
      painter.drawImage(h.canvas,0,h.canvas.height-srcHeight,h.canvas.width,srcHeight,0,0,390,650);
      await fs.writeFile(path.join(process.env.DOODLE_PREVIEW_DIR,'doodle-sid-visible-mobile.png'),await image.encode('png'));
    }
  }
  await h.events.get('doodle-drone-test:click')();
  const mob=a.state().summitEncounter,p=a.state().player,pose=a.art.summitDrone[0];
  mob.phase='retreat';
  p.x=mob.x;
  const top=a.spriteTopAtX(pose,mob.x,mob.y,mob.w,mob.h,p.x);
  p.y=top+p.height/2-3;p.vy=-250;
  a.updateSummitEnemies(0,top+5,top-3,p.x);
  assert.equal(mob.phase,'defeated');assert.equal(p.vy,830);
  assert.equal(a.summitEnemyPose(mob),a.art.summitDroneBroken,'Stomp switches to the broken, stopped-rotor sprite');
  const oldY=mob.y,oldX=mob.x;
  a.updateSummitEnemies(.3,0,0,p.x);
  assert.ok(mob.y<oldY,'Broken drone falls under gravity');
  assert.notEqual(mob.x,oldX,'Broken drone drifts while falling');
  assert.equal(a.state().summitShots.length,0,'Destroyed drone cannot fire');
  a.draw();
  if(process.env.DOODLE_PREVIEW_DIR)await fs.writeFile(path.join(process.env.DOODLE_PREVIEW_DIR,`doodle-drone-broken-${mobile?'mobile':'desktop'}.png`),await h.canvas.encode('png'));
  for(let i=0;i<150&&a.state().summitEncounter===mob;i++)a.updateSummitEnemies(1/60,0,0,p.x);
  assert.notEqual(a.state().summitEncounter,mob,'Wreck is removed only after falling offscreen');
  assert.deepEqual(h.calls,[]);
  console.log(`${mobile?'Mobile':'Desktop'}: visible Sid arena and stomped drone wreck animation passed`);
}

for(const mobile of [true,false]) {
  const h=await harness(mobile),a=h.api;
  await h.events.get('doodle-commentator-test:click')();
  a.extendWorld();
  const s=a.state();
  assert.equal(a.art.summitPlatforms.length,4,'All four new platform sprites load with the summit');
  for(const f of a.art.summitPlatforms)assert.ok(f.sw/f.sh>2,'Platform cutouts exclude transparent gutters');
  assert.ok(s.platforms.some(p=>p.summitSide),'Summit offers side footholds as alternative routes');
  const main=s.platforms.filter(p=>!p.summitSide&&!p.commentator).sort((a,b)=>a.y-b.y);
  for(let i=1;i<main.length;i++)assert.ok(main[i].y-main[i-1].y<=146.01,'Main route has regular gaps');
  assert.ok(s.hazards.length>0,'Falling objects appear in the final biome');
  const first=s.hazards[0];
  assert.ok(first.y>s.cameraY+s.height,'Falling objects start above the screen');
  assert.ok(first.speed>=100&&first.speed<=135,'Summit fall speed leaves time to react');
  a.extendWorld();
  assert.ok(a.state().hazards.includes(first),'World generation must not erase active summit hazards');
  a.draw();
  if(process.env.DOODLE_PREVIEW_DIR)await fs.writeFile(path.join(process.env.DOODLE_PREVIEW_DIR,`doodle-summit-platforms-${mobile?'mobile':'desktop'}.png`),await h.canvas.encode('png'));
  assert.deepEqual(h.calls,[]);
  console.log(`${mobile?'Mobile':'Desktop'}: new summit art, regular route, side footholds and falling objects passed`);
}

for(const mobile of [true,false]) {
  const h=await harness(mobile),a=h.api;
  await a.startSpaceEventTest('carbon');
  a.clearSpaceEncounter();
  const existing=a.seedSpaceObjects();
  assert.equal(a.spawnSpaceEncounter('carbon'),true);
  const carbon=a.state().spaceEncounter;
  assert.ok(a.state().enemies.includes(existing.enemy),'Starting carbon preserves enemies');
  assert.ok(a.state().hazards.includes(existing.hazard),'Starting carbon preserves falling items');
  a.bossShield();
  a.forceBoss();
  assert.equal(a.state().spaceEncounter,carbon,'Toto must not erase an active carbon shower');
  assert.ok(a.state().enemies.includes(existing.enemy));
  assert.ok(a.state().hazards.includes(existing.hazard));
  const initialDebrisY=carbon.debris[0].y;
  a.updateSpaceEvents(1/60);
  assert.ok(carbon.debris[0].y<initialDebrisY,'Existing carbon keeps moving while Toto is present');
  a.update(1/60);
  assert.ok(a.state().enemies.includes(existing.enemy),'Per-frame boss updates must preserve visible enemies');
  assert.ok(a.state().hazards.includes(existing.hazard),'Per-frame event updates must preserve falling items');
  a.setSpaceAge(12);a.updateSpaceEvents(0);
  assert.equal(a.state().spaceEncounter,carbon,'Visible carbon cannot disappear on its old eleven-second timeout');
  const boss=a.state().spaceBoss,p=a.state().player;
  for(const x of [a.state().width*.03,a.state().width*.5,a.state().width*.97]){
    p.x=x;p.y=a.state().cameraY+a.state().height*.42;p.vy=-400;
    a.setBossWarning(boss);
    const laneX=(boss.safeLane+.5)*a.state().width/4;
    const bridge=a.state().platforms.filter(platform=>platform.bossBridge).at(-1);
    assert.ok(Math.abs(p.x-bridge.x)<=bridge.hitboxWidth/2,'Entry bridge catches the current position');
    assert.ok(Math.abs(laneX-bridge.x)<=bridge.hitboxWidth/2,'Entry bridge reaches the refuge lane');
    assert.ok(a.landingPlatform(bridge.y+4,bridge.y-4,bridge.x,bridge.x),'Bridge is a real landing surface');
    const refuge=a.state().platforms.filter(platform=>platform.bossSafe&&Math.abs(platform.x-laneX)<.01)
      .sort((a,b)=>a.y-b.y);
    assert.ok(refuge.length>=3);
    assert.ok(refuge.every(platform=>platform.kind==='normal'&&!platform.broken));
    assert.ok(refuge.at(-1).y>=a.state().cameraY+a.state().height);
    for(const platform of refuge){
      assert.ok(platform.hitboxWidth<=a.state().width/4-12,'Footholds remain within the safe lane');
    }
    a.updateSpaceBoss(1.11);
    const shots=a.state().bossShots;
    assert.equal(shots.length,3);
    assert.ok(shots.every(shot=>Math.abs(shot.x-laneX)>a.state().width/8),'No wheel enters the refuge lane');
    a.state().bossShots.length=0;
  }
  const oldTop=boss.safeTopY;
  const safeCount=a.state().platforms.filter(p=>p.bossSafe||p.bossBridge).length;
  const originalRandom=Math.random;
  try {
    Math.random=()=>.9;
    // Same warning repeated at the same location must not add another ladder.
    a.setBossWarning(boss);
    const stableCount=a.state().platforms.filter(p=>p.bossSafe||p.bossBridge).length;
    for(let i=0;i<12;i++)a.setBossWarning(boss);
    assert.equal(a.state().platforms.filter(p=>p.bossSafe||p.bossBridge).length,stableCount,
      'Repeated warnings reuse refuge platforms instead of piling up');
    assert.ok(stableCount<=safeCount+Math.ceil(a.state().height/150)+2);
    const laneX=(boss.safeLane+.5)*a.state().width/4;
    const rows=a.state().platforms.filter(p=>p.bossSafe&&Math.abs(p.x-laneX)<1).sort((a,b)=>a.y-b.y);
    for(let i=1;i<rows.length;i++)assert.ok(rows[i].y-rows[i-1].y>=125,'Refuge platforms have breathing room');
  } finally { Math.random=originalRandom; }
  a.cameraAt(a.state().cameraY+1000);boss.phase='volley';a.extendBossRefuge(boss);
  assert.ok(boss.safeTopY>oldTop,'Safe footholds extend as the camera rises');
  a.draw();
  if(process.env.DOODLE_PREVIEW_DIR)await fs.writeFile(path.join(process.env.DOODLE_PREVIEW_DIR,`doodle-toto-refuge-${mobile?'mobile':'desktop'}.png`),await h.canvas.encode('png'));
  assert.deepEqual(h.calls,[]);
  console.log(`${mobile?'Mobile':'Desktop'}: preserved space objects/events, carbon lifetime and Toto safe-lane footholds passed`);
}

for(const mobile of [true,false]) {
  const h=await harness(mobile),a=h.api;
  a.startGame(true,{adminTest:true});
  for(const [w,ht] of mobile?[[390,844],[390,650],[430,740]]:[[1000,800]]) {
    h.resize(w,ht);
    a.cameraAt(1000);
    const p=a.state().player;p.y=2000;
    for(let i=0;i<90;i++)a.followPlayerCamera(1/60);
    let s=a.state();
    const positionFromTop=1-(p.y-s.cameraY)/s.visibleWorldHeight;
    assert.ok(mobile?positionFromTop>.60&&positionFromTop<.64:Math.abs(positionFromTop-.58)<.01,
      'Mobile hero stays slightly below the visible centre; desktop framing remains stable');
    for(let i=0;i<60;i++){p.y+=400/60;a.followPlayerCamera(1/60);}
    s=a.state();
    if(mobile)assert.ok(1-(p.y-s.cameraY)/s.visibleWorldHeight>.54,'Camera catches ascent before the hero rises above centre');
  }
  console.log(`${mobile?'Mobile':'Desktop'}: camera framing in full and cropped viewports passed`);
}

for(const mobile of [true,false]) {
  const h=await harness(mobile),a=h.api;
  await a.startBathBossTest();
  const b=a.state().bathBoss,p=a.state().player;
  assert.ok(b);assert.equal(b.phase,'boarding');assert.equal(b.hp,8);
  assert.equal(a.art.bathBossPoses.length,12);assert.equal(a.art.bathBossProps.length,9);
  p.x=b.cabinX;p.y=b.cabinY+p.height/2+3;p.vy=-300;
  a.updateBathBoss(1/60);
  assert.equal(b.phase,'ride','A real descending jump boards the cabin');
  for(let i=0;i<241;i++)a.updateBathBoss(1/60);
  assert.equal(b.phase,'intro');
  assert.equal(a.state().platforms.filter(p=>p.y>a.bathGeometry().floor+1).length,2);
  assert.equal(b.bubbles.length,0,'No permanent bubble ladder');
  if(mobile){
    for(const [w,ht] of [[390,560],[844,390],[390,650]]){
      h.resize(w,ht);const view=a.bathGeometry();
      assert.ok(view.y+view.h/2<=a.state().cameraY+view.ah,'Boss fits after mobile orientation changes');
    }
  }
  let g=a.bathGeometry();
  assert.ok(g.y+g.h/2<=a.state().cameraY+g.ah,'Boss fits in the visible mobile arena');
  assert.ok(a.state().platforms.every(p=>p.y>=a.state().cameraY));
  const lockedScore=a.state().score;
  for(let hit=1;hit<=8;hit++) {
    for(let i=0;i<1300&&b.phase!=='open';i++){
      a.bossShield();a.update(1/60);
      if(b.phase==='attack')assert.ok(b.shots.filter(s=>s.kind==='ban').every(s=>Math.floor(s.x/(a.state().width/3))!==b.safeLane),
        'Each volley leaves its announced safe lane free of BAN plates');
    }
    assert.equal(b.phase,'open','Every attack cycle opens an attack window');
    assert.equal(b.bubbles.length,1,'Exactly one counterattack spring per window');
    for(let i=0;i<55;i++){a.bossShield();a.update(1/60);}
    g=a.bathGeometry();
    assert.ok(g.x-g.w/2>=0&&g.x+g.w/2<=a.state().width,'Whole tub remains inside the arena');
    if(process.env.DOODLE_PREVIEW_DIR&&[1,4,7].includes(hit)){
      a.draw();await fs.writeFile(path.join(process.env.DOODLE_PREVIEW_DIR,`doodle-bath-phase-${b.tier}-${mobile?'mobile':'desktop'}.png`),await h.canvas.encode('png'));
    }
    if(hit===1){
      const spring=b.bubbles[0];
      p.x=spring.x;p.vx=0;p.y=spring.y+15+p.height/2+3;p.vy=-300;
      a.updateBathBoss(1/60);
      assert.equal(spring.cooldown,Infinity,'Counterattack bubble is consumed, never recharges');
      assert.equal(p.vy,650);
      for(let i=0;i<120&&b.hp===8;i++)a.updateBathBoss(1/60);
    }else{
      const medalY=g.y-g.h*.08;
      p.x=g.x;p.vx=0;p.y=medalY+p.height/2+3;p.vy=-300;
      a.updateBathBoss(1/60);
    }
    assert.equal(b.hp,8-hit,'One actual descending medal impact removes exactly one life');
    const hp=b.hp;a.updateBathBoss(0);assert.equal(b.hp,hp,'A hit cannot repeat outside the open phase');
    assert.equal(b.tier,hit>=6?3:hit>=3?2:1);
    if(hit<8)assert.equal(a.state().score,lockedScore,'Arena does not farm height points');
  }
  assert.equal(b.phase,'victory');assert.equal(a.state().bathBossCleared,true);
  assert.equal(a.state().score,lockedScore+800);
  for(let i=0;i<182;i++)a.updateBathBoss(1/60);
  assert.equal(b.phase,'eagle');
  for(let i=0;i<150;i++)a.updateBathBoss(1/60);
  a.draw();
  if(process.env.DOODLE_PREVIEW_DIR)await fs.writeFile(path.join(process.env.DOODLE_PREVIEW_DIR,`doodle-bath-eagle-${mobile?'mobile':'desktop'}.png`),await h.canvas.encode('png'));
  for(let i=0;i<250;i++)a.updateBathBoss(1/60);
  assert.equal(b.phase,'complete');assert.equal(a.state().mode,'over');
  assert.deepEqual(h.calls,[],'Admin boss and ending tests never write attempts or scores');
  a.startGame(true,{forceRestart:true,adminTest:true});
  assert.equal(a.state().bathBoss,null);assert.equal(a.state().bathBossCleared,false);
  await h.events.get('doodle-commentator-test:click')();
  a.peakScore(12999);a.update(0);
  assert.equal(a.state().bathBoss,null,'The cabin gate must not trigger before 13000');
  a.peakScore(13000);a.update(0);
  assert.equal(a.state().bathBoss.phase,'boarding','The gate opens automatically at 13000 in the summit');
  a.state().bathBoss.phase='intro';a.buildBathArena();
  const fight=a.state().bathBoss,hero=a.state().player,gg=a.bathGeometry();
  fight.phase='warning';fight.timer=0;fight.lane=0;fight.bubbles=[];
  hero.x=a.state().width*.5;hero.y=gg.floor+100;hero.vy=0;
  fight.shots=[{kind:'ban',x:hero.x,y:hero.y+135/60,vy:-135,age:1}];
  for(let hit=0;hit<3;hit++){
    fight.shots=[{kind:'ban',x:hero.x,y:hero.y+135/60,vy:-135,age:1}];
    a.expireShield();a.updateBathBoss(1/60);
    assert.equal(fight.lives,2-hit);
    if(hit<2)assert.equal(a.state().mode,'running','An arena mistake is recoverable');
  }
  assert.equal(a.state().mode,'over','Third unshielded contact ends the run');
  assert.deepEqual(h.calls,[]);
  console.log(`${mobile?'Mobile':'Desktop'}: bath cabin boarding, eight real hits, three phases, resize, locked score, eagle finale and restart passed`);
}
