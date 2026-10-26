(() => {
  'use strict';
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const tracks = [];
  const samples = 768;
  let frame = 0, lastTime = 0;
  const wrap = value => ((value % 1) + 1) % 1;
  function geometry(track) {
    const length = track.path.getTotalLength();
    if (!length) return false;
    track.points = Array.from({length: samples}, (_, i) => {
      const p = track.path.getPointAtLength(i * length / samples);
      return {x:p.x, y:p.y};
    });
    return true;
  }
  function draw(track) {
    if (!track.points && !geometry(track)) return;
    for (const car of track.cars) {
      const index = wrap(car.position) * samples;
      const i = Math.floor(index), t = index - i;
      const a = track.points[i], b = track.points[(i + 1) % samples];
      const dx = b.x-a.x, dy = b.y-a.y, distance = Math.hypot(dx, dy) || 1;
      // Two slightly offset racing lines keep an overtaking pair distinguishable.
      const lane = car.lane * (3.2 + Math.sin(track.time * .7 + car.phase) * .6);
      car.node.setAttribute('cx', (a.x + dx*t - dy/distance*lane).toFixed(2));
      car.node.setAttribute('cy', (a.y + dy*t + dx/distance*lane).toFixed(2));
    }
    track.group.classList.add('is-ready');
  }
  function tick(time) {
    frame = 0;
    if (document.hidden || reduced.matches) {lastTime=0; return;}
    const dt = lastTime ? Math.min((time-lastTime)/1000, .05) : 0;
    lastTime = time;
    for (const track of tracks) {
      if (!track.visible) continue;
      track.time += dt;
      for (const car of track.cars) {
        car.position = wrap(car.position + dt * car.speed * (1 + .16*Math.sin(track.time*.45 + car.phase)));
      }
      draw(track);
    }
    start();
  }
  function start() {
    if (!frame && !document.hidden && !reduced.matches && tracks.some(track => track.visible)) frame = requestAnimationFrame(tick);
  }
  function pause() {
    cancelAnimationFrame(frame); frame = 0; lastTime = 0;
  }
  const observer = typeof IntersectionObserver === 'function' ? new IntersectionObserver(entries => {
    for (const entry of entries) {
      const track = tracks.find(item => item.svg === entry.target);
      track.visible = entry.isIntersecting;
      if (track.visible) draw(track);
    }
    if (!tracks.some(track => track.visible)) pause();
    start();
  }) : null;
  function init() {
    document.querySelectorAll('.circuit-visual.is-animated').forEach(svg => {
      const group = svg.querySelector('.circuit-peloton');
      if (!group) return;
      const nodes = [...group.querySelectorAll('.circuit-car')];
      for (let i = nodes.length-1; i > 0; i--) {
        const j = Math.floor(Math.random()*(i+1));
        [nodes[i], nodes[j]] = [nodes[j], nodes[i]];
      }
      const offset = Math.random();
      const track = {svg, group, path:svg.querySelector('.circuit-trace'), time:0, visible:!observer,
        cars:nodes.map((node, i) => ({node, position:wrap(offset+i/nodes.length), speed:.028+Math.random()*.009,
          phase:Math.random()*Math.PI*2, lane:i%2 ? 1 : -1}))};
      tracks.push(track);
      svg.addEventListener('circuit:changed', () => {track.points=null; if (track.visible) draw(track);});
      if (observer) observer.observe(svg); else draw(track);
    });
    start();
  }
  document.addEventListener('visibilitychange', () => {pause(); start();});
  reduced.addEventListener('change', () => {pause(); start();});
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once:true}); else init();
})();
