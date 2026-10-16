# Doodle stability review — 2026-10-16

Reviewed Canvas rendering and texture lifetime, sprite alpha masks, platform
landing and falling hazards, viewport changes, staged loading, and chapter/boss
regressions. Existing unrelated site changes were left untouched.

## Implemented

- Landing selects the earliest crossed platform surface instead of the first
  platform in array order. Horizontal player and moving-platform positions are
  evaluated at the contact time. Screen wrapping cannot create a phantom sweep
  through the middle of the board. Below-screen surfaces remain excluded.
- Falling hazards test the relative movement between physics ticks against the
  sprite silhouette. Fast descents cannot pass through a thin obstacle merely
  because neither endpoint overlaps it. Wheel stomps retain priority.
- Collision masks use 32 × 32 cells instead of 18 × 18. Transparent margins
  remain non-solid; artwork itself is not cropped destructively or recompressed.
- Animated sprite sizing retains at most eight display-sized textures and one
  original-resolution fallback per sprite, until viewport invalidation. The old
  24-entry eviction loop could allocate another canvas on every zoom frame.
  Stable-size hero poses still use their display-resolution textures.
- Updated the script URL revision for client cache invalidation.

## Verification and limits

`tests/doodle_streaming.mjs` exercises native Canvas with desktop and mobile
viewport sizes. Added regression checks for first-contact ordering, moving
surfaces, screen wrap, transparent margins, swept collision and near misses,
and bounded texture allocation across 120 distinct requested sizes. The suite
also exercises staged-load failure/retry, scene transitions, winter/space
encounters, the ten-hit Sid fight, arena resizing and restart isolation.

Syntax and whitespace checks pass. The original source images, canvas pixel
density and gameplay physics step are preserved. Explicit frame clearing is
retained because of previous WebKit trailing-image regressions.

These checks do not measure browser GPU frame time or FPS on a physical iPhone.
No numeric FPS gain is claimed. Real-device profiling remains needed to identify
driver/compositing stalls and peak memory during later chapters. Startup still
requests approximately 10.98 MiB; staged loading has not eliminated that network
cost. No server, CDN, public access or leaderboard rules were changed.
