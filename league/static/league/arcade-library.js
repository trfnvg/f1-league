(() => {
  const featured = document.querySelector("[data-contest-deadline]");
  if (!featured) return;
  const deadline = Date.parse(featured.dataset.contestDeadline);
  const serverTime = Date.parse(featured.dataset.serverTime);
  if (!Number.isFinite(deadline) || !Number.isFinite(serverTime)) return;
  const started = Date.now();
  let timer;
  function checkDeadline() {
    window.clearTimeout(timer);
    const remaining = deadline - (serverTime + Date.now() - started);
    if (remaining <= 0) {
      if (featured.contains(document.activeElement)) {
        const title = document.querySelector(".library-section-heading h2");
        if (title) {
          title.tabIndex = -1;
          title.focus({preventScroll: true});
        }
      }
      featured.remove();
      document.removeEventListener("visibilitychange", checkDeadline);
      window.removeEventListener("pageshow", checkDeadline);
      return;
    }
    timer = window.setTimeout(checkDeadline, Math.min(remaining, 86400000));
  }
  document.addEventListener("visibilitychange", checkDeadline);
  window.addEventListener("pageshow", checkDeadline);
  checkDeadline();
})();
