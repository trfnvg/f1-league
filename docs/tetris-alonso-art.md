# Pit Stack — pixel Alonso builder

Generated/edited with the built-in image_gen tool (imagegen skill), transparent alpha.
Production asset: `league/static/league/images/tetris-gp/alonso-pixel-builder-v2.png`.
Original 1536×1024 RGBA atlas: three columns, two rows, six 512×512 cells:
0 building / 1 placing / 2 surprised / 3 fists raised / 4 thumbs up / 5 disappointed.
The old `alonso-builder-v1.png` is archived as the edit reference, not loaded by the game.
No resolution reduction or lossy conversion. CSS uses nearest-neighbor pixel sampling,
integer-offset, stepped movements, and discrete drawn frames rather than rotating
a smooth illustration. Bottom-row floor is aligned by a 30-source-pixel CSS offset;
a top clip prevents exposing the previous row's feet.

Final image-edit prompt:

> Use case: style-transfer. Asset type: production game sprite sheet, actual coarse crisp pixel art. Input image is an EDIT TARGET for character identity and concept ONLY. Completely redraw its smooth painterly illustration into authentic 1990s 16-bit arcade pixel art: obvious large square pixel clusters, chunky dark stepped outlines, limited palette of about 24 colors, flat 2-3 shade ramps, no antialiasing, NO smooth gradients, NO photographic/painterly face or hair, NO soft illustration. Imagine each square frame hand-drawn at 96x96 logical pixels and scaled by nearest-neighbor. Preserve recognizable adult Fernando Alonso with thick eyebrows, dark swept hair, short dark/grey beard, green racing suit without logos, block-built green Formula 1 car on a small workshop bench. Make ONE atlas in EXACTLY THREE columns and TWO rows of equal square cells, aspect ratio 3:2, SIX full frames total, row-major reading order. Keep exact same character scale, camera and bench/car/floor positions across all six cells. Entire person and workbench fully inside each cell with generous transparent margins. Frame0 top-left: seated concentrating holding yellow tetromino slightly above car. Frame1 top-middle: seated leaning in, hand moved down placing that yellow block onto car. Frame2 top-right: seated looking up surprised at game, mouth slightly open, both hands lifted halfway. Frame3 bottom-left: seated jubilant, BOTH FISTS raised up beside head, smiling broadly, same car stays on bench. Frame4 bottom-middle: seated smiling and giving a clear thumbs up, same completed car on bench. Frame5 bottom-right: seated disappointed/bemused, looking at loose red block in hand, shoulders slumped. Car remains on bench and never changes position; same green suit, face and proportions all frames. Transparent alpha background throughout. No text, labels, caption, border, grid, UI, scenery, shadows on background, logo, watermark, extra characters or extra frames. Priority is VISIBLY PIXELATED old-console sprite style, clean angular pixels, not the smooth illustration of the reference. This sheet will animate using discrete frame swaps.

Runtime: one image decode, CSS-composited movement; no extra animation loop,
timers, canvas drawing or changes to deterministic game rules. The existing game
loop advances frame timing; DOM is written only when a frame/state changes.
Idle alternates building and placing. Four lines trigger surprise during the charge,
then a 3-second sequence of raised fists and thumbs up with eight bounded particles.
Other reactions: 360 ms ordinary landing, 800 ms small clear, disappointment at loss.
All reaction clocks freeze on pause and reset on restart. Consecutive Tetrises restart
rather than queue reactions; small clears do not interrupt a celebration.
There are no visible captions. Reduced-motion mode shows still expressive poses
without idle or victory frame cycling, jumping or particles.

Desktop uses free space left of the board; narrow screens put the character under
telemetry. Short fullscreen landscape hides decoration to preserve the field.
No trophy is awarded or persisted yet; the character establishes the future trophy theme.

Checks: `tests/tetris_mascot.mjs`, `tests/tetris_browser.mjs`.
