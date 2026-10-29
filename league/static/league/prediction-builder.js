(() => {
  const form = document.querySelector('[data-prediction-builder]');
  if (!form) return;
  const names = ['p1', 'p2', 'p3'];
  const podium = names.map(name => form.elements.namedItem(name));
  if (podium.some(field => !field)) return;
  const slots = form.querySelector('[data-podium-slots]');
  const dialog = document.getElementById('driver-picker-dialog');
  if (!dialog || !dialog.showModal) return;
  const profiles = new Map(JSON.parse(document.getElementById('driver-picker-profiles').textContent).map(driver => [driver.key, driver]));
  const options = dialog.querySelector('[data-picker-options]');
  const search = dialog.querySelector('[data-picker-search]');
  const driverFields = [...form.querySelectorAll('select')];
  const requiredFields = driverFields.filter(field => field.required);
  const categoryButtons = new Map();
  const renderedDrivers = new WeakMap();
  let targetField = null;
  const error = form.querySelector('[data-podium-error]');
  const labels = ['Победитель', 'Второе место', 'Третье место'];
  const summaryLabels = {p1: 'Первое место', p2: 'Второе место', p3: 'Третье место', pole: 'Поул', fastest_lap: 'Быстрый круг', driver_of_day: 'Гонщик дня', safety_car_count: 'Safety Car', dnf_count: 'Сходы (DNF)', crazy_prediction: 'Crazy Prediction', sprint_qualifying_winner: 'Квалификация к спринту', sprint_winner: 'Победитель спринта'};
  const fields = [...form.querySelectorAll('select,input,textarea')].filter(field => summaryLabels[field.name]);
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
  function teamLabel(profile, fallback) {
    const label = element('small', profile?.team ? 'driver-team-name' : '', profile?.team || fallback);
    if (profile?.team_color) label.style.color = profile.team_color;
    return label;
  }
  const slotButtons = podium.map((field, index) => {
    const button = element('button', 'prediction-podium-slot');
    button.type = 'button';
    button.addEventListener('click', () => openPicker(field));
    button.setAttribute('aria-haspopup', 'dialog');
    button.setAttribute('aria-controls', dialog.id);
    const wrapper = element('div', 'prediction-podium-field');
    wrapper.append(element('span', 'form-label', `P${index + 1} · ${labels[index]}`), button);
    slots.append(wrapper);
    return button;
  });
  function portrait(profile, fallbackName) {
    const wrapper = element('span', 'driver-choice-photo');
    wrapper.append(element('span', '', (profile?.surname || fallbackName).slice(0, 2).toUpperCase()));
    if (profile?.photo) {
      const image = element('img');
      image.src = profile.photo;
      image.alt = '';
      image.loading = 'lazy';
      image.referrerPolicy = 'no-referrer';
      image.addEventListener('error', () => { image.hidden = true; });
      wrapper.append(image);
    }
    return wrapper;
  }
  function openPicker(field) {
    targetField = field;
    search.value = '';
    dialog.querySelector('[data-picker-category]').textContent = summaryLabels[field.name];
    filterDrivers();
    dialog.showModal();
    document.documentElement.classList.add('driver-picker-open');
    if (window.matchMedia('(pointer:fine)').matches) search.focus();
  }
  function filterDrivers() {
    const query = search.value.trim().toLocaleLowerCase().replace(/^#/, '');
    options.replaceChildren();
    for (const option of targetField.options) {
      if (!option.value) continue;
      const profile = profiles.get(option.value);
      const match = option.textContent.match(/^(.*?)\s*\((.*?)\)$/);
      const surname = profile?.surname || (match ? match[1] : option.textContent);
      const team = profile?.team || (match ? match[2] : '');
      if (query && ![profile?.name, surname, team, profile?.number, option.value].join(' ').toLocaleLowerCase().includes(query)) continue;
      const button = element('button', 'driver-choice');
      button.type = 'button';
      button.dataset.driver = option.value;
      const index = names.includes(targetField.name) ? podium.findIndex(field => field !== targetField && field.value === option.value) : -1;
      button.disabled = index >= 0;
      button.setAttribute('aria-pressed', String(targetField.value === option.value));
      const meta = element('span', 'driver-choice-meta');
      meta.append(element('strong', '', surname), teamLabel(profile, team));
      if (index >= 0) meta.append(element('small', '', 'Уже выбран на P' + (index + 1)));
      button.append(portrait(profile, surname), meta, element('span', 'driver-choice-number', profile ? '#' + profile.number : ''));
      button.addEventListener('click', () => {
        targetField.value = option.value;
        targetField.dispatchEvent(new Event('change', {bubbles: true}));
        dialog.close();
      });
      options.append(button);
    }
    dialog.querySelector('[data-picker-empty]').hidden = options.childElementCount > 0;
  }
  search.addEventListener('input', filterDrivers);
  dialog.querySelector('[data-picker-close]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => { if (!dialog.open) document.documentElement.classList.remove('driver-picker-open'); });
  dialog.addEventListener('click', event => { if (event.target === dialog) {
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
  }});
  driverFields.filter(field => !names.includes(field.name)).forEach(field => {
    const button = element('button', 'prediction-category-choice');
    button.type = 'button';
    button.dataset.driverField = field.name;
    button.id = field.id + '-picker';
    const label = form.querySelector(`label[for="${field.id}"]`);
    if (label) label.htmlFor = button.id;
    button.setAttribute('aria-haspopup', 'dialog');
    button.setAttribute('aria-controls', dialog.id);
    button.addEventListener('click', () => openPicker(field));
    field.insertAdjacentElement('afterend', button);
    categoryButtons.set(field.name, button);
  });
  const summary = form.querySelector('[data-summary-lines]');
  const summaryValues = fields.map(field => {
    const line = element('div');
    const value = element('dd');
    line.append(element('dt', '', summaryLabels[field.name]), value);
    summary.append(line);
    return value;
  });
  const progress = form.querySelector('[data-prediction-progress]');
  const bar = form.querySelector('[data-progress-bar]');
  bar.max = fields.length;
  function render(event) {
    // Typing in one answer must not recreate portraits in unrelated categories.
    // A native select may emit both input and change for the same value.
    const changedField = event?.target;
    fields.forEach((field, i) => {
      if (changedField && changedField !== field) return;
      const index = podium.indexOf(field);
      const button = index >= 0 ? slotButtons[index] : categoryButtons.get(field.name);
      if (button) {
        if (renderDriverButton(button, field) && index >= 0) {
          button.setAttribute('aria-label', `${labels[index]}: ${valueText(field)}`);
        }
        if (field.value && button.hasAttribute('aria-invalid')) button.removeAttribute('aria-invalid');
      }
      const hasValue = field.value.trim() !== '';
      const text = valueText(field);
      if (summaryValues[i].textContent !== text) summaryValues[i].textContent = text;
      summaryValues[i].classList.toggle('is-empty', !hasValue);
    });
    const filled = fields.filter(field => field.value.trim() !== '').length;
    const progressText = `${filled} из ${fields.length} ответов заполнено`;
    if (progress.textContent !== progressText) progress.textContent = progressText;
    if (bar.value !== filled) bar.value = filled;
    if (!error.hidden && podium.every(field => field.value) && new Set(podium.map(field => field.value)).size === 3) error.hidden = true;
  }
  function renderDriverButton(button, field) {
    if (renderedDrivers.get(button) === field.value) return false;
    const profile = profiles.get(field.value);
    const name = field.value ? valueText(field) : 'Выбери гонщика';
    const meta = element('span', 'driver-choice-meta');
    meta.append(element('strong', '', name), teamLabel(profile, field.value ? 'Выбрано' : 'Не выбрано'));
    button.replaceChildren(portrait(profile, valueText(field)), meta);
    renderedDrivers.set(button, field.value);
    return true;
  }
  form.addEventListener('input', render);
  form.addEventListener('change', render);
  form.addEventListener('submit', event => {
    const missing = podium.findIndex(field => !field.value);
    if (missing >= 0 || new Set(podium.map(field => field.value)).size !== 3) {
      event.preventDefault();
      const focusIndex = missing >= 0 ? missing : 0;
      error.textContent = 'Выбери трёх разных пилотов для подиума.';
      error.hidden = false;
      render();
      slotButtons[focusIndex].focus();
    } else {
      const missingField = requiredFields.find(field => !field.value);
      if (missingField) {
        event.preventDefault();
        const button = categoryButtons.get(missingField.name);
        button.setAttribute('aria-invalid', 'true');
        button.focus();
        openPicker(missingField);
      }
    }
  });
  render();
  driverFields.forEach(field => { field.required = false; field.hidden = true; });
  form.querySelector('[data-native-podium]').hidden = true;
  slots.hidden = false;

  form.querySelector('[data-live-summary]').hidden = false;
  form.querySelector('[data-fallback-submit]').hidden = true;
})();
