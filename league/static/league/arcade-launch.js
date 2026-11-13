/* Library cards request the game's existing viewport-filling mode.
   Navigating never starts an attempt or requires native fullscreen support. */
(() => {
  "use strict";
  if(new URLSearchParams(location.search).get("fullscreen")!=="1")return;
  const button=document.querySelector("#vegas-fullscreen,#tetris-fullscreen,#doodle-fullscreen-toggle,#arcade-enter-fullscreen,#minesweeper-fullscreen");
  if(button&&button.getAttribute("aria-pressed")!=="true")button.click();
})();
