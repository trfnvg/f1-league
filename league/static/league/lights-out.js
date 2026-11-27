(() => {
  "use strict";

  const game = document.querySelector("[data-lights-out]");
  if (!game) return;
  const lamps = Array.from(game.querySelectorAll("[data-lamp]"));
  const action = game.querySelector("[data-action]");
  const status = game.querySelector("[data-status]");
  const hint = game.querySelector("[data-hint]");
  const audioButton = game.querySelector("[data-audio]");
  const bestDisplay = game.querySelector("[data-best]");
  const result = game.querySelector("[data-result]");
  const time = game.querySelector("[data-time]");
  const bestKey = "fastlap-lights-out-best-" + game.dataset.playerId;
  const soundKey = "fastlap-lights-out-sound";

  function load(key) {
    try { return localStorage.getItem(key); } catch { return null; }
  }

  function save(key, value) {
    try { localStorage.setItem(key, value); } catch { /* Private mode can deny storage. */ }
  }

  let best = Number(load(bestKey));
  if (!Number.isFinite(best) || best < 1 || best > 10000) best = 0;
  let soundEnabled = load(soundKey) !== "off";
  let audioContext;
  let audioOutput;
  let soundBuffer;
  let soundDownload;
  let loadingSound = false;
  let frame = 0;
  let nextLightAt = 0;
  let lightCount = 0;
  let goAt = 0;
  let phase = "ready";
  let pendingTouchStart = null;

  function showBest() {
    bestDisplay.textContent = best ? best + " мс" : "—";
  }

  function showSound() {
    audioButton.setAttribute("aria-pressed", String(soundEnabled));
    if (audioOutput) audioOutput.gain.value = soundEnabled ? 1 : 0;
  }

  function downloadSound() {
    soundDownload ||= fetch(game.dataset.soundUrl)
      .then(response => {
        if (!response.ok) throw new Error("Lamp sound unavailable");
        return response.arrayBuffer();
      })
      .catch(() => {
        soundDownload = null;
        return null;
      });
    return soundDownload;
  }

  function prepareSound() {
    if (!soundEnabled) return;
    const AudioEngine = window.AudioContext || window.webkitAudioContext;
    if (!AudioEngine) return;
    try {
      if (!audioContext) {
        audioContext = new AudioEngine();
        audioOutput = audioContext.createGain();
        audioOutput.connect(audioContext.destination);
      }
      if (audioContext.state !== "running") audioContext.resume().catch(() => {});
      if (!loadingSound && !soundBuffer) {
        loadingSound = true;
        downloadSound()
          .then(data => data && audioContext.decodeAudioData(data.slice(0)))
          .then(buffer => { soundBuffer = buffer; })
          .catch(() => { /* The visual signal still works. */ })
          .finally(() => { loadingSound = false; });
      }
    } catch { /* The visual signal still works. */ }
  }

  function playLampSound() {
    if (!soundEnabled || !soundBuffer || audioContext?.state !== "running") return;
    const source = audioContext.createBufferSource();
    source.buffer = soundBuffer;
    source.connect(audioOutput);
    source.onended = () => source.disconnect();
    source.start();
  }

  function showPhase(value, message, label, instruction) {
    phase = value;
    game.dataset.state = value;
    status.textContent = message;
    action.textContent = label;
    hint.textContent = instruction;
  }

  function setLamps(count) {
    lightCount = count;
    lamps.forEach((lamp, index) => lamp.classList.toggle("is-lit", index < count));
  }

  function endAttempt(state, message) {
    cancelAnimationFrame(frame);
    setLamps(0);
    showPhase(state, message, "Ещё раз", "Попытки без лимита");
  }

  function tick() {
    const now = performance.now();
    if (phase === "countdown" && now >= nextLightAt) {
      if (lightCount < lamps.length) {
        setLamps(lightCount + 1);
        playLampSound();
        nextLightAt = now + (lightCount === lamps.length ? 450 + Math.random() * 1850 : 650);
      } else {
        setLamps(0);
        showPhase("go", "Огни погасли!", "Старт", "Жми сейчас");
        goAt = performance.now();
      }
    } else if (phase === "go" && now - goAt >= 10000) {
      endAttempt("expired", "Старт пропущен");
      return;
    }
    frame = requestAnimationFrame(tick);
  }

  function press(pressedAt) {
    if (phase === "countdown" || (phase === "go" && pressedAt < goAt)) {
      endAttempt("false-start", "Фальстарт");
      return;
    }
    if (phase === "go") {
      const reaction = Math.max(1, Math.round(pressedAt - goAt));
      if (reaction > 10000) {
        endAttempt("expired", "Старт пропущен");
        return;
      }
      const improved = !best || reaction < best;
      if (improved) {
        best = reaction;
        save(bestKey, best);
        showBest();
      }
      time.textContent = reaction;
      result.hidden = false;
      endAttempt("result", (improved ? "Новый рекорд" : "Твоя реакция") + " · " + reaction + " мс");
      return;
    }
    pendingTouchStart = null;
    prepareSound();
    result.hidden = true;
    setLamps(0);
    goAt = 0;
    nextLightAt = performance.now() + 300;
    showPhase("countdown", "Жди сигнала", "Старт", "Нажми, когда погаснут все пять огней");
    frame = requestAnimationFrame(tick);
  }

  function actionTime(event) {
    const now = performance.now();
    // Some browsers and assistive tools use epoch timestamps or supply none.
    return event.timeStamp > 0 && event.timeStamp <= now ? event.timeStamp : now;
  }

  action.addEventListener("pointerdown", event => {
    if (!event.isPrimary || event.button !== 0) return;
    if (event.pointerType !== "mouse" && phase !== "countdown" && phase !== "go") {
      pendingTouchStart = event.pointerId;
      return;
    }
    press(actionTime(event));
  });
  action.addEventListener("pointerup", event => {
    // Begin on touch release to unlock audio. Measure reactions on touch down.
    if (event.pointerId !== pendingTouchStart) return;
    pendingTouchStart = null;
    press(actionTime(event));
  });
  action.addEventListener("pointercancel", event => {
    if (event.pointerId === pendingTouchStart) pendingTouchStart = null;
  });
  action.addEventListener("click", event => {
    // Assistive technology and Enter trigger a click without pointerdown.
    if (event.detail === 0) press(actionTime(event));
  });
  document.addEventListener("keydown", event => {
    if (event.code !== "Space" || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    const focusedControl = event.target.closest?.("a, button, input, select, textarea, [contenteditable]");
    if (focusedControl && focusedControl !== action) return;
    event.preventDefault();
    if (!event.repeat) press(actionTime(event));
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && (phase === "countdown" || phase === "go")) {
      endAttempt("expired", "Попытка прервана");
    }
  });
  audioButton.addEventListener("click", () => {
    soundEnabled = !soundEnabled;
    save(soundKey, soundEnabled ? "on" : "off");
    showSound();
    if (soundEnabled) prepareSound();
  });

  showBest();
  showSound();
  if (soundEnabled) downloadSound();
})();
