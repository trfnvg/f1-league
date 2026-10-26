(() => {
  'use strict';
  const init = () => {
    const select = document.getElementById('id_circuit');
    const preview = document.querySelector('[data-circuit-preview]');
    const name = document.getElementById('id_name');
    if (!select || !preview) return;
    let autoName = '';
    const update = (fillName) => {
      const option = select.selectedOptions[0];
      const data = option ? option.dataset : {};
      preview.hidden = !data.circuitPath;
      const placeholder = document.querySelector('[data-circuit-placeholder]');
      if (placeholder) placeholder.hidden = !!data.circuitPath;
      if (!data.circuitPath) return;
      preview.querySelectorAll('path').forEach(path => path.setAttribute('d', data.circuitPath));
      preview.querySelectorAll('.circuit-start,.circuit-start-ring').forEach(circle => {
        circle.setAttribute('cx', data.circuitStartX); circle.setAttribute('cy', data.circuitStartY);
      });
      const svg = preview.querySelector('svg');
      svg.setAttribute('aria-label', `Схема трассы ${data.circuitName}`);
      svg.setAttribute('data-circuit', select.value);
      svg.querySelector('title').textContent = data.circuitName;
      const labels = JSON.parse(data.circuitLabels || '[]');
      svg.querySelectorAll('.circuit-label').forEach((label, i) => {
        if (!labels[i]) return;
        label.setAttribute('x', labels[i].x);
        label.setAttribute('y', labels[i].y);
        label.textContent = labels[i].text;
      });
      if (svg.setCurrentTime) svg.setCurrentTime(0);
      svg.dispatchEvent(new Event('circuit:changed'));
      preview.querySelector('[data-circuit-caption]').textContent = data.circuitName;
      if (fillName && name && (!name.value.trim() || name.value === autoName)) {
        name.value = data.circuitGp; autoName = data.circuitGp;
      }
    };
    select.addEventListener('change', () => update(true));
    update(false);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
