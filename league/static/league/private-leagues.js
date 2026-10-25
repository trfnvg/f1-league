(() => {
  'use strict';
  const button=document.querySelector('[data-copy-invite]');
  if(button)button.addEventListener('click',async()=>{
    const input=document.getElementById('league-invite-link'),status=document.querySelector('[data-copy-status]');
    try {await navigator.clipboard.writeText(input.value);status.textContent='Ссылка скопирована. Отправьте её друзьям.';}
    catch {input.focus();input.select();status.textContent='Выделили ссылку — скопируйте её вручную.';}
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
