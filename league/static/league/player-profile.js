(() => {
  const input = document.querySelector('#avatarUploadForm input[type="file"]');
  const form = document.getElementById('avatarUploadForm');
  const button = document.getElementById('avatarMenuButton');
  const menu = document.getElementById('avatarUploadMenu');
  const upload = document.getElementById('avatarUploadAction');
  if (!input || !form || !button || !menu || !upload) return;
  function show(open) { menu.hidden = !open; button.setAttribute('aria-expanded', String(open)); }
  button.addEventListener('click', event => { event.stopPropagation(); show(menu.hidden); });
  menu.addEventListener('click', event => event.stopPropagation());
  upload.addEventListener('click', () => { show(false); input.click(); });
  document.querySelector('[data-change-avatar]')?.addEventListener('click', () => input.click());
  document.addEventListener('click', () => show(false));
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !menu.hidden) { show(false); button.focus(); } });
  input.addEventListener('change', () => { if (input.files.length) form.requestSubmit(); });
})();
