(() => {
  const board = document.querySelector('.classification');
  const viewport = board?.querySelector('.classification-viewport');
  if (!viewport) return;
  const controls = board.querySelector('.classification-controls');
  const previous = controls.querySelector('[data-table-step="-1"]');
  const next = controls.querySelector('[data-table-step="1"]');
  const jump = controls.querySelector('[data-latest-round]');
  const headers = [...board.querySelectorAll('.classification-stage-header')];
  const picker = board.querySelector('[data-round-picker]');
  const modes = [...board.querySelectorAll('[data-table-mode]')];
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
    if (board.classList.contains('is-overview')) return;
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
    picker.value = header.dataset.roundId;
    board.querySelector('[data-summary-round]').textContent = header.querySelector('strong').textContent;
    board.querySelectorAll('tbody tr').forEach(row => {
      const source = [...row.querySelectorAll('.classification-result')].find(cell => cell.dataset.roundId === header.dataset.roundId);
      const target = row.querySelector('.classification-summary');
      target.classList.toggle('is-unscored', source.classList.contains('is-unscored'));
      target.classList.toggle('is-penalty', source.classList.contains('is-penalty'));
      target.querySelector('.classification-round-score').textContent = source.classList.contains('is-unscored') ? '—' : source.querySelector('.classification-score').textContent.trim();
      if (source.classList.contains('is-unscored')) target.setAttribute('aria-label', 'Нет результата');
      else target.removeAttribute('aria-label');
    });
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
  function setMode(mode) {
    board.classList.toggle('is-overview', mode === 'overview');
    board.classList.toggle('is-rounds', mode === 'rounds');
    modes.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.tableMode === mode)));
    viewport.scrollLeft = 0;
    viewport.tabIndex = mode === 'overview' ? -1 : 0;
    if (selected) reveal(selected, false);
    updateNavigation();
  }
  modes.forEach(button => button.addEventListener('click', () => setMode(button.dataset.tableMode)));
  picker.addEventListener('change', () => {
    const header = headers.find(item => item.dataset.roundId === picker.value);
    if (header) select(header);
  });
  picker.disabled = !headers.length;
  board.querySelector('.classification-workspace').hidden = false;
  setMode('overview');
  const latest = headers.find(header => header.classList.contains('is-latest')) || headers[0];
  if (latest) select(latest);
  updateNavigation();
})();
