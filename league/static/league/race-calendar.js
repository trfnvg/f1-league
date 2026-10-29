(() => {
  'use strict';
  const calendar = document.querySelector('[data-race-calendar]');
  if (!calendar) return;
  const timezoneControl = calendar.querySelector('[data-calendar-timezone]');
  const selector = calendar.querySelector('#calendar-timezone');
  const times = [...calendar.querySelectorAll('[data-calendar-time]')];
  const zoneNote = calendar.querySelector('[data-calendar-zone-note]');
  const deviceZone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Moscow';
  const savedKey = 'fastlap:calendar:timezone';
  function updateTimezone() {
    const value = selector.value;
    times.forEach(time => {
      const zone = value === 'device' ? deviceZone : value === 'venue' ? time.dataset.venue : 'Europe/Moscow';
      const date = new Date(time.dateTime);
      const parts = new Intl.DateTimeFormat('ru-RU', {
        timeZone: zone, day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
      }).formatToParts(date);
      const get = type => parts.find(part => part.type === type)?.value || '';
      time.textContent = `${get('day')}.${get('month')} · ${get('hour')}:${get('minute')}`;
      time.title = `${zone} · ${date.toISOString()}`;
    });
    calendar.querySelectorAll('[data-calendar-zone-badge]').forEach(label => {
      label.textContent = value === 'venue' ? 'МЕСТНОЕ' : value === 'device' ? deviceZone.split('/').pop().replaceAll('_', ' ') : 'МСК';
    });
    zoneNote.textContent = value === 'venue'
      ? 'Время сессий и даты уик-эндов — по месту проведения.'
      : value === 'device'
        ? `Время сессий — ${deviceZone}. Даты уик-эндов — по месту проведения.`
        : 'Время сессий — московское (UTC+3). Даты уик-эндов — по месту проведения.';
    try { localStorage.setItem(savedKey, value); } catch (_) { /* Storage may be disabled. */ }
  }
  if (timezoneControl && selector && typeof Intl.DateTimeFormat === 'function') {
    try {
      const saved = localStorage.getItem(savedKey);
      if (['Europe/Moscow', 'device', 'venue'].includes(saved)) selector.value = saved;
    } catch (_) { /* Server-rendered Moscow time is always available. */ }
    updateTimezone();
    timezoneControl.hidden = false;
    selector.addEventListener('change', updateTimezone);
  }
  const filters = calendar.querySelector('[data-calendar-filters]');
  const cards = [...calendar.querySelectorAll('[data-calendar-round]')];
  const months = [...calendar.querySelectorAll('[data-calendar-month]')];
  if (filters) {
    filters.hidden = false;
    function applyFilter(filter) {
      filters.querySelectorAll('button').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.filter === filter)));
      cards.forEach(card => { card.hidden = filter === 'upcoming' && card.dataset.finished === 'true'; });
      months.forEach(month => {
        month.hidden = ![...month.querySelectorAll('[data-calendar-round]')].some(card => !card.hidden);
        const anchor = calendar.querySelector(`.rc-month-nav a[href="#${month.id}"]`);
        if (anchor) anchor.hidden = month.hidden;
      });
      calendar.querySelector('[data-calendar-empty]').hidden = cards.some(card => !card.hidden);
    }
    filters.addEventListener('click', event => {
      const button = event.target.closest('[data-filter]');
      if (button) applyFilter(button.dataset.filter);
    });
    applyFilter('upcoming');
  }
})();
