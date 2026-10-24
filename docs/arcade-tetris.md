# Pit Stack · admin-only F1 falling-block prototype

## Access and scope

Open **Аркады → Управление аркадами → Лаборатория · новые игры → Pit Stack**,
or `/arcade/play/tetris/` as an active staff user. Anonymous/ordinary users receive
404, including with `?admin_test=1`. The GET-only view checks staff before reading
contests or building leaderboards. No schema changes.

This is a playable **test**, not a third published competition. `PREVIEW_GAMES`
is separate from `GAMES`: the public library, publication dropdown, attempts,
records, current contest and winner's wheel are unchanged. Forging a publication
POST with `active_game=tetris` is rejected. No score, attempt or local high-score
is saved; reloading starts a fresh session. Future publication will need its own
server-side attempt/scoring validation and ranking integration, not just moving
the entry into GAMES (existing models_for defaults to Flappy).

## Rules and controls

The user's “original tennis rules” was interpreted as “original Tetris rules”.
This prototype uses familiar classic falling-block rules, not an exact emulator
of any one historical release: 10 columns × 20 visible rows, all seven four-cell
shapes, uniform independent random pieces, one-piece preview, bidirectional rotation
with small horizontal wall adjustments only, 350–220 ms lock grace capped at ten
movement/rotation resets. No ghost, hold, enemies or wheel bonuses.

Full rows clear together after a 180 ms visual effect. 1/2/3/4 rows award
40/100/300/1200 × the current one-based level; soft drop awards 1 per cell, hard
drop 2. Every ten lines increases the score multiplier. Difficulty uses the larger
of cleared-line tier and active-time tier (45 seconds per tier): gravity is
800 × 0.78^tier, bounded at 65 ms per cell; lock grace decreases by 8 ms per tier,
bounded at 220 ms. Pauses/hidden tabs do not accrue time. Accumulated fractional
gravity time is retained, including multiple cell steps when required by a frame.
New-piece obstruction or lock above the board ends the run.

Arrows or physical A/D/W/S (also work with Russian keyboard layout), X for
clockwise / Z for counterclockwise rotation, Enter/NumpadEnter to hard drop.
Space starts from the title/game-over screen and pauses/resumes a running game;
held-key repeats are ignored. It also works on initial page focus, without first
clicking the canvas. P remains a pause shortcut. Editable controls and focused
buttons/links retain native keyboard handling.
Keyboard hold-to-repeat is retained. There are no bottom action buttons, rules
description, visible keyboard instructions or test-status text. The level and
its progress bar are removed from the HUD; scoring multipliers remain line-based.
The compact tempo indicator describes increasing pressure without a level number.

