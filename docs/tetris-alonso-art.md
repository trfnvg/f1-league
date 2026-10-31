# Pit Stack — Alonso builder

Generated with the built-in image_gen tool (imagegen skill), transparent background.
Production asset: `league/static/league/images/tetris-gp/alonso-builder-v1.png`.
Original 2172×724 RGBA atlas: three 724×724 cells, idle / celebration / disappointment.
Preserve original resolution and alpha; no external image host, third-party logos or game API.

Final generation prompt:

> Use case: stylized-concept. Asset type: production transparent pixel-art sprite atlas for the browser falling-blocks game Pit Stack. Create ONE wide horizontal sprite sheet with EXACTLY THREE equal square cells in a single row, left-to-right: idle builder, celebration, disappointed. Each cell shows the SAME recognizable Fernando Alonso, dark swept hair, thick dark eyebrows, short salt-and-pepper beard, teal-green racing suit without text/logos, seated on a small workshop stool, assembling a miniature green Formula 1 car made of colorful interlocking tetromino building blocks on a low workbench. Attractive premium 16-bit/32-bit hand-pixeled game art, precise clean pixel clusters, expressive adult likeness, not a baby/chibi, warm face highlights, charcoal outlines, teal and muted red/yellow blocks, transparent negative space. Full body/workbench/car inside every cell, same scale and alignment, generous padding between cells, nothing cropped. LEFT CELL: relaxed focused pose, holding one yellow L block above unfinished car. MIDDLE CELL: joyful smile and one hand giving thumbs up, completed block car with a tiny gold sparkle. RIGHT CELL: bemused disappointed expression, looking down at a loose red block in his hand and a few scattered parts on bench, no tears. Three distinct full poses, no extra copies, no panel borders, no labels, no letters, no words, no watermark, no scenery, genuine transparent alpha background. These will be used as three CSS sprite states and gently animated using CSS, so aligned feet and car baselines and equal square cells are important.

Runtime: one image decode, CSS-composited movement; no extra animation loop,
timers, canvas drawing or changes to deterministic game rules. Reactions run for
360 ms (ordinary landing), 800 ms (small clear), 3000 ms (four lines), freeze on pause,
reset on restart. Four-row charge triggers anticipation before the explosion;
the clear then triggers a bounce and eight bounded, clipped block particles.
Consecutive Tetrises restart rather than queue reactions; small clears do not
interrupt a celebration. There are no visible captions below the character.
Reduced-motion users see the same expressive poses without animation.
Desktop uses the free space left of the board; narrow screens put the character
under telemetry. Short fullscreen landscape hides decoration to preserve the field.
No trophy awarded or persisted yet; the character establishes the future trophy theme.

Checks: `tests/tetris_mascot.mjs`, `tests/tetris_browser.mjs`.
