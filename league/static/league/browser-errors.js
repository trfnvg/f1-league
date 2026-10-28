/* First-party diagnostics only: never send error messages, form data or URLs. */
(() => {
  'use strict';
  const configNode = document.getElementById('browser-monitoring-config');
  if (!configNode) return;
  const config = JSON.parse(configNode.textContent);
  const seen = new Set();
  const errorTypes = new Set(['Error', 'TypeError', 'ReferenceError', 'SyntaxError', 'RangeError', 'URIError', 'EvalError']);
  let count = 0;

  function send(kind, source, line, column, name) {
    if (count >= 3 || !source) return;
    let url;
    try { url = new URL(source, location.href); } catch (_) { return; }
    // Ignore browser extensions, third-party widgets, API URLs and dynamic code.
    if (url.origin !== location.origin || !url.pathname.startsWith('/static/league/')) return;
    const asset = url.pathname.split('/').pop();
    if (!/^[a-zA-Z0-9_.-]{1,100}\.js$/.test(asset)) return;
    const report = {
      asset, line: Number.isInteger(line) ? Math.min(1000000, Math.max(0, line)) : 0,
      column: Number.isInteger(column) ? Math.min(1000000, Math.max(0, column)) : 0,
      kind, error_type: errorTypes.has(name) ? name : 'Error',
      viewport: innerWidth <= 760 ? 'mobile' : 'desktop'
    };
    const key = JSON.stringify(report);
    if (seen.has(key)) return;
    seen.add(key);
    count++;
    // No retries and no errors thrown by the reporter itself.
    fetch(config.endpoint, {
      method: 'POST', mode: 'same-origin', credentials: 'same-origin', keepalive: true,
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': config.csrf },
      body: key
    }).catch(() => {});
  }

  addEventListener('error', event => {
    send('error', event.filename, event.lineno, event.colno, event.error?.name);
  });
  addEventListener('unhandledrejection', event => {
    // Parse locations only; do not transmit the rejection value or stack text.
    const reason = event.reason;
    if (!(reason instanceof Error) || typeof reason.stack !== 'string') return;
    const locations = reason.stack.matchAll(/(https?:\/\/[^\s()]+?\.js(?:\?[^\s():]*)?):(\d+):(\d+)/g);
    for (const match of locations) {
      if (match[1].startsWith(location.origin + '/static/league/')) {
        send('unhandledrejection', match[1], Number(match[2]), Number(match[3]), reason.name);
        break;
      }
    }
  });
})();
