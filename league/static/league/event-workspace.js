(() => {
  const root = document.querySelector('[data-event-workspace]');
  if (!root) return;
  const nav = root.querySelector('.stage-sections');
  const tabs = [...nav.querySelectorAll('a')];
  const panels = tabs.map(tab => document.getElementById(tab.hash.slice(1)));
  if (panels.some(panel => !panel)) return;
  nav.setAttribute('role', 'tablist');
  tabs.forEach((tab, i) => {
    tab.id = `event-tab-${i}`;
    tab.setAttribute('role', 'tab');
    tab.setAttribute('aria-controls', panels[i].id);
    panels[i].setAttribute('role', 'tabpanel');
    panels[i].setAttribute('aria-labelledby', tab.id);
  });
  function activate(index, updateHash = false) {
    tabs.forEach((tab, i) => {
      const selected = i === index;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
      panels[i].hidden = !selected;
    });
    if (updateHash) history.replaceState(null, '', tabs[index].hash);
  }
  function fromLocation() {
    let target;
    try { target = document.getElementById(decodeURIComponent(location.hash.slice(1))); } catch (_) {}
    const index = panels.findIndex(panel => panel === target || (target && panel.contains(target)));
    const fallback = panels.findIndex(panel => panel.id === root.dataset.defaultPanel);
    activate(index >= 0 ? index : Math.max(0, fallback));
    if (target && !panels.includes(target)) target.scrollIntoView({block: 'start'});
  }
  tabs.forEach((tab, i) => {
    tab.addEventListener('click', event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      activate(i, true);
    });
    tab.addEventListener('keydown', event => {
      const next = event.key === 'ArrowRight' ? (i + 1) % tabs.length
        : event.key === 'ArrowLeft' ? (i + tabs.length - 1) % tabs.length
        : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : -1;
      if (next < 0) return;
      event.preventDefault();
      activate(next, true);
      tabs[next].focus();
    });
  });
  window.addEventListener('hashchange', fromLocation);
  fromLocation();
})();
