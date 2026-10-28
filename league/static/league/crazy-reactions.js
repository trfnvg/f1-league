(() => {
  const pending = new Set();
  document.querySelectorAll('[data-reaction-form]').forEach(form => form.addEventListener('submit', async event => {
    event.preventDefault();
    const group = form.closest('[data-reactions]'), url = group.dataset.reactionUrl;
    if (pending.has(url)) return;
    pending.add(url);
    const matching = [...document.querySelectorAll('[data-reactions]')].filter(item => item.dataset.reactionUrl === url);
    matching.forEach(item => {item.setAttribute('aria-busy', 'true'); item.querySelector('[data-reaction-status]').textContent = '';});
    try {
      const response = await fetch(url, {method:'POST', body:new FormData(form), credentials:'same-origin', headers:{Accept:'application/json'}});
      if (!response.ok || response.redirected || !response.headers.get('Content-Type')?.includes('application/json')) throw new Error();
      const data = await response.json();
      matching.forEach(item => {
        data.options.forEach(option => {
          const button = item.querySelector(`[data-reaction-kind="${option.kind}"]`);
          if (!button) return;
          button.setAttribute('aria-pressed', String(option.selected));
          button.querySelector('[data-reaction-count]').textContent = option.count;
        });
        item.querySelector('[data-reaction-status]').textContent = 'Сохранено';
      });
    } catch {
      matching.forEach(item => {item.querySelector('[data-reaction-status]').textContent = 'Не удалось сохранить. Обновите страницу и попробуйте снова.';});
    } finally {
      pending.delete(url);
      matching.forEach(item => item.removeAttribute('aria-busy'));
    }
  }));
})();