Mobile input follows the [official Tetris Mobile swipe scheme](https://playstudios.helpshift.com/hc/en/16-tetris-mobile/faq/2953-tetris-controls/?l=en&p=web):
relative horizontal drag moves the piece, right-side tap rotates clockwise,
left-side tap rotates counterclockwise. Slow downward dragging soft-drops;
an intentional quick downward flick hard-drops exactly once. No up-swipe hold
is introduced, because this game has no hold rule. These are independently
implemented controls, not copied application code or assets.

`tetris-gestures.js` is a DOM-free recognizer with cell-relative sensitivity,
6–10 px jitter slop and a locked movement axis. Hard-drop requires a primarily
downward gesture of at least 28 px / 1.8 movement steps, no more than 320 ms,
and at least 0.45 CSS px/ms. Once a slow soft-drop has started, releasing never
hard-drops. Pointer capture permits off-board releases; multitouch, pause,
resize, pointer cancellation and new-piece spawning cancel pending gestures.
Spawn serials prevent a held finger from dropping/rotating a subsequent piece.
No swipe scroll, text selection or browser zoom is enabled on the board; the
rest of the page retains normal browser gestures. No gesture timers run idle.

Focus loss, hidden tab and leaving fullscreen pause safely;
resume is explicit. iPhone-compatible fixed-viewport fallback when element
fullscreen is unavailable. Board always stays 1:2; no stretched geometry.

## Graphics and performance

World Tour: ten original GPT-generated retro pixel-art Grand Prix panoramas depict
Monaco, Las Vegas, Austin, Shanghai, Suzuka, Monza, Silverstone, Singapore, Spa
and Abu Dhabi, with recognizable architecture, track environments and race cars.
They sit outside an opaque near-black 10×20 board
with a faint grid. All seven bright traditional tile colours have uncluttered
faces with a narrow retro bevel, without rivets, racing stripes or textures.
F1 styling stays outside the play surface: a red trim, small checkered flag,
pit-wall score panels and start lights. Backgrounds advance every ten cleared
lines, in shuffled sets of ten, with no adjacent repeat even between sets.
The first load starts at Monaco to match the server-rendered, high-priority image.
Starting or restarting keeps the currently displayed title-screen venue; the
first transition is only after ten lines. Reset invalidates old-run downloads.
Two reusable image layers crossfade for 1.4 seconds; reduced-motion switches
instantly. The next venue alone is prefetched. Images are asynchronously decoded
before switching: failed loads retain the old art, and stale completions cannot
override a more recent transition/reset. No permanent scenery animation loops.

Assets: `league/static/league/images/tetris-gp/*-retro-v1.webp`. Generated using
the built-in GPT image tool, one call per venue, with full prompts and source
basenames in `docs/tetris-gp-art-manifest.json`. Original resolution is retained;
WebP is lossless, with every decoded RGB pixel verified identical to source PNG.
To reproduce packing from the saved source directory, run
`python tools/pack_tetris_gp_art.py /path/to/generated_images/session`.

The initial garage illustration was generated **with built-in GPT imagegen** and
is retained only for the admin laboratory card at
`league/static/league/images/tetris-pit-garage-v1.png` (original 1536×1024).
It is not loaded by the game page. Code-native tiles are cached once for all
seven colours, not scaled/cropped pieces from an AI sheet.
Canvas respects device pixel density up to 3×. Idle and
paused states render once, not continuously. Only changed game states redraw;
no persistent particles or unbounded scene objects. Background and block art
are not quality-reduced. On resize, canvas repaints synchronously to prevent a
black frame, including when paused.

### Final generation prompt

Use case: stylized-concept. Asset type: production background illustration for an actual Formula 1 themed falling-block puzzle browser game. Create one beautiful premium retro 16-bit pixel-art Formula 1 pit garage interior, landscape 3:2. Calm charcoal navy metal garage, warm overhead workshop lights, turquoise tool cabinets, neatly stacked racing tyres and red-white kerbs at the bottom edges, partial red racing car nose low on the right, garage door opening onto a distant sunlit race circuit on the left. Centre 45 percent is a very dark quiet unbroken workshop wall with subtle panel seams, so a tall playable puzzle board can be overlaid on it. Keep all busy recognisable decorations towards outer left and right thirds; plenty of restrained dark negative space. Handcrafted crisp pixel clusters, controlled warm ivory, steel blue, muted racing red and small turquoise highlights, cinematic arcade mood, clean silhouettes, coherent retro videogame background, sharp detailed but not noisy. No letters, no words, no numbers, no game UI, no blocks or puzzle board drawn into image, no border, no logos, no watermark. Opaque image, landscape composition.

## Verification

### Soundtrack

**Grid Lights** is an original, deterministic chiptune composition written for
Pit Stack: A minor, 128 BPM, 32 bars / exactly 60 seconds. Lead pulse harmonics,
bass, arpeggios, synthesized kick/snare/hi-hat and stereo delay; no external music
or samples. `tools/compose_pit_stack.mjs` contains the complete score and offline
PCM synthesizer. The browser plays a rendered loop, not runtime synthesizers.

Published file: `league/static/league/audio/pit-stack-grid-lights-v1.m4a`, AAC
stereo, 44.1 kHz, approximately 1.04 MiB. Source master peak is 0.82, RMS ~0.132;
short edge fades and wrapped delay avoid a click at the loop boundary.
Rebuild with:

```sh
node tools/compose_pit_stack.mjs /tmp/pit-stack-grid-lights-v1.wav
afconvert /tmp/pit-stack-grid-lights-v1.wav league/static/league/audio/pit-stack-grid-lights-v1.m4a -f m4af -d aac -b 160000 -q 127
```

`tetris-audio.js` starts media and resumes Web Audio directly in the trusted
start/resume/sound gesture, per [MDN autoplay guidance](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API/Best_practices).
No title-screen autoplay; `preload=none`. A single MediaElementSource/GainNode
controls volume (default 28%, including on iOS). Mute and volume are stored in
`fastlap.pitStack.audio.v1`; denied/corrupt storage does not affect the game.
The speaker button opens a compact volume slider on focus/hover; arrows on the
slider and Space on the speaker retain their native keyboard behavior.

Music pauses on gameplay pause, focus loss, hidden page, game over and pagehide.
Resume keeps the playhead; a new run rewinds. Tempo rises smoothly by 1.8% per
difficulty tier, capped at 1.216× (~156 BPM), with
[pitch preserved](https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/preservesPitch).
Blocked play promises are caught and can be retried with the speaker button;
stale completions cannot resume music after pause/mute. No audio animation timers.

### Checks

- `node tests/tetris_engine.mjs`: rules, all seven pieces, rotation/walls,
  all four line clear counts, score/levels, pause, soft/hard drop, lock delay,
  restart and 150,000 seeded random mutation steps across 1,644 games.
- `node tests/tetris_gestures.mjs`: taps in both directions, jitter, relative
  drag/reversal, fast/slow downward input, exactly-once hard-drop, axis lock,
  multitouch, cancel/pause/new-piece protection and bounded input work.
- `node tests/tetris_scenery.mjs`: decode-before-show, single-next prefetch,
  network failure retention/recovery, stale load completion protection and reset.
- `node tests/tetris_audio.mjs`: no autoplay, persisted preferences, volume/gain,
  tempo cap, pause/play promise races, rejected playback retry, denied storage.
- `python manage.py test league.test_arcade_tetris league.test_arcade_library`:
  21 tests including access control, no mutations, no public links, rejected
  publication, removed UI and existing arcade regression tests.
- `PYTHON_BIN=/path/to/venv/python PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs
  node tests/tetris_browser.mjs`: real Django template rendered without a DB,
  real headless Chromium, 1440×1000, 390×844 and 320×568 screens, 2×/3× backing
  density, keyboard, trusted touch taps/drags/flick/cancel/multitouch and a
  finger held across spawning, pause/resume, inline/fullscreen/landscape geometry,
  no script exceptions. Also checks bounded scenery layers, shuffled tours without
  adjacent repeats across all ten venues, decoded full-resolution images, an
  opaque play surface, and samples all
  seven rendered tile colours for at least 4.5:1 contrast against the field.
  Real AAC decode/playback, looping, mute/volume, tempo, focus loss, pause/resume,
  preference persistence, and decoded signal headroom are checked too.
  Optional `TETRIS_PREVIEW_DIR` writes representative mixed-stack screenshots.
  Third-party fonts/Bootstrap are blocked for repeatability.
- Django migration check: no changes required. Existing pending unrelated
  changes remain unmodified and must not be bundled into a future commit.

Browser integration runtime failed to initialise; standalone local Chromium
was used for these UI checks. This is not a physical iPhone/WebKit or laptop
FPS benchmark, and no live deployment is implied.
