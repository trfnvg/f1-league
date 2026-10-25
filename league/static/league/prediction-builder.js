(() => {
  const form = document.querySelector('[data-prediction-builder]');
  if (!form) return;
  const names = ['p1', 'p2', 'p3'];
  const podium = names.map(name => form.elements.namedItem(name));
  if (podium.some(field => !field)) return;
  const slots = form.querySelector('[data-podium-slots]');
  const grid = form.querySelector('[data-driver-grid]');
  const more = form.querySelector('[data-more-predictions]');
  const error = form.querySelector('[data-podium-error]');
  const labels = ['Победитель', 'Второе место', 'Третье место'];
  const summaryLabels = {p1: 'Первое место', p2: 'Второе место', p3: 'Третье место', pole: 'Поул', fastest_lap: 'Быстрый круг', driver_of_day: 'Гонщик дня', safety_car_count: 'Safety Car', dnf_count: 'Сходы (DNF)', crazy_prediction: 'Crazy Prediction', sprint_qualifying_winner: 'Квалификация к спринту', sprint_winner: 'Победитель спринта'};
  const fields = [...form.querySelectorAll('select,input,textarea')].filter(field => summaryLabels[field.name]);
  const initialValues = fields.map(field => field.value);
  const savedBadge = form.closest('.event-page').querySelector('.event-status-badge.is-saved');
  let active = Math.max(0, podium.findIndex(field => !field.value));
  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function valueText(field) {
    if (!field.value.trim()) return '—';
    return field.tagName === 'SELECT' ? field.selectedOptions[0].textContent.replace(/\s*\([^)]*\)$/, '') : field.value;
  }
  const slotButtons = podium.map((field, index) => {
    const button = element('button', 'prediction-podium-slot');
    button.type = 'button';
    button.append(element('small', '', `P${index + 1} / ${labels[index]}`), element('strong'), element('span'));
    button.addEventListener('click', () => { active = index; render(); });
    slots.append(button);
    return button;
  });
  const driverButtons = [...podium[0].options].filter(option => option.value).map(option => {
    const button = element('button', 'prediction-driver-option');
    button.type = 'button';
    button.dataset.driver = option.value;
    const match = option.textContent.match(/^(.*?)\s*\((.*?)\)$/);
    const name = match ? match[1] : option.textContent;
    const team = match ? match[2] : '';
    const meta = element('span', 'prediction-driver-meta');
    meta.append(element('strong', '', name), element('small', '', team));
    button.append(element('span', 'prediction-driver-monogram', name.slice(0, 2).toUpperCase()), meta, element('span', 'prediction-driver-mark'));
    button.addEventListener('click', () => {
      podium[active].value = option.value;
      podium[active].dispatchEvent(new Event('change', {bubbles: true}));
      const next = podium.findIndex(field => !field.value);
      if (next >= 0) { active = next; slotButtons[next].focus({preventScroll: true}); }
      render();
    });
    grid.append(button);
    return button;
  });
  const summary = form.querySelector('[data-summary-lines]');
  const summaryValues = fields.map(field => {
    const line = element('div');
    const value = element('dd');
    line.append(element('dt', '', summaryLabels[field.name]), value);
    summary.append(line);
    return value;
  });
  function render() {
    slotButtons.forEach((button, index) => {
      button.setAttribute('aria-pressed', String(active === index));
      button.querySelector('strong').textContent = valueText(podium[index]) === '—' ? 'Выбери пилота' : valueText(podium[index]);
      button.querySelector('span').textContent = active === index ? 'Выбираешь сейчас' : podium[index].value ? 'Выбрано' : 'Не выбрано';
    });
    form.querySelector('[data-active-place]').textContent = `Сейчас выбираешь: ${labels[active].toLowerCase()}`;
    driverButtons.forEach(button => {
      const taken = podium.findIndex(field => field.value === button.dataset.driver);
      button.disabled = taken >= 0 && taken !== active;
      button.setAttribute('aria-pressed', String(taken === active));
      button.querySelector('.prediction-driver-mark').textContent = taken >= 0 ? `P${taken + 1}` : '';
    });
    let filled = 0;
    fields.forEach((field, i) => {
      const hasValue = field.value.trim() !== '';
      filled += Number(hasValue);
      summaryValues[i].textContent = valueText(field);
      summaryValues[i].classList.toggle('is-empty', !hasValue);
    });
    form.querySelector('[data-prediction-progress]').textContent = `${filled} из ${fields.length} ответов заполнено`;
    const bar = form.querySelector('[data-progress-bar]');
    bar.max = fields.length;
    bar.value = filled;
    if (savedBadge) savedBadge.textContent = fields.some((field, i) => field.value !== initialValues[i]) ? 'Есть изменения' : 'Прогноз сохранён';
    if (podium.every(field => field.value) && new Set(podium.map(field => field.value)).size === 3) error.hidden = true;
  }
  form.addEventListener('input', render);
  form.addEventListener('change', render);
  form.addEventListener('invalid', () => { more.open = true; }, true);
  form.addEventListener('submit', event => {
    const missing = podium.findIndex(field => !field.value);
    if (missing >= 0 || new Set(podium.map(field => field.value)).size !== 3) {
      event.preventDefault();
      active = missing >= 0 ? missing : 0;
      error.textContent = 'Выбери трёх разных пилотов для подиума.';
      error.hidden = false;
      render();
      slotButtons[active].focus();
    }
  });
  render();
  podium.forEach(field => { field.required = false; });
  form.querySelector('[data-native-podium]').hidden = true;
  slots.hidden = false;
  form.querySelector('[data-driver-picker]').hidden = false;
  form.querySelector('[data-live-summary]').hidden = false;
  form.querySelector('[data-fallback-submit]').hidden = true;
  if (!form.querySelector('.errorlist,.alert-danger') && !fields.some(field => !names.includes(field.name) && field.tagName === 'SELECT' && field.value)) more.open = false;
})();
