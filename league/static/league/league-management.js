(() => {
  const tools = document.querySelector('[data-member-tools]');
  if (tools) {
    const search = tools.querySelector('[data-member-search]');
    const filter = tools.querySelector('[data-member-filter]');
    const status = tools.querySelector('[data-member-status]');
    const empty = document.querySelector('[data-member-empty]');
    const normalize = value => value.normalize('NFKC').toLocaleLowerCase('ru').replace(/ё/g, 'е').trim();
    const rows = [...document.querySelectorAll('[data-member-row]')].map(row => ({
      row, name: normalize(row.querySelector('[data-member-name]').textContent),
      handle: normalize(row.querySelector('[data-member-handle]')?.textContent || ''),
    }));
    const update = () => {
      const query = normalize(search.value).replace(/^@/, '');
      let visible = 0;
      rows.forEach(({row, name, handle}) => {
        row.hidden = !((!filter.value || row.dataset.memberRole === filter.value) &&
          (!query || name.includes(query) || handle.includes(query)));
        if (!row.hidden) visible++;
      });
      empty.hidden = visible > 0 || rows.length === 0;
      status.textContent = `Показано ${visible} из ${rows.length}`;
    };
    search.addEventListener('input', update);
    filter.addEventListener('change', update);
    window.addEventListener('pageshow', update);
    tools.hidden = false;
    update();
  }
  document.querySelectorAll('[data-role-form]').forEach(roleForm => {
    const select = roleForm.querySelector('select');
    const submit = roleForm.querySelector('button');
    const sync = () => { submit.disabled = select.value === select.dataset.originalRole; };
    select.addEventListener('change', sync);
    window.addEventListener('pageshow', sync);
    sync();
    roleForm.addEventListener('submit', event => {
      const name = roleForm.closest('[data-member-row]').querySelector('[data-member-name]').textContent.trim();
      const label = select.selectedOptions[0].textContent.trim();
      if (select.value === select.dataset.originalRole || !window.confirm(`Изменить роль участника «${name}» на «${label}»?`)) {
        event.preventDefault();
      }
    });
  });
  const form = document.querySelector('[data-league-profile-form]');
  if (!form) return;
  const input = form.querySelector('[data-logo-input]');
  const clear = form.querySelector('[data-logo-clear]');
  const preview = form.querySelector('[data-logo-preview]');
  const image = preview.querySelector('[data-logo-image]');
  const placeholder = preview.querySelector('[data-logo-placeholder]');
  const button = form.querySelector('[data-logo-button]');
  const filename = form.querySelector('[data-logo-filename]');
  let temporary = null;
  form.classList.add('is-enhanced');
  button.hidden = false;
  filename.hidden = false;
  function release() {
    if (temporary) URL.revokeObjectURL(temporary);
    temporary = null;
  }
  function show(source) {
    if (source) { image.src = source; image.hidden = false; placeholder.hidden = true; }
    else { image.removeAttribute('src'); image.hidden = true; placeholder.hidden = false; }
  }
  input.addEventListener('change', () => {
    release();
    const file = input.files && input.files[0];
    filename.textContent = file ? file.name : 'Файл не выбран';
    if (file && clear) clear.checked = false;
    if (file && ['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
      temporary = URL.createObjectURL(file);
      show(temporary);
    } else show(preview.dataset.original);
  });
  if (clear) clear.addEventListener('change', () => {
    if (clear.checked) { input.value = ''; filename.textContent = 'Файл не выбран'; release(); show(''); }
    else show(preview.dataset.original);
  });
  window.addEventListener('pagehide', release);
  window.addEventListener('pageshow', event => {
    if (event.persisted && input.files && input.files[0]) input.dispatchEvent(new Event('change'));
  });
})();
