# Doodle artwork loading

Artwork is unchanged: no source image recompression, resolution reduction or
device-pixel-ratio changes are part of this optimization.

## Chapters

- Startup: 12 images, approximately 10.98 MiB of source files. Includes the
  original introduction, hero, paddock, platforms, tyres and rocket.
- Sky: prefetched at camera height 1200; required at 2700, before the first
  clouds at 2800. Includes hawk animation.
- Space: prefetched at camera height 7000; required at 10000, before the fade
  starts at 10500. Includes Toto and his projectiles, carbon debris, Ferrari
  satellite, lunar service crew and Alonso's shuttle.
- Forgotten paddock: prefetched at score 4000; required at 4900, before the
  portal at 5000. Includes platforms and Kimi.
- Antarctica: prefetched in the forgotten paddock at score 6500; required at
  7900, before the cutscene at 8000. Includes both cutscenes, piranhas and the
  Iceman/Ferrari strategist/FIA snowman encounters. Their three animation
  sheets are never requested at startup (12 of 37 images load initially).

Chapters share in-flight requests. Prepared artwork is published only after the
whole chapter is valid. A failed chapter retries after a backoff; unavailable
artwork freezes simulation time, score and physics at the readiness barrier,
with a loading caption. Restart resets the wait state. Previously loaded
chapters remain available for restarts. Admin previews await their own chapters
before starting a sandbox run and do not create scored attempts.

Image decoding is asynchronous. Sprite preparation yields between sheets using
idle callbacks (with a timeout) or a timer fallback. Transparent frame margins
are discarded without resizing the retained pixels or changing collision masks.
The winter seam is composited once at display resolution and reused, rather
than blending 16 bands per tile on every frame. This is only a narrow seam
surface, not an oversized repeated canvas. Resize/context recovery invalidates
the seam cache.

## Regression checks

The native Canvas test uses Node and `@napi-rs/canvas`, installed separately from
the Python application:

```sh
node tests/doodle_streaming.mjs
# Or point CANVAS_MODULE at an existing @napi-rs/canvas/index.js installation.
```

It checks cold-start request count, deduplication, delayed and failed resources,
pause/resume, atomic publication, retries, cold admin previews, fullscreen-sized
mobile/desktop canvases, cached seam draw count and pixel-exact sprite trimming.
Optional `DOODLE_PREVIEW_DIR` writes PNG previews to an existing directory.

These are native Canvas checks, not Safari/Chrome device FPS measurements.
Verify scrolling, controls, transitions and frame timings on actual target
devices before claiming a particular FPS improvement.
