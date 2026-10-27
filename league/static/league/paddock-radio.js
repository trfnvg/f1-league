(() => {
  const list = document.getElementById('live-paddock-list');
  if (!list) return;
  const radio = list.closest('.ns-live');
  const toggle = radio.querySelector('.paddock-radio-toggle');
  let expanded = false;
  let refreshing = false;
  let lastHTML = list.innerHTML;
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  radio.classList.add('is-radio-ready');
  const storageKey = `fastlap:radio:v1:${list.dataset.feedUrl}`;
  let seen = [];
  try {
    const stored = JSON.parse(sessionStorage.getItem(storageKey) || '[]');
    if (Array.isArray(stored)) seen = stored;
  } catch (_) {}
  const pending = new Set();
  let pulseTimer;

  function registerMessages() {
    const items = [...list.querySelectorAll('.activity-news-item')];
    const currentKeys = new Set(items.map(item => item.dataset.radioKey));
    pending.forEach(key => { if (!currentKeys.has(key)) pending.delete(key); });
    items.forEach((item, index) => {
      if (!seen.includes(item.dataset.radioKey) && (seen.length || index === 0)) {
        pending.add(item.dataset.radioKey);
        item.classList.add('is-unread');
      }
    });
    seen = [...new Set([...seen, ...items.map(item => item.dataset.radioKey)])].slice(-40);
    try { sessionStorage.setItem(storageKey, JSON.stringify(seen)); } catch (_) {}
  }

  function transmit() {
    if (document.hidden || motion.matches) return;
    const area = radio.getBoundingClientRect();
    if (area.bottom <= 0 || area.top >= innerHeight) return;
    let received = false;
    list.querySelectorAll('.activity-news-item').forEach(item => {
      if (!pending.has(item.dataset.radioKey) || item.closest('.radio-transmission').hidden) return;
      pending.delete(item.dataset.radioKey);
      item.classList.add('is-transmitting');
      received = true;
    });
    if (!received) return;
    radio.classList.add('is-receiving');
    clearTimeout(pulseTimer);
    pulseTimer = setTimeout(() => {
      radio.classList.remove('is-receiving');
      list.querySelectorAll('.is-transmitting').forEach(item => item.classList.remove('is-transmitting'));
    }, 1400);
  }

  function updateDisclosure(item) {
    const copy = item.querySelector('.activity-news-copy>strong');
    const button = item.nextElementSibling;
    button.hidden = !item.classList.contains('is-open') && copy.scrollHeight <= copy.clientHeight + 1;
  }

  function render() {
    const items = [...list.querySelectorAll('.activity-news-item')];
    items.forEach((item, index) => {
      item.closest('.radio-transmission').hidden = !expanded && index >= 3;
      updateDisclosure(item);
    });
    toggle.hidden = items.length <= 3;
    toggle.setAttribute('aria-expanded', String(expanded));
    toggle.querySelector('[data-radio-toggle-label]').textContent = expanded ? 'Свернуть' : `Ещё ${Math.max(0, items.length - 3)}`;
    transmit();
  }
  list.addEventListener('click', event => {
    const button = event.target.closest('.radio-message-open');
    const item = button ? button.previousElementSibling : event.target.closest('.activity-news-item');
    if (!item) return;
    item.classList.remove('is-unread');
    if (!button) return;
    const opened = item.classList.toggle('is-open');
    button.setAttribute('aria-expanded', String(opened));
    button.textContent = opened ? 'Свернуть сообщение' : 'Читать сообщение';
    updateDisclosure(item);
  });
  toggle.addEventListener('click', () => { expanded = !expanded; render(); });
  registerMessages();
  render();
  if ('IntersectionObserver' in window) new IntersectionObserver(transmit, {threshold: .2}).observe(radio);
  if ('ResizeObserver' in window) new ResizeObserver(render).observe(list);

  async function refresh() {
    if (refreshing || document.hidden) return;
    refreshing = true;
    try {
      const response = await fetch(list.dataset.feedUrl, {
        credentials: 'same-origin', cache: 'no-store',
        headers: {'X-Requested-With': 'XMLHttpRequest'},
      });
      if (!response.ok) return;
      const data = await response.json();
      // Don't replace an active link while somebody is using the keyboard.
      if (typeof data.html === 'string' && lastHTML !== data.html && !list.contains(document.activeElement)
          && !list.querySelector('.is-open')) {
        list.innerHTML = data.html;
        lastHTML = data.html;
        registerMessages();
        render();
      }
    } catch (_) {
      // A failed poll leaves the messages and expanded state intact.
    } finally {
      refreshing = false;
    }
  }
  window.setInterval(refresh, 15000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) { transmit(); void refresh(); } });
})();
