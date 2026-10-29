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
    const receipt = !!document.querySelector('[data-save-receipt]') && !invalid && status.dataset.saved === 'yes';
    const buttons = [...form.querySelectorAll('button[type="submit"]')];
    const buttonLabels = new Map(buttons.map(button => [button, button.textContent]));
    const badge = form.closest('.event-page')?.querySelector('.event-status-badge');
    let sending = false;
    let confirmed = receipt;
    const setText = (node, text) => { if (node.textContent !== text) node.textContent = text; };
    const setState = state => {
      if (status.dataset.state !== state) status.dataset.state = state;
      if (form.dataset.saveState !== state) form.dataset.saveState = state;
      buttons.forEach(button => {
        const text = state === 'sending' ? 'Сохраняем…' : state === 'confirmed' ? 'Прогноз принят' : buttonLabels.get(button);
        // Replacing an unchanged label during textarea blur can cancel a tap in WebKit.
        if (button.textContent !== text) button.textContent = text;
        const disabled = String(state === 'sending');
        if (button.getAttribute('aria-disabled') !== disabled) button.setAttribute('aria-disabled', disabled);
      });
    };
    const dirty = () => invalid || values() !== initial;
    const warn = event => { if (dirty() && !sending) { event.preventDefault(); event.returnValue = ''; } };
    const render = () => {
      const changed = dirty();
      window.removeEventListener('beforeunload', warn);
      if (changed) window.addEventListener('beforeunload', warn);
      if (changed) confirmed = false;
      if (Date.now() >= Date.parse(status.dataset.deadline)) {
        setState('locked');
        setText(label, 'Прогнозы зафиксированы');
        setText(note, changed ? 'Изменения на этой странице не сохранены. Дедлайн уже прошёл.' : 'Приём прогнозов завершён.');
      } else {
        setState(changed ? 'dirty' : confirmed ? 'confirmed' : status.dataset.saved === 'yes' ? 'saved' : 'empty');
        setText(label, changed ? 'Есть несохранённые изменения' : confirmed ? 'Прогноз принят' : originalLabel);
        setText(note, changed ? 'Нажми «Сохранить прогноз», чтобы ответы попали в зачёт.' : originalNote);
      }
      if (badge) setText(badge, label.textContent);
    };
    form.addEventListener('input', render);
    form.addEventListener('change', render);
    form.addEventListener('submit', event => {
      if (sending) { event.preventDefault(); return; }
    });
    // Run after form-level validation, including the driver picker's cancellation.
    // A microtask can run between event listeners in WebKit.
    window.addEventListener('submit', event => {
      if (event.target !== form || event.defaultPrevented) return;
      sending = true;
      setState('sending');
      label.textContent = 'Сохраняем прогноз…';
      note.textContent = 'Дождись подтверждения от сервера.';
    });
    window.addEventListener('pageshow', event => {
      sending = false;
      if (event.persisted) confirmed = false;
      render();
    });
    document.addEventListener('visibilitychange', render);
    const remaining = Date.parse(status.dataset.deadline) - Date.now();
    if (remaining > 0 && remaining < 2147483647) setTimeout(render, remaining + 50);
    render();
    if (receipt) setTimeout(() => { confirmed = false; if (!sending) render(); }, 2400);
  });
})();
