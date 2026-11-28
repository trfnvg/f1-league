(() => {
  "use strict";
  const scene = document.querySelector(".lights-out-scene");
  if (!scene) return;
  const matte = scene.querySelector(".grid-matte");
  const photo = matte.querySelector("picture img");
  const people = matte.querySelector(".grid-people");
  const portrait = matchMedia("(max-aspect-ratio: 1/1)");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)");

  // Hand-registered photographic patches, in art coordinates (not screen pixels).
  // Only the shoulders/heads move; the wall, floor and foreground stay still.
  const shots = {
    wide: { w: 1000, h: 562, fans: [
      [11,135,16,24],[25,148,15,24],[45,149,14,21],[65,162,14,20],
      [83,168,13,20],[103,171,12,19],[125,184,12,18],[147,182,11,16],
      [170,192,11,15],[202,199,10,14],[228,203,9,13],[258,213,8,12],
      [32,52,12,16],[85,72,11,15],[140,101,10,14],[191,120,9,13]],
      crews: [[902,214,28,40],[968,218,22,28],[789,225,14,25],[729,236,13,21],[685,240,12,18]] },
    portrait: { w: 506, h: 900, fans: [
      [10,402,14,21],[22,413,14,20],[40,405,13,18],[58,419,13,17],
      [80,420,11,17],[101,427,11,15],[121,425,10,13],[141,435,9,12],
      [162,436,8,11],[14,308,12,17],[49,327,11,15],[83,349,10,13],[122,374,9,12]],
      crews: [[479,419,20,25],[468,431,17,31],[432,427,14,25],[374,435,12,19]] },
  };
  function registerPeople() {
    people.replaceChildren();
    if (!photo.complete || !photo.naturalWidth) return;
    const illumination = scene.querySelector(".grid-practicals");
    illumination.style.backgroundImage = 'url("' + photo.currentSrc + '")';
    illumination.style.filter = "url(#grid-emission)";
    if (reduce.matches) return;
    const shot = portrait.matches ? shots.portrait : shots.wide;
    const patches = document.createDocumentFragment();
    for (const [kind, points] of [["fan", shot.fans], ["crew", shot.crews]]) {
      points.forEach(([x,y,w,h], i) => {
        const node = document.createElement("i");
        node.className = "grid-person grid-person--" + kind;
        const {style} = node;
        style.left = (x-w/2)/shot.w*100 + "%";
        style.top = (y-h/2)/shot.h*100 + "%";
        style.width = w/shot.w*100 + "%"; style.height = h/shot.h*100 + "%";
        style.backgroundImage = 'url("' + photo.currentSrc + '")';
        style.backgroundSize = shot.w/w*100 + "% " + shot.h/h*100 + "%";
        style.backgroundPosition = (x-w/2)/(shot.w-w)*100 + "% " + (y-h/2)/(shot.h-h)*100 + "%";
        style.setProperty("--period", (kind === "crew" ? 4.8 : 2.9) + (i%5)*.46 + "s");
        style.setProperty("--delay", -(i*1.71 + .8) + "s");
        patches.append(node);
      });
    }
    people.append(patches);
  }
  photo.addEventListener("load", registerPeople);
  portrait.addEventListener("change", registerPeople);
  reduce.addEventListener("change", registerPeople);
  registerPeople();

  // Anchor the shared seven-day sunset to server time rather than the player's clock.
  const serverTime = Number(scene.dataset.serverMs);
  const deadline = Number(scene.dataset.deadlineMs);
  const opened = Date.now();
  const week = 7 * 24 * 3600 * 1000;
  const clamp = v => Math.max(0, Math.min(1, v));
  const smooth = v => v * v * (3 - 2 * v);
  const channels = scene.querySelector("feComponentTransfer").children;
  const saturation = scene.querySelector("feColorMatrix");
  // Nonlinear exposure keeps garage lights and canopy LEDs lit at night.
  const nightCurves = [[.006,.026,.052,.082,.125,.185,.29,.56,.97],
                      [.012,.034,.067,.106,.16,.23,.36,.66,.98],
                      [.027,.055,.094,.145,.209,.29,.43,.73,1]];
  function relight() {
    const time = serverTime + (Date.now() - opened);
    const p = deadline && serverTime ? clamp(1 - (deadline-time)/week) : 0;
    const night = smooth(clamp((p-.36)/.64));
    matte.style.setProperty("--dusk", p.toFixed(6));
    matte.style.setProperty("--night", night.toFixed(6));
    matte.style.setProperty("--sun-visible", (1-smooth(clamp((p-.62)/.2))).toFixed(5));
    saturation.setAttribute("values", (1 - .78 * night).toFixed(5));
    for (let c=0; c<channels.length; c++) {
      channels[c].setAttribute("type", "table");
      channels[c].setAttribute("tableValues", nightCurves[c].map((v,i) =>
        (i/8*(1-night) + v*night).toFixed(5)).join(" "));
    }
    matte.style.filter = night ? "url(#grid-grade)" : "none";
    scene.dataset.light = p === 1 ? "night" : "sunset";
  }
  let timer;
  function refresh() {
    clearTimeout(timer);
    if (document.hidden) return;
    relight();
    const remaining = deadline - (serverTime + Date.now() - opened);
    if (remaining > 0) timer = setTimeout(refresh, Math.min(30000, remaining));
  }
  document.addEventListener("visibilitychange", refresh);
  window.addEventListener("pageshow", refresh);
  refresh();
})();
