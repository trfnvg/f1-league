(() => {
  'use strict';
  const root = document.querySelector('.ns-home');
  if (!root) return;
  const clock = root.querySelector('[data-race-start]');
  const raceStart = Date.parse(clock?.dataset.raceStart || '');
  const switchAt = Date.parse(root.dataset.stageSwitch || '');
  const serverTime = Date.parse(root.dataset.serverTime || '');
  const offset = Number.isFinite(serverTime) ? serverTime - Date.now() : 0;
  const digits = clock?.querySelector('.ns-countdown-grid');
  const status = clock?.querySelector('.ns-race-status');
  const outputs = clock ? Object.fromEntries([...clock.querySelectorAll('[data-clock]')].map(node => [node.dataset.clock, node])) : {};
  let reloadRequested = false;
  const render = () => {
    const now = Date.now() + offset;
    if (Number.isFinite(switchAt) && now >= switchAt && !document.hidden && !reloadRequested) {
      reloadRequested = true;
      window.location.reload();
      return;
    }
    if (!Number.isFinite(raceStart) || !digits) return;
    const remaining = Math.max(0, Math.ceil((raceStart - now) / 1000));
    digits.hidden = remaining === 0;
    if (status) {
      status.hidden = remaining > 0;
      if (!remaining) status.textContent = Number.isFinite(switchAt) && now < switchAt ? 'Гонка идёт' : 'Гонка завершена';
    }
    const parts = {days: Math.floor(remaining / 86400), hours: Math.floor(remaining / 3600) % 24, minutes: Math.floor(remaining / 60) % 60, seconds: remaining % 60};
    for (const [key, value] of Object.entries(parts)) {
      const text = String(value).padStart(2, '0');
      if (outputs[key] && outputs[key].textContent !== text) outputs[key].textContent = text;
    }
  };
  let timer;
  const resume = () => {
    clearInterval(timer);
    if (!document.hidden) { render(); timer = setInterval(render, 1000); }
  };
  document.addEventListener('visibilitychange', resume);
  window.addEventListener('pageshow', resume);
  resume();
})();
