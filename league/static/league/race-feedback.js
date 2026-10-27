(() => {
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const counters = new Map();
  let frame = 0;
  function finishCounters() {
    cancelAnimationFrame(frame);
    frame = 0;
    counters.forEach((state, node) => { node.textContent = state.text; });
    counters.clear();
  }
  function tick(now) {
    counters.forEach((state, node) => {
      const progress = Math.min(1, (now - state.start) / 650);
      node.textContent = String(Math.round(state.target * (1 - (1 - progress) ** 3)));
      if (progress === 1) {
        node.textContent = state.text;
        counters.delete(node);
      }
    });
    frame = counters.size ? requestAnimationFrame(tick) : 0;
  }
  function count(node) {
    const target = Number(node.dataset.countTo);
    if (motion.matches || document.hidden || !Number.isFinite(target) || !target) return;
    // Reserve the final number's width before changing its text. Rows never move.
    node.style.minWidth = `${node.getBoundingClientRect().width}px`;
    counters.set(node, {target, text: node.textContent, start: performance.now()});
    node.textContent = '0';
    if (!frame) frame = requestAnimationFrame(tick);
  }
  function firstFinish(key) {
    try {
      const store = 'fastlap:finish-feedback:v1';
      const history = JSON.parse(localStorage.getItem(store) || '[]');
      const seen = Array.isArray(history) ? history : [];
      if (seen.includes(key)) return false;
      localStorage.setItem(store, JSON.stringify([...seen.slice(-39), key]));
      return true;
    } catch (_) { return false; }
  }
  function reveal(node) {
    if (node.matches('[data-count-to]')) count(node);
    else if (node.matches('[data-race-finish]')) {
      if (firstFinish(node.dataset.raceFinish) && !motion.matches) node.classList.add('is-finishing');
    } else if (!motion.matches && node.textContent.trim() !== '—') {
      node.setAttribute('data-position-change', '');
      node.classList.add('is-moving');
    }
  }
  const nodes = document.querySelectorAll('[data-count-to], [data-race-finish], .classification-movement');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (!entry.isIntersecting || document.hidden) return;
      reveal(entry.target);
      observer.unobserve(entry.target);
    }), {threshold: .2});
    nodes.forEach(node => observer.observe(node));
  }
  motion.addEventListener('change', finishCounters);
  document.addEventListener('visibilitychange', () => { if (document.hidden) finishCounters(); });
  window.addEventListener('pagehide', finishCounters);
})();
