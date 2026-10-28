(() => {
  'use strict';
  document.querySelectorAll('[data-confirm-invite-rotation]').forEach(form=>form.addEventListener('submit',event=>{
    if(!window.confirm('Обновить ссылку? Все прежние ссылки перестанут работать. Участники останутся в лиге.'))event.preventDefault();
  }));
  const button=document.querySelector('[data-copy-invite]');
  if(button)button.addEventListener('click',async()=>{
    const input=document.getElementById('league-invite-link'),status=document.querySelector('[data-copy-status]');
    const url=input.value || input.href;
    try {await navigator.clipboard.writeText(url);status.textContent='Ссылка скопирована. Отправьте её друзьям.';}
    catch {
      input.focus();
      if(typeof input.select==='function')input.select();
      else {const range=document.createRange();range.selectNodeContents(input);const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);}
      status.textContent='Выделили ссылку — скопируйте её вручную.';
    }
  });
  const official=document.getElementById('id_use_official');
  if(official){
    const choices=[...document.querySelectorAll('#id_drivers input')];
    const sync=()=>choices.forEach(input=>{input.disabled=official.checked;});
    official.addEventListener('change',sync);sync();
  }
  document.querySelectorAll('.league-switch').forEach(menu=>{
    document.addEventListener('click',event=>{if(!menu.contains(event.target))menu.open=false;});
    menu.addEventListener('keydown',event=>{
      if(event.key==='Escape'){menu.open=false;menu.querySelector('summary').focus();}
    });
  });
  document.querySelectorAll('[data-race-cover]').forEach(cover=>{
    const fallback=()=>{cover.hidden=true;};
    cover.addEventListener('error',fallback);
    if(cover.complete&&!cover.naturalWidth)fallback();
  });
})();
