(() => {
  document.querySelectorAll('[data-save-status]').forEach(status => {
    const form = status.closest('form');
    if (!form) return;
    const fields = [...form.elements].filter(el => el.name && el.name !== 'csrfmiddlewaretoken' && !['submit', 'button'].includes(el.type));
    const values = () => JSON.stringify(fields.map(el => [el.name, el.value, el.checked]));
    const initial = values();
    const invalid = status.dataset.invalid === 'yes';
    const label = status.querySelector('[data-save-label]');
    const note = status.querySelector('[data-save-note]');
    const originalLabel = label.textContent, originalNote = note.textContent;
    const badge = form.closest('.event-page')?.querySelector('.event-status-badge');
    let sending = false;
    const dirty = () => invalid || values() !== initial;
    const warn = event => { if (dirty() && !sending) { event.preventDefault(); event.returnValue = ''; } };
    const render = () => {
      const changed = dirty();
      window.removeEventListener('beforeunload', warn);
      if (changed) window.addEventListener('beforeunload', warn);
      if (Date.now() >= Date.parse(status.dataset.deadline)) {
        label.textContent = 'Прогнозы зафиксированы';
        note.textContent = changed ? 'Изменения на этой странице не сохранены. Дедлайн уже прошёл.' : 'Приём прогнозов завершён.';
      } else {
        label.textContent = changed ? 'Есть несохранённые изменения' : originalLabel;
        note.textContent = changed ? 'Нажми «Сохранить прогноз», чтобы ответы попали в зачёт.' : originalNote;
      }
      if (badge) badge.textContent = label.textContent;
    };
    form.addEventListener('input', render);
    form.addEventListener('change', render);
    form.addEventListener('submit', event => {
      queueMicrotask(() => {
        if (event.defaultPrevented) return;
        sending = true;
        label.textContent = 'Сохраняем прогноз…';
        note.textContent = 'Дождись подтверждения от сервера.';
      });
    });
    window.addEventListener('pageshow', () => { sending = false; render(); });
    document.addEventListener('visibilitychange', render);
    const remaining = Date.parse(status.dataset.deadline) - Date.now();
    if (remaining > 0 && remaining < 2147483647) setTimeout(render, remaining + 50);
    render();
  });
})();
