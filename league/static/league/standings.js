(() => {
  const board = document.querySelector('.classification');
  const viewport = board?.querySelector('.classification-viewport');
  if (!viewport) return;
  const controls = board.querySelector('.classification-controls');
  const previous = controls.querySelector('[data-table-step="-1"]');
  const next = controls.querySelector('[data-table-step="1"]');
  const jump = controls.querySelector('[data-latest-round]');
  const headers = [...board.querySelectorAll('.classification-stage-header')];
  const columns = new Map(headers.map(header => [header.dataset.roundId, []]));
  board.querySelectorAll('[data-round-id]').forEach(cell => columns.get(cell.dataset.roundId)?.push(cell));
  let selected = null;
  let scheduled = false;

  function pinnedWidth() {
    const row = viewport.querySelector('thead tr');
    return row.cells[0].getBoundingClientRect().width + row.cells[1].getBoundingClientRect().width;
  }
  function updateNavigation() {
    const max = viewport.scrollWidth - viewport.clientWidth;
    controls.hidden = max <= 1;
    previous.disabled = viewport.scrollLeft < 2;
    next.disabled = viewport.scrollLeft >= max - 2;
    viewport.classList.toggle('is-scrolled', viewport.scrollLeft > 1);
    scheduled = false;
  }
  function scrollTo(left, smooth = true) {
    viewport.scrollTo({left, behavior: smooth && !matchMedia('(prefers-reduced-motion: reduce)').matches ? 'smooth' : 'auto'});
  }
  function reveal(header, smooth = true) {
    const view = viewport.getBoundingClientRect();
    const box = header.getBoundingClientRect();
    const left = view.left + pinnedWidth();
    if (box.left < left) scrollTo(viewport.scrollLeft + box.left - left, smooth);
    else if (box.right > view.right) scrollTo(viewport.scrollLeft + box.right - view.right, smooth);
  }
  function select(header) {
    if (selected) {
      columns.get(selected.dataset.roundId).forEach(cell => cell.classList.remove('is-selected'));
      selected.querySelector('button').setAttribute('aria-pressed', 'false');
    }
    selected = header;
    columns.get(header.dataset.roundId).forEach(cell => cell.classList.add('is-selected'));
    header.querySelector('button').setAttribute('aria-pressed', 'true');
    const selection = board.querySelector('.classification-selection');
    selection.hidden = false;
    selection.querySelector('[data-selection-caption]').textContent = header.dataset.roundTitle;
    selection.querySelector('[data-selection-link]').href = header.dataset.roundUrl;
  }
  headers.forEach(header => {
    const button = header.querySelector('button');
    button.hidden = false;
    button.addEventListener('click', () => { select(header); reveal(header); });
    button.addEventListener('focus', () => reveal(header, false));
  });
  controls.querySelectorAll('[data-table-step]').forEach(button => button.addEventListener('click', () => {
    scrollTo(viewport.scrollLeft + Number(button.dataset.tableStep) * Math.max(68, (viewport.clientWidth - pinnedWidth()) * .85));
  }));
  jump?.addEventListener('click', () => {
    const header = headers.find(item => item.dataset.roundId === jump.dataset.latestRound);
    if (header) { select(header); reveal(header); }
  });
  viewport.addEventListener('scroll', () => {
    if (!scheduled) { scheduled = true; requestAnimationFrame(updateNavigation); }
  }, {passive:true});
  window.addEventListener('resize', updateNavigation, {passive:true});
  const latest = headers.find(header => header.classList.contains('is-latest'));
  if (latest) { select(latest); reveal(latest, false); }
  updateNavigation();
})();
