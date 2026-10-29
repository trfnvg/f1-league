(() => {
  document.querySelectorAll('[data-duel-availability]').forEach(form => {
    const select = form.elements.namedItem('opponent');
    const button = form.querySelector('button[type="submit"]');
    const status = form.querySelector('[data-duel-opponent-status]');
    let controller;
    let checking = false;
    let unavailable = false;
    let revision = 0;
    async function check() {
      const current = ++revision;
      controller?.abort();
      unavailable = false;
      checking = !!select.value;
      button.disabled = checking;
      status.hidden = !select.value;
      status.dataset.unavailable = 'false';
      select.removeAttribute('aria-invalid');
      if (!select.value) return;
      status.textContent = 'Проверяем доступность соперника…';
      const requestController = new AbortController();
      controller = requestController;
      const timeout = setTimeout(() => requestController.abort(), 8000);
      try {
        const url = new URL(form.dataset.duelAvailability, location.href);
        url.searchParams.set('opponent', select.value);
        const response = await fetch(url, {signal: requestController.signal, credentials: 'same-origin', cache: 'no-store'});
        if (!response.ok) throw new Error('Availability check failed');
        const data = await response.json();
        if (typeof data.available !== 'boolean') throw new Error('Invalid availability response');
        if (current !== revision) return;
        unavailable = !data.available;
        status.hidden = !unavailable;
        status.dataset.unavailable = String(unavailable);
        status.textContent = data.message || '';
        if (unavailable) select.setAttribute('aria-invalid', 'true');
      } catch {
        if (current !== revision) return;
        // The POST still validates on the server if the advisory check fails.
        status.hidden = false;
        status.textContent = 'Не удалось проверить соперника. Проверим доступность при отправке вызова.';
      } finally {
        clearTimeout(timeout);
        if (current === revision) {
          checking = false;
          button.disabled = unavailable;
        }
      }
    }
    select.addEventListener('change', check);
    form.addEventListener('submit', event => {
      if (checking || unavailable) event.preventDefault();
    });
    window.addEventListener('pageshow', () => { if (select.value) check(); });
    if (select.value) check();
  });
})();
