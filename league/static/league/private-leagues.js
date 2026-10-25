(() => {
  'use strict';
  const button=document.querySelector('[data-copy-invite]');
  if(!button)return;
  button.addEventListener('click',async()=>{
    const input=document.getElementById('league-invite-link'),status=document.querySelector('[data-copy-status]');
    try {await navigator.clipboard.writeText(input.value);status.textContent='Ссылка скопирована. Отправьте её друзьям.';}
    catch {input.focus();input.select();status.textContent='Выделили ссылку — скопируйте её вручную.';}
  });
})();
