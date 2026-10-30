(() => {
  'use strict';
  const board = document.querySelector('[data-prediction-status-url]');
  if (!board) return;
  const indicators = [...board.querySelectorAll('[data-presence-user]')];
  const panel = board.querySelector('[data-presence-panel]');
  const count = board.querySelector('[data-presence-count]');
  const connection = board.querySelector('[data-presence-connection]');
  const reload = board.querySelector('[data-presence-reload]');
  const labels = {saved: 'Прогноз сохранён', missing: 'Прогноз не сохранён', ineligible: 'Не участвует в этом этапе'};
  let eventRound = panel.querySelector('.classification-presence-title>span').textContent.split('·').pop().trim();
  let timer, inflight = false, stopped = false, toast, toastTimer;
  const setText = (node, text) => { if (node.textContent !== text) node.textContent = text; };
  indicators.forEach(button => button.addEventListener('click', () => {
    if (!toast) {
      toast = document.createElement('div');
      toast.className = 'league-presence-toast';
      toast.setAttribute('role', 'status');
      document.body.append(toast);
    }
    toast.textContent = `${button.dataset.playerName} — ${labels[button.dataset.presenceState]} · ${eventRound}${board.dataset.presenceStale === 'true' ? ' (последние полученные данные)' : ''}`;
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, 4000);
  }));
  async function refresh() {
    clearTimeout(timer);
    if (stopped || document.hidden || inflight) return;
    inflight = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(board.dataset.predictionStatusUrl, {
        signal: controller.signal, credentials: 'same-origin', cache: 'no-store',
        headers: {'X-Requested-With': 'XMLHttpRequest'},
      });
      if (!response.ok) {
        if ([401, 403, 404].includes(response.status)) { stopped = true; reload.hidden = false; }
        throw new Error('Presence unavailable');
      }
      const data = await response.json();
      if (!data.event || Number(data.event.id) !== Number(board.dataset.predictionEvent)) {
        // Do not silently attach statuses for a new GP to an old race card.
        indicators.forEach(button => { button.hidden = true; });
        board.dataset.presenceStale = 'true';
        setText(connection, data.event ? 'Этап сменился' : 'Нет предстоящих этапов');
        count.hidden = true;
        reload.hidden = false;
        stopped = true;
        return;
      }
      if (!data.statuses || !Number.isInteger(data.saved) || !Number.isInteger(data.eligible)) throw new Error('Invalid presence');
      for (const button of indicators) {
        const state = data.statuses[button.dataset.presenceUser];
        if (state !== undefined && !labels[state]) throw new Error('Invalid player presence');
      }
      if (board.dataset.presenceStale !== 'false') board.dataset.presenceStale = 'false';
      setText(count, `${data.saved} / ${data.eligible}`);
      setText(connection, data.event.closed ? 'Приём закрыт' : 'Сохранено');
      eventRound = `R${String(data.event.round).padStart(2, '0')}`;
      for (const button of indicators) {
        const state = data.statuses[button.dataset.presenceUser] || 'ineligible';
        if (button.dataset.presenceState === state) continue;
        button.dataset.presenceState = state;
        button.querySelector('.presence-dot').className = `presence-dot is-${state}`;
        const label = `${labels[state]} · ${eventRound}`;
        button.title = label;
        button.setAttribute('aria-label', label);
      }
    } catch (_) {
      board.dataset.presenceStale = 'true';
      setText(connection, 'Нет обновления');
    } finally {
      clearTimeout(timeout);
      inflight = false;
      if (!stopped && !document.hidden) timer = setTimeout(refresh, 15000);
    }
  }
  document.addEventListener('visibilitychange', () => {
    clearTimeout(timer);
    if (!document.hidden) refresh();
  });
  window.addEventListener('online', refresh);
  window.addEventListener('pageshow', refresh);
  timer = setTimeout(refresh, 15000);
})();
