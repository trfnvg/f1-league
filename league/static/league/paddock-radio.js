(() => {
  const list = document.getElementById('live-paddock-list');
  if (!list) return;
  const radio = list.closest('.ns-live');
  const toggle = radio.querySelector('.paddock-radio-toggle');
  let expanded = false;
  let refreshing = false;
  let lastHTML = list.innerHTML;

  function render() {
    const items = [...list.querySelectorAll('.activity-news-item')];
    items.forEach((item, index) => { item.hidden = !expanded && index >= 3; });
    toggle.hidden = items.length <= 3;
    toggle.setAttribute('aria-expanded', String(expanded));
    toggle.querySelector('[data-radio-toggle-label]').textContent = expanded ? 'Свернуть' : `Ещё ${Math.max(0, items.length - 3)}`;
  }
  toggle.addEventListener('click', () => { expanded = !expanded; render(); });
  render();

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
      if (typeof data.html === 'string' && lastHTML !== data.html && !list.contains(document.activeElement)) {
        list.innerHTML = data.html;
        lastHTML = data.html;
        render();
      }
    } catch (_) {
      // A failed poll leaves the messages and expanded state intact.
    } finally {
      refreshing = false;
    }
  }
  window.setInterval(refresh, 15000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) void refresh(); });
})();
