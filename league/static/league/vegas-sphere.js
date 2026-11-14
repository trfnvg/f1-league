/* No frame loop: CSS animates only the eyes while the landmark is visible. */
(() => {
  "use strict";
  const sphere=document.getElementById("vegas-sphere");
  if(!sphere)return;
  const motion=matchMedia("(prefers-reduced-motion: reduce)");
  const desktop=matchMedia("(min-width:701px)"),touch=matchMedia("(hover:none) and (pointer:coarse)");
  let visible=false,active=true;
  function sync(){sphere.dataset.awake=String(visible&&active&&!document.hidden&&!motion.matches&&desktop.matches&&!touch.matches);}
  if("IntersectionObserver" in window){
    new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;sync();}).observe(sphere);
  }else{visible=true;}
  motion.addEventListener("change",sync);
  desktop.addEventListener("change",sync);
  touch.addEventListener("change",sync);
  document.addEventListener("visibilitychange",sync);
  window.addEventListener("pagehide",()=>{active=false;sync();});
  window.addEventListener("pageshow",()=>{active=true;sync();});
  sync();
})();
