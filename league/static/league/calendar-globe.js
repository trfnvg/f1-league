(() => {
  'use strict';
  const root = document.querySelector('[data-race-globe]');
  if (!root) return;
  const races = JSON.parse(document.getElementById('calendar-globe-data').textContent);
  if (!races.length) return;
  const $ = name => root.querySelector(`[data-globe-${name}]`);
  const stage = $('stage'), canvas = $('canvas'), routes = $('routes');
  const tour = $('tour'), markerLayer = $('markers'), motion = $('motion');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const rad = Math.PI / 180;
  const clamp = (value, lo, hi) => Math.max(lo, Math.min(hi, value));
  const vector = (lat, lon) => [Math.cos(lat*rad)*Math.sin(lon*rad), Math.sin(lat*rad), Math.cos(lat*rad)*Math.cos(lon*rad)];
  const dot = (a,b) => a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
  const cross = (a,b) => [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  const unit = values => {const length=Math.hypot(...values)||1;return values.map(value=>value/length);};
  // Camera-to-world quaternion: unlike latitude clamps, this permits complete
  // turns over either pole and diagonal/rolling gestures without a singularity.
  const multiply = (a,b) => [
    a[3]*b[0]+a[0]*b[3]+a[1]*b[2]-a[2]*b[1],
    a[3]*b[1]-a[0]*b[2]+a[1]*b[3]+a[2]*b[0],
    a[3]*b[2]+a[0]*b[1]-a[1]*b[0]+a[2]*b[3],
    a[3]*b[3]-a[0]*b[0]-a[1]*b[1]-a[2]*b[2],
  ];
  const rotation = (axis,angle) => [...axis.map(value=>value*Math.sin(angle/2)),Math.cos(angle/2)];
  const lookAt = (lat,lon) => multiply(rotation([0,1,0],lon*rad),rotation([1,0,0],-lat*rad));
  function between(from,to) {
    const cosine=clamp(dot(from,to),-1,1);
    if(cosine<-.999999)return rotation(unit(cross(from,Math.abs(from[0])<.8?[1,0,0]:[0,1,0])),Math.PI);
    return unit([...cross(from,to),1+cosine]);
  }
  function interpolate(from,to,t) {
    let cosine=from.reduce((sum,value,index)=>sum+value*to[index],0);
    if(cosine<0){to=to.map(value=>-value);cosine=-cosine;}
    if(cosine>.9995)return unit(from.map((value,index)=>value+(to[index]-value)*t));
    const angle=Math.acos(clamp(cosine,-1,1)),denominator=Math.sin(angle);
    return from.map((value,index)=>(value*Math.sin((1-t)*angle)+to[index]*Math.sin(t*angle))/denominator);
  }
  const vectors = races.map(race => vector(race.lat,race.lon));
  const initial = Math.max(0,races.findIndex(race => race.next));
  let selected = initial, displayed = -1, labelled = -1;
  let orientation=lookAt(races[initial].lat*.7,races[initial].lon+12);
  let zoom = 1, width = 1, height = 1, dpr = 1, visible = false, initialized = false;
  let renderer, animation, raf = 0, lastFrame = 0, auto = false, hovered = false, dragging;
  let countdownTimer, frameCount = 0, renderGeneration = 0;
  const contacts=new Map();let pinch;
  const routeContext = routes.getContext('2d');
  const pinButtons = [], tourButtons = [];
  const arcVectors = vectors.slice(1).map((end,index) => {
    const start = vectors[index], angle = Math.acos(clamp(dot(start,end),-1,1));
    return Array.from({length:33},(_,step) => {
      const t=step/32, denominator=Math.sin(angle)||1;
      const a=Math.sin((1-t)*angle)/denominator, b=Math.sin(t*angle)/denominator;
      const lift=1.006+.014*Math.sin(Math.PI*t);
      return start.map((value,axis)=>(value*a+end[axis]*b)*lift);
    });
  });
  const create = (tag,cls,text) => {
    const node=document.createElement(tag); if(cls)node.className=cls;
    if(text!==undefined)node.textContent=text; return node;
  };
  const zoneSelector=document.getElementById('calendar-timezone');
  const clockValues=[...root.querySelectorAll('[data-globe-clock-value]')];
  function raceTime(value,race) {
    if(!value)return 'Время уточняется';
    const valueZone=zoneSelector?.value;
    const timeZone=valueZone==='venue'?race.timezone:valueZone==='device'?(Intl.DateTimeFormat().resolvedOptions().timeZone||'Europe/Moscow'):'Europe/Moscow';
    return new Intl.DateTimeFormat('ru-RU',{timeZone,day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(value)).replace(',',' ·');
  }
  function tick() {
    const race=races[displayed]; if(!race)return;
    const remaining=race.raceAt?new Date(race.raceAt).getTime()-Date.now():null;
    const counting=!race.finished&&remaining!==null&&remaining>0;
    $('departure').classList.toggle('is-counting',counting);$('clock').hidden=!counting;
    let text='Время старта уточняется';
    if(race.finished)text='Этап завершён';
    else if(remaining!==null && remaining<=0)text='Старт гонки прошёл';
    else if(remaining!==null) {
      let seconds=Math.floor(remaining/1000);
      const days=Math.floor(seconds/86400);seconds%=86400;
      const hours=Math.floor(seconds/3600);seconds%=3600;
      const minutes=Math.floor(seconds/60);seconds%=60;
      [days,hours,minutes,seconds].forEach((value,index)=>{
        const next=String(value).padStart(2,'0');if(clockValues[index].textContent!==next)clockValues[index].textContent=next;
      });
      text=`До старта: ${days}д ${String(hours).padStart(2,'0')}ч ${String(minutes).padStart(2,'0')}м ${String(seconds).padStart(2,'0')}с`;
    }
    if($('countdown').textContent!==text)$('countdown').textContent=text;
  }
  function showCard(index,force=false) {
    if(displayed===index&&!force)return;
    const changed=displayed!==index;displayed=index;const race=races[index];
    if(changed&&!reduced.matches&&visible)$('card').animate([{opacity:.6},{opacity:1}],{duration:180,easing:'ease-out'});
    $('round').textContent=`R${String(race.round).padStart(2,'0')}`;
    $('state').textContent=race.next?'БЛИЖАЙШИЙ ЭТАП':race.finished?'ЗАВЕРШЁН':race.sprint?'SPRINT WEEKEND':'ГРАН-ПРИ';
    for(const key of ['country','location','circuit','dates'])$(key).textContent=race[key];
    $('race-time').textContent=raceTime(race.raceAt,race);
    $('zone').textContent=zoneSelector?.value==='venue'?'ГОНКА · НА АВТОДРОМЕ':zoneSelector?.value==='device'?'ГОНКА · МОЁ ВРЕМЯ':'ГОНКА · МСК';
    const cover=$('cover');cover.hidden=!race.cover;
    if(race.cover&&cover.getAttribute('src')!==race.cover)cover.src=race.cover;
    $('track').setAttribute('d',race.track||'');
    $('track-bed').setAttribute('d',race.track||'');
    $('track').closest('.rg-track-wrap').hidden=!race.track;
    const start=$('track-start');start.toggleAttribute('hidden',!race.track);
    if(race.track){const point=$('track').getPointAtLength(0);start.setAttribute('cx',point.x);start.setAttribute('cy',point.y);}
    const link=$('open');link.href=race.url;
    link.firstChild.textContent=race.external?'На сайте F1 ':'Открыть этап ';
    if(race.external){link.target='_blank';link.rel='noopener noreferrer';}else{link.removeAttribute('target');link.removeAttribute('rel');}
    $('schedule').href=`#grand-prix-${race.key}`;
    const fragment=document.createDocumentFragment();
    race.sessions.forEach(session=>{
      const row=create('div');row.append(create('dt','',session.label),create('dd','',raceTime(session.at,race)));fragment.append(row);
    });
    $('sessions').replaceChildren(fragment);tick();
  }
  function setAuto(value) {
    auto=value&&!reduced.matches&&!!renderer;
    motion.setAttribute('aria-pressed',String(auto));
    $('motion-label').textContent=auto?'Пауза':'Вращение';
    motion.setAttribute('aria-label',auto?'Остановить вращение глобуса':'Включить вращение глобуса');
    requestFrame();
  }
  function select(index,center=true,scroll=true,reveal=true) {
    selected=(index+races.length)%races.length;hovered=false;showCard(selected);
    labelled=reveal?selected:-1;
    pinButtons.forEach((button,i)=>button.setAttribute('aria-pressed',String(i===selected)));
    tourButtons.forEach((button,i)=>button.setAttribute('aria-pressed',String(i===selected)));
    setAuto(false);
    if(center) {
      const target=lookAt(races[selected].lat*.8,races[selected].lon+8);
      if(reduced.matches||!visible){orientation=target;animation=null;}
      else animation={start:performance.now(),from:orientation.slice(),to:target};
    }
    if(scroll) {
      const item=tourButtons[selected],box=item.getBoundingClientRect(),list=tour.getBoundingClientRect();
      tour.scrollTo({left:tour.scrollLeft+box.left-list.left-(tour.clientWidth-box.width)/2,behavior:reduced.matches?'auto':'smooth'});
    }
    requestFrame();
  }
  races.forEach((race,index)=>{
    const pin=create('button','rg-pin'+(race.next?' is-next':''));pin.type='button';
    pin.dataset.globePin=race.key;pin.hidden=true;
    pin.setAttribute('aria-label',`R${race.round} · ${race.location} · ${race.dates}`);
    pin.append(create('span','rg-pin-label',race.location));
    // Hover/focus never reveals labels or replaces the selected race card.
    pin.addEventListener('pointerenter',()=>{hovered=true;});
    pin.addEventListener('pointerleave',()=>{hovered=false;requestFrame();});
    pin.addEventListener('focus',()=>{hovered=true;});
    pin.addEventListener('blur',()=>{hovered=false;requestFrame();});
    // Pointer taps are resolved on pointerup so a drag may start on a marker.
    // Native keyboard/assistive-technology activation still uses click.
    pin.addEventListener('click',event=>{if(event.detail===0)select(index);});markerLayer.append(pin);pinButtons.push(pin);
    const button=create('button','rg-tour-item');button.type='button';button.dataset.globeRace=race.key;
    const meta=create('small','',`R${String(race.round).padStart(2,'0')}`);
    meta.append(create('span','',race.dates.slice(0,5)));
    button.classList.toggle('is-finished',race.finished);button.classList.toggle('is-next',race.next);
    button.append(meta,create('strong','',race.location));
    button.setAttribute('aria-label',`Показать ${race.title}, ${race.dates}`);
    button.addEventListener('click',()=>select(index));tour.append(button);tourButtons.push(button);
  });
  root.hidden=false;select(initial,false,true,false);
  $('cover').addEventListener('error',()=>{$('cover').hidden=true;});
  zoneSelector?.addEventListener('change',()=>showCard(displayed,true));
  $('schedule').addEventListener('click',event=>{
    const race=races[displayed],card=document.getElementById(`grand-prix-${race.key}`);
    if(!card)return;
    event.preventDefault();
    document.querySelector('[data-calendar-filters] [data-filter="all"]')?.click();
    history.replaceState(null,'',`#grand-prix-${race.key}`);
    card.scrollIntoView({behavior:reduced.matches?'auto':'smooth',block:'start'});
  });
  function basis() {
    const [x,y,z,w]=orientation;
    return [[1-2*(y*y+z*z),2*(x*y+z*w),2*(x*z-y*w)],
      [2*(x*y-z*w),1-2*(x*x+z*z),2*(y*z+x*w)],
      [2*(x*z+y*w),2*(y*z-x*w),1-2*(x*x+y*y)]];
  }
  function project(point,axes,radius) {
    return {x:width/2+dot(point,axes[0])*radius,y:height/2-dot(point,axes[1])*radius,z:dot(point,axes[2])};
  }
  function draw() {
    if(!renderer)return;
    const axes=basis(),radius=Math.min(width,height)*.43*zoom;
    renderer(axes,radius*dpr);
    const positions=vectors.map(point=>project(point,axes,radius));
    pinButtons.forEach((button,index)=>{
      const point=positions[index],hidden=point.z<.055||point.x<10||point.x>width-10||point.y<45||point.y>height-55;
      if(button.hidden!==hidden)button.hidden=hidden;
      button.classList.toggle('is-labelled',index===labelled);
      if(hidden)return;
      button.style.transform=`translate(${point.x.toFixed(2)}px,${point.y.toFixed(2)}px) translate(-50%,-50%)`;
      button.style.zIndex=String(index===selected?5:Math.round(point.z*3));
      button.classList.toggle('is-label-left',point.x>width*.66);
    });
    if(routeContext) {
      routeContext.setTransform(dpr,0,0,dpr,0,0);routeContext.clearRect(0,0,width,height);
      arcVectors.forEach((points,index)=>{
        const active=index===selected||index+1===selected;
        routeContext.beginPath();let started=false;
        points.forEach(point=>{
          const p=project(point,axes,radius);
          if(p.z<.08){started=false;return;}
          if(started)routeContext.lineTo(p.x,p.y);else{routeContext.moveTo(p.x,p.y);started=true;}
        });
        routeContext.lineWidth=active?1.2:.6;
        routeContext.strokeStyle=active?'#ff756aa6':'#9aa8b32d';routeContext.stroke();
      });
    }
    root.dataset.globeFrame=String(++frameCount);
  }
  function frame(time) {
    raf=0;if(!visible||document.hidden||!renderer)return;
    const elapsed=lastFrame?Math.min(80,time-lastFrame):16;lastFrame=time;
    if(animation) {
      const t=clamp((time-animation.start)/420,0,1),ease=1-Math.pow(1-t,3);
      orientation=interpolate(animation.from,animation.to,ease);
      if(t===1)animation=null;
    }else if(auto&&!hovered&&!dragging)orientation=unit(multiply(orientation,rotation([0,1,0],elapsed*.004*rad)));
    draw();
    if(animation||(auto&&!hovered&&!dragging))requestFrame();
  }
  function requestFrame() {if(!raf&&visible&&!document.hidden&&renderer)raf=requestAnimationFrame(frame);}
  function resize() {
    const box=stage.getBoundingClientRect();width=Math.max(1,box.width);height=Math.max(1,box.height);
    dpr=Math.min(devicePixelRatio||1,2);
    for(const node of [canvas,routes]){
      const w=Math.round(width*dpr),h=Math.round(height*dpr);
      if(node.width!==w)node.width=w;if(node.height!==h)node.height=h;
    }
    for(const point of contacts.values())point.ball=ball(point.x,point.y);
    requestFrame();
  }
  function fallback() {
    cancelGesture();
    renderGeneration++; // Invalidate texture loads belonging to a lost/failed context.
    renderer=null;root.dataset.globeRenderer='fallback';root.classList.add('is-fallback');
    $('loading').hidden=true;
    $('fallback').hidden=false;pinButtons.forEach(pin=>{pin.hidden=true;});
    motion.disabled=true;root.querySelectorAll('[data-globe-zoom]').forEach(button=>{button.disabled=true;});
    setAuto(false);if(raf)cancelAnimationFrame(raf);raf=0;
  }
  const vertex='attribute vec2 position;void main(){gl_Position=vec4(position,0.,1.);}';
  const fragment=`precision mediump float;
    uniform vec2 resolution;uniform float radius;uniform mat3 axes;
    uniform sampler2D dayMap;uniform sampler2D nightMap;
    void main(){
      vec2 p=(gl_FragCoord.xy-resolution*.5)/radius;float r=length(p);
      if(r>1.){gl_FragColor=vec4(0.);return;}
      vec3 n=vec3(p,sqrt(max(0.,1.-dot(p,p))));vec3 world=axes*n;
      vec2 uv=vec2(atan(world.x,world.z)/6.2831853+.5,asin(clamp(world.y,-1.,1.))/3.14159265+.5);
      vec3 day=texture2D(dayMap,uv).rgb;vec3 night=texture2D(nightMap,uv).rgb;
      float light=max(0.,dot(n,normalize(vec3(-.7,.5,1.))));
      float gray=dot(day,vec3(.21,.72,.07));
      float ocean=smoothstep(.015,.085,day.b-day.r)*(1.-smoothstep(.17,.45,gray));
      day=mix(vec3(gray),day,.72);day=mix(day,vec3(.13,.32,.44),ocean*.65);
      night=max(night-vec3(.035,.045,.075),vec3(0.));
      vec3 color=day*(.36+.64*light)*(.84+.16*sqrt(n.z))+night*vec3(1.05,.95,.8)*(.12-.08*light);
      float reflection=pow(max(0.,dot(n,normalize(vec3(-.4,.7,1.)))),24.)*ocean*.045;
      color+=vec3(.75,.8,.78)*reflection+vec3(.5,.54,.56)*pow(1.-n.z,5.)*.035;
      gl_FragColor=vec4(color,1.-smoothstep(.995,1.,r));
    }`;
  function loadImage(url) {
    return new Promise((resolve,reject)=>{
      const image=new Image();
      const finish=(error)=>{
        clearTimeout(timeout);image.onload=image.onerror=null;
        if(error)reject(error);else resolve(image);
      };
      const timeout=setTimeout(()=>finish(new Error('Globe texture timed out')),15000);
      image.onload=()=>finish();image.onerror=()=>finish(new Error('Globe texture unavailable'));image.src=url;
    });
  }
  async function init() {
    initialized=true;
    const generation=++renderGeneration;
    try {
      const gl=canvas.getContext('webgl',{alpha:true,antialias:false,premultipliedAlpha:false,powerPreference:'low-power'});
      if(!gl)throw new Error('WebGL unavailable');
      function shader(type,source) {
        const result=gl.createShader(type);gl.shaderSource(result,source);gl.compileShader(result);
        if(!gl.getShaderParameter(result,gl.COMPILE_STATUS))throw new Error('Globe shader unavailable');return result;
      }
      const program=gl.createProgram();gl.attachShader(program,shader(gl.VERTEX_SHADER,vertex));gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fragment));gl.linkProgram(program);
      if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error('Globe renderer unavailable');
      gl.useProgram(program);const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
      gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);
      const position=gl.getAttribLocation(program,'position');gl.enableVertexAttribArray(position);gl.vertexAttribPointer(position,2,gl.FLOAT,false,0,0);
      const images=await Promise.all([loadImage(root.dataset.dayTexture),loadImage(root.dataset.nightTexture)]);
      if(generation!==renderGeneration||gl.isContextLost())return;
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true);
      images.forEach((image,index)=>{
        gl.activeTexture(gl.TEXTURE0+index);gl.bindTexture(gl.TEXTURE_2D,gl.createTexture());
        gl.texImage2D(gl.TEXTURE_2D,0,gl.RGB,gl.RGB,gl.UNSIGNED_BYTE,image);
        gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
        gl.uniform1i(gl.getUniformLocation(program,index?'nightMap':'dayMap'),index);
      });
      const resolution=gl.getUniformLocation(program,'resolution'),r=gl.getUniformLocation(program,'radius'),a=gl.getUniformLocation(program,'axes');
      renderer=(axes,radius)=>{gl.viewport(0,0,canvas.width,canvas.height);gl.uniform2f(resolution,canvas.width,canvas.height);gl.uniform1f(r,radius);gl.uniformMatrix3fv(a,false,new Float32Array(axes.flat()));gl.drawArrays(gl.TRIANGLES,0,6);};
      root.dataset.globeRenderer='webgl';root.classList.remove('is-fallback');$('fallback').hidden=true;$('loading').hidden=true;motion.disabled=false;
      root.querySelectorAll('[data-globe-zoom]').forEach(button=>{button.disabled=false;});resize();requestFrame();
    }catch(_){fallback();}
  }
  canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();fallback();});
  canvas.addEventListener('webglcontextrestored',()=>{initialized=false;if(visible)init();});
  const observer=new IntersectionObserver(entries=>{
    // A resize/fast scroll can queue several entries for the same stage.
    // Only the latest one describes its current visibility.
    visible=entries[entries.length-1].isIntersecting;root.dataset.globeVisible=String(visible);
    if(visible){if(!initialized)init();lastFrame=0;requestFrame();}
    else{if(raf)cancelAnimationFrame(raf);raf=0;}
  },{threshold:.05});observer.observe(stage);
  // On a phone the information card can be visible below the off-screen Earth.
  // Keep its countdown live without running the GPU for that part of the page.
  new IntersectionObserver(entries=>{
    clearInterval(countdownTimer);
    if(entries[entries.length-1].isIntersecting){tick();countdownTimer=setInterval(()=>{if(!document.hidden)tick();},1000);}
  }).observe(root);
  new ResizeObserver(resize).observe(stage);
  document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelGesture();if(raf)cancelAnimationFrame(raf);raf=0;}else{lastFrame=0;requestFrame();tick();}});
  motion.addEventListener('click',()=>setAuto(!auto));
  $('home').addEventListener('click',()=>{zoom=1;select(initial);});
  root.querySelectorAll('[data-globe-step]').forEach(button=>button.addEventListener('click',()=>select(selected+Number(button.dataset.globeStep))));
  function changeZoom(amount){zoom=clamp(zoom+amount,.8,1.8);requestFrame();}
  root.querySelectorAll('[data-globe-zoom]').forEach(button=>button.addEventListener('click',()=>changeZoom(Number(button.dataset.globeZoom)*.15)));
  stage.addEventListener('keydown',event=>{
    if(event.target!==stage||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','=','-','Home'].includes(event.key))return;
    event.preventDefault();setAuto(false);animation=null;
    if(event.key==='Home'){zoom=1;select(initial);}
    else if(['+','=','-'].includes(event.key))changeZoom(event.key==='-'?-.15:.15);
    else{
      const horizontal=event.key==='ArrowLeft'||event.key==='ArrowRight';
      const angle=(event.key==='ArrowRight'||event.key==='ArrowDown'?12:-12)*rad;
      orientation=unit(multiply(orientation,rotation(horizontal?[0,1,0]:[1,0,0],angle)));requestFrame();
    }
  });
  function ball(x,y) {
    const box=stage.getBoundingClientRect(),radius=Math.min(width,height)*.43*zoom;
    const px=(x-box.left-width/2)/radius,py=(height/2-y+box.top)/radius;
    const squared=px*px+py*py;
    return squared<=1?[px,py,Math.sqrt(1-squared)]:unit([px,py,0]);
  }
  const distance=()=>{const [a,b]=[...contacts.values()];return Math.hypot(a.x-b.x,a.y-b.y);};
  stage.addEventListener('pointerdown',event=>{
    if((event.pointerType==='mouse'&&event.button!==0)||!renderer||contacts.size>=2)return;
    event.preventDefault();animation=null;hovered=false;setAuto(false);dragging=true;
    const pin=event.target.closest('[data-globe-pin]');
    contacts.set(event.pointerId,{x:event.clientX,y:event.clientY,startX:event.clientX,startY:event.clientY,
      ball:ball(event.clientX,event.clientY),pin:pin?pinButtons.indexOf(pin):-1,moved:false,pinched:false});
    stage.setPointerCapture(event.pointerId);
    if(contacts.size>1){for(const point of contacts.values())point.pinched=true;pinch={distance:Math.max(1,distance()),zoom};}
    if(event.pointerType==='mouse')stage.focus({preventScroll:true});
  });
  stage.addEventListener('pointermove',event=>{
    const point=contacts.get(event.pointerId);if(!point)return;
    if(event.cancelable)event.preventDefault();point.x=event.clientX;point.y=event.clientY;
    if(contacts.size>1){zoom=clamp(pinch.zoom*distance()/pinch.distance,.8,1.8);requestFrame();return;}
    if(!point.moved&&Math.hypot(point.x-point.startX,point.y-point.startY)<4)return;
    point.moved=true;stage.classList.add('is-dragging');
    const next=ball(point.x,point.y);
    orientation=unit(multiply(orientation,between(next,point.ball)));point.ball=next;requestFrame();
  });
  function release(event) {
    const point=contacts.get(event.pointerId);if(!point)return;
    contacts.delete(event.pointerId);pinch=null;
    if(event.type==='pointerup'&&!point.moved&&!point.pinched&&point.pin>=0)select(point.pin);
    for(const remaining of contacts.values()){remaining.ball=ball(remaining.x,remaining.y);remaining.moved=true;}
    if(!contacts.size){dragging=false;stage.classList.remove('is-dragging');}
    if(stage.hasPointerCapture(event.pointerId))stage.releasePointerCapture(event.pointerId);
  }
  function cancelGesture() {
    const ids=[...contacts.keys()];contacts.clear();pinch=null;dragging=false;stage.classList.remove('is-dragging');
    for(const id of ids)if(stage.hasPointerCapture(id))stage.releasePointerCapture(id);
  }
  window.addEventListener('blur',cancelGesture);
  stage.addEventListener('pointerup',release);stage.addEventListener('pointercancel',release);stage.addEventListener('lostpointercapture',release);
  // This is deliberately local to the map; page scrolling/zooming outside it
  // remains native. Wheel scrolling is never hijacked to zoom the Earth.
  stage.addEventListener('touchmove',event=>{if(renderer&&event.cancelable)event.preventDefault();},{passive:false});
  reduced.addEventListener('change',()=>{if(reduced.matches){setAuto(false);if(animation){orientation=animation.to;animation=null;}}requestFrame();});
})();
