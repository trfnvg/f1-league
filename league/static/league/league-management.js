(() => {
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
