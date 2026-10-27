(() => {
  const scene = document.querySelector('[data-home-launch]');
  if (!scene) return;
  const intro = scene.closest('.home-launch-intro');
  const replay = scene.querySelector('[data-launch-replay]');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const key = 'fastlap:home-launch:v1';
  let played = true, timer = 0, frame = 0;
  try { played = sessionStorage.getItem(key) === 'seen'; } catch (_) {}
  const state = value => { scene.dataset.state = value; intro.dataset.launchState = value; };
  function finish() {
    clearTimeout(timer);
    cancelAnimationFrame(frame);
    state(reduced.matches ? 'idle' : 'complete');
    replay.disabled = false;
  }
  function play() {
    if (reduced.matches || document.hidden || scene.dataset.state === 'playing') return;
    played = true;
    try { sessionStorage.setItem(key, 'seen'); } catch (_) {}
    clearTimeout(timer);
    state('idle');
    replay.disabled = true;
    // Two frames allow a manual replay to restart the CSS timeline cleanly.
    frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(() => {
        state('playing');
        timer = setTimeout(finish, 2400);
      });
    });
  }
  replay.hidden = reduced.matches;
  replay.addEventListener('click', play);
  scene.addEventListener('animationend', event => {
    if (event.animationName === 'home-car-depart') finish();
  });
  reduced.addEventListener('change', () => {
    replay.hidden = reduced.matches;
    if (reduced.matches) { finish(); state('idle'); }
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && replay.disabled) finish();
  });
  window.addEventListener('pagehide', () => { if (replay.disabled) finish(); });
  if (!played && !reduced.matches && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting) && !document.hidden) {
        play(); observer.disconnect();
      }
    }, {threshold:.3});
    observer.observe(scene);
  }
})();
