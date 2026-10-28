/* Availability is a hint, never a reservation or a substitute for POST validation. */
(() => {
  'use strict';
  document.querySelectorAll('form[data-handle-check-url]').forEach(form => {
    const input = form.querySelector('input[name="username"], input[name="handle"]');
    const status = form.querySelector('[data-handle-status]');
    const csrf = form.querySelector('input[name="csrfmiddlewaretoken"]');
    if (!input || !status || !csrf) return;
    const field = input.closest('.account-field');
    const serverError = field.querySelector('.account-error');
    const describedBy = new Set((input.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
    describedBy.add(status.id);
    input.setAttribute('aria-describedby', [...describedBy].join(' '));
    let timer, controller, version = 0, composing = false, cooldownUntil = 0;
    const show = (state, message) => {
      status.dataset.state = state;
      status.textContent = message;
      status.hidden = !message;
      if (state === 'invalid') input.setAttribute('aria-invalid', 'true');
      else input.removeAttribute('aria-invalid');
    };
    const unknown = 'Не удалось проверить логин. Проверим при отправке формы.';
    const limited = 'Подожди немного. Логин также проверим при отправке формы.';
    const changed = () => {
      clearTimeout(timer);
      if (controller) controller.abort();
      const current = ++version;
      if (serverError) {
        serverError.hidden = true;
        serverError.querySelectorAll('[id]').forEach(node => describedBy.delete(node.id));
        input.setAttribute('aria-describedby', [...describedBy].join(' '));
      }
      const value = input.value.trim().toLowerCase();
      if (composing || !value) { show('idle', ''); return; }
      if (!/^[a-z0-9]{3,30}$/.test(value)) {
        show('invalid', 'Используй от 3 до 30 латинских букв и цифр, без пробелов и спецсимволов.');
        return;
      }
      if (Date.now() < cooldownUntil) { show('unknown', limited); return; }
      show('checking', 'Проверяем логин…');
      timer = setTimeout(async () => {
        const requestController = new AbortController();
        controller = requestController;
        // A stalled request must not leave the form stuck in “checking”.
        const timeout = setTimeout(() => requestController.abort(), 8000);
        try {
          const response = await fetch(form.dataset.handleCheckUrl, {
            method: 'POST', credentials: 'same-origin', cache: 'no-store',
            headers: {'X-CSRFToken': csrf.value, 'Accept': 'application/json'},
            body: new URLSearchParams({handle: value}), signal: requestController.signal
          });
          if (current !== version) return;
          if (response.status === 429) {
            const wait = Number(response.headers.get('Retry-After')) || 60;
            cooldownUntil = Date.now() + Math.min(Math.max(wait, 1), 3600) * 1000;
            show('unknown', limited);
            return;
          }
          if (!response.ok) throw new Error('Handle check unavailable');
          const result = await response.json();
          if (current !== version) return;
          if (typeof result.available !== 'boolean' || typeof result.message !== 'string') {
            throw new Error('Invalid handle check response');
          }
          show(result.available ? 'available' : 'invalid', result.message);
        } catch (_) {
          if (current === version) show('unknown', unknown);
        } finally {
          clearTimeout(timeout);
          if (controller === requestController) controller = null;
        }
      }, 400);
    };
    input.addEventListener('input', changed);
    input.addEventListener('compositionstart', () => { composing = true; changed(); });
    input.addEventListener('compositionend', () => { composing = false; changed(); });
    // Never block submission on a network check. The server validates again,
    // including when JavaScript is disabled or another player takes the handle.
    form.addEventListener('submit', () => {
      clearTimeout(timer);
      version++;
      if (controller) controller.abort();
    });
  });
})();
