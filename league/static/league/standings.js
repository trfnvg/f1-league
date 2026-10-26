(() => {
  const board = document.querySelector('.classification');
  const viewport = board?.querySelector('.classification-viewport');
  const controls = board?.querySelector('.classification-controls');
  if (!viewport || !controls) return;
  const previous = controls.querySelector('[data-table-step="-1"]');
  const next = controls.querySelector('[data-table-step="1"]');
  let scheduled = false;
  function updateNavigation() {
    const maximum = Math.max(0, viewport.scrollWidth - viewport.clientWidth);
    controls.hidden = maximum <= 1;
    previous.disabled = viewport.scrollLeft < 2;
    next.disabled = viewport.scrollLeft >= maximum - 2;
    scheduled = false;
  }
  controls.querySelectorAll('[data-table-step]').forEach(button => {
    button.addEventListener('click', () => {
      const cells = viewport.querySelector('thead tr').cells;
      const pinned = cells[0].getBoundingClientRect().width + cells[1].getBoundingClientRect().width;
      const step = Math.max(64, viewport.clientWidth - pinned);
      viewport.scrollLeft += Number(button.dataset.tableStep) * step;
    });
  });
  viewport.addEventListener('scroll', () => {
    if (!scheduled) {
      scheduled = true;
      requestAnimationFrame(updateNavigation);
    }
  }, {passive: true});
  window.addEventListener('resize', updateNavigation, {passive: true});
  updateNavigation();
})();
