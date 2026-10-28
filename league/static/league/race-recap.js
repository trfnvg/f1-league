(() => {
  'use strict';
  const canvas = document.querySelector('[data-recap-canvas]');
  if (!canvas) return;
  const data = JSON.parse(document.getElementById('race-recap-data').textContent);
  const ctx = canvas.getContext('2d');
  const download = document.querySelector('[data-recap-download]');
  const share = document.querySelector('[data-recap-share]');
  const status = document.querySelector('[data-recap-status]');
  const sans = 'Inter, system-ui, -apple-system, sans-serif';
  const mono = '"SFMono-Regular", Consolas, monospace';
  const white = '#f5f3ef', muted = '#9ca4b0', red = '#f1544a';
  function text(value, x, y, size, color = white, weight = 600, family = sans) {
    ctx.font = `${weight} ${size}px ${family}`; ctx.fillStyle = color;
    ctx.fillText(String(value), x, y);
  }
  function fit(value, x, y, maxWidth, size, color = white, weight = 600) {
    value = String(value);
    while (size > 16) {ctx.font = `${weight} ${size}px ${sans}`; if (ctx.measureText(value).width <= maxWidth) break; size--;}
    while (ctx.measureText(value).width > maxWidth && value.length > 1) value = value.slice(0, -2) + '…';
    text(value, x, y, size, color, weight);
  }
  function rule(y) {ctx.strokeStyle = '#373b43'; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(68,y);ctx.lineTo(1012,y);ctx.stroke();}
  function box(x,y,w,h,r,fill) {ctx.beginPath();ctx.roundRect(x,y,w,h,r);ctx.fillStyle=fill;ctx.fill();}
  function draw() {
    ctx.fillStyle = '#181c22';ctx.fillRect(0,0,1080,1350);
    const glow = ctx.createLinearGradient(0,0,1080,1350);
    glow.addColorStop(0,'#303038');glow.addColorStop(.48,'#1d2229');glow.addColorStop(1,'#11161b');
    ctx.fillStyle=glow;ctx.fillRect(0,0,1080,1350);
    ctx.save();ctx.beginPath();ctx.rect(0,0,1080,1350);ctx.clip();
    ctx.strokeStyle='#ffffff04';ctx.lineWidth=1;
    for(let x=-1350;x<1080;x+=48){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x+1350,1350);ctx.stroke();}
    ctx.restore();
    box(68,66,64,64,16,red);text('FL',78,111,33,'#fff',850);
    text('fastlap',150,112,43,white,800);text('RACE PREDICTION CLUB',690,104,18,muted,500,mono);
    rule(164);
    text(`R${String(data.round).padStart(2,'0')} / ${data.year} / RACE REPORT`,68,221,20,red,600,mono);
    fit(data.location,68,305,944,76,white,800);
    fit(data.event,70,352,930,25,muted,450);
    if(data.circuit_path){
      ctx.save();ctx.translate(490,390);ctx.scale(.95,.95);ctx.lineWidth=5;ctx.lineJoin='round';
      ctx.strokeStyle='#ffffff0b';ctx.stroke(new Path2D(data.circuit_path));ctx.restore();
    }
    box(68,411,68,68,18,'#363b43');fit(data.initials||'FL',80,457,46,28,white,700);
    fit(data.name,155,445,825,39,white,700);
    fit(data.handle || 'УЧАСТНИК FASTLAP',157,478,820,20,muted,450);
    fit(data.points,56,746,850,238,white,850);
    text('ОЧКОВ ЗА ЭТАП',72,799,24,red,650,mono);
    // A restrained chequered flag balances the score, without a bitmap asset.
    for(let row=0;row<4;row++)for(let col=0;col<6;col++){
      ctx.fillStyle=(row+col)%2===0?'#aab0b9':'#343b44';ctx.fillRect(910+col*16,730+row*16,16,16);
    }
    rule(856);
    text(data.rank_label,70,907,16,muted,500,mono);
    text(data.rank ? `P${data.rank}` : '—',68,986,62,white,750);
    const movement = data.movement;
    text(data.movement === null ? 'РЕЗУЛЬТАТИВНЫХ' : 'ДИНАМИКА',398,907,16,muted,500,mono);
    text(movement === null ? `${data.hits}/${data.categories}` : movement>0 ? `+${movement}` : String(movement),
      396,986,62,movement>0?'#9acdb4':movement<0?'#ed9589':white,750);
    text(data.duel ? 'ДУЭЛЬ' : 'ЗАЧЁТ',728,907,16,muted,500,mono);
    if(data.duel){fit(data.duel.label,727,977,280,33,white,700);fit(`${data.duel.points>0?'+':''}${data.duel.points} · vs ${data.duel.opponent}`,730,1012,280,19,muted,450);}
    else {text(data.is_league?'ЛИГА':'ОБЩИЙ',727,977,34,white,700);}
    box(68,1061,944,126,16,'#ffffff05');ctx.fillStyle=red;ctx.fillRect(68,1086,3,76);
    if(data.overtook.length){
      text('ОБГОН В ЗАЧЁТЕ',94,1102,17,red,600,mono);
      const names = data.overtook.slice(0,2).join(' · ')+(data.overtook.length>2?` · ещё ${data.overtook.length-2}`:'');
      fit(names,94,1149,885,31,white,650);
    }else{
      text('КАЖДОЕ ОЧКО — НА СЧЕТУ',94,1102,17,red,600,mono);
      fit(`Результативных прогнозов: ${data.hits} из ${data.categories}`,94,1149,885,31,white,650);
    }
    rule(1230);fit(data.scope,68,1280,720,23,muted,500);text('fastlap.ru',829,1280,25,white,650);
    text(data.is_league?'ЗАЧЁТ ЭТАПОВ / БЕЗ СЕЗОННЫХ БОНУСОВ':`FINISH / R${String(data.round).padStart(2,'0')}`,68,1316,14,'#87929f',500,mono);
    canvas.dataset.ready='true';download.disabled=false;
  }
  function blob() {return new Promise((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(new Error()),'image/png'));}
  const filename=`fastlap-${data.year}-r${data.round}-report.png`;
  download.addEventListener('click',async()=>{
    try {
      const url=URL.createObjectURL(await blob()),anchor=document.createElement('a');
      anchor.href=url;anchor.download=filename;document.body.append(anchor);anchor.click();anchor.remove();
      window.setTimeout(()=>URL.revokeObjectURL(url),60000);
      status.textContent='Карточка готова. Если браузер открыл картинку, сохраните её через меню «Поделиться».';
    }catch{status.textContent='Не удалось создать картинку. Обновите страницу и попробуйте снова.';}
  });
  share.addEventListener('click',async()=>{
    try {const file=new File([await blob()],filename,{type:'image/png'});await navigator.share({files:[file],title:'Мои итоги гонки · Fastlap'});}
    catch(error){if(error.name!=='AbortError')status.textContent='Не удалось отправить. Скачайте карточку и поделитесь картинкой.';}
  });
  Promise.race([document.fonts?.ready || Promise.resolve(),new Promise(resolve=>window.setTimeout(resolve,2500))]).then(async()=>{
    try {draw();if(navigator.canShare){const file=new File([await blob()],filename,{type:'image/png'});share.hidden=!navigator.canShare({files:[file]});}}
    catch{status.textContent='Не удалось нарисовать карточку. Обновите страницу и попробуйте снова.';}
  });
})();
