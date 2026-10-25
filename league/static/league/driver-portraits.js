(() => {
  document.addEventListener('error', event => {
    if (event.target.matches?.('img[data-driver-photo]')) event.target.hidden = true;
  }, true);
  document.querySelectorAll('img[data-driver-photo]').forEach(image => {
    if (image.complete && !image.naturalWidth) image.hidden = true;
  });
})();
