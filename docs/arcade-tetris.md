# Pit Stack · released F1 falling-block game

## Access and scope

Open **Аркады → Pit Stack**, or `/arcade/play/tetris/`. Guests can practice;
authenticated players save verified results. Staff can use `?admin_test=1`
from the lab without creating attempts or changing standings.

Staff choose permanently available games at **Управление аркадами → Постоянная
библиотека**. Defaults preserve Flappy/Cowboy and include newly released Tetris.
An active competition is independently visible even without its permanent checkbox.
Unchecked games disallow new free runs/direct access; completed records remain.
The winner can still access the wheel after the deadline until the race starts.
Minesweeper remains staff-only. No running contest is automatically replaced.

Migration 0063 adds the library preference and separate TetrisAttempt/TetrisRecord
tables. Admin can assign and publish Tetris for a future event. Its event standings,
deadline freeze, all-time records and winner's wheel use only Tetris attempts.

## Authoritative results

POST start issues a random 32-bit seed and rules version 1, binds the current
competition and increments that user's attempt counter (maximum 30 starts/minute).
The client uses that seed, a shared LCG and fixed 60 Hz simulation ticks. It submits
ordered input ticks, never a score, board or chosen pieces. `tetris_rules.py`
replays physics independently and computes the saved score. Results are owned by
the logged-in user; CSRF remains enabled. Version, wall-clock duration, command
ordering/types, game-over and resource bounds are validated. Invalid replays consume
the attempt; a retry of an already saved attempt is idempotent. In-flight legitimate
runs may finish after a visibility change, but cannot enter a closed event's standings.

The verifier bounds a run to four active hours / 30,000 inputs / eight commands per
tick / 800 KB request; reaching the time/input bound ends the client run and saves
its verified score. Pause/hidden-tab time is not replay time. The raw replay is kept
with the attempt for audit. Network failures retain the proof in memory for retry;
no localStorage high score is authoritative. This validates scores and physics, not
human identity: automation/bots and deliberate slow play remain separate problems.

## Rules and controls

The user's “original tennis rules” was interpreted as “original Tetris rules”.
This game uses familiar classic falling-block rules, not an exact emulator
of any one historical release: 10 columns × 20 visible rows, all seven four-cell
shapes, uniform independent random pieces, one-piece preview, bidirectional rotation
with small horizontal wall adjustments only, 350–220 ms lock grace capped at ten
movement/rotation resets. No hold or enemies. The selected event's winner can use
the site's existing wheel; wheel prizes never modify Tetris physics or score.

Full rows clear together after a 180 ms visual effect. 1/2/3/4 rows award
40/100/300/1200 × the current one-based level; soft drop awards 1 per cell, hard
drop 2. Every ten lines increases the score multiplier and advances the gravity
table by one level. Time played never increases difficulty or music tempo.
Gravity follows the NES NTSC frames-per-cell table, mapped to logical 60 Hz:
48,43,38,33,28,23,18,13,8,6,5,5,5,4,4,4,3,3,3,2,2,2,2,2,2,2,2,2,2,1.
Our level 1 corresponds to NES level 0: 800 ms per cell initially, 100 ms at
90 lines, 33.33 ms at 190 lines, 16.67 ms at 290+ lines. This is a speed-curve
adaptation, not cycle-exact NES emulation; randomization, rotation, modern hard
drop/ghost and lock grace remain our existing rules. Table reference:
[NES disassembly, framesPerDropTable](https://raw.githubusercontent.com/CelestialAmber/TetrisNESDisasm/master/main.asm).
Lock grace decreases by 8 ms per line-based tier, bounded at 220 ms.
Pauses/hidden tabs do not accrue time. Fractional gravity time is retained,
with a tiny floating-point tolerance for exact frame boundaries and multiple
cell steps when needed. Soft drop never resets pending natural-gravity time,
so holding Down cannot slow a fast falling piece.
New-piece obstruction or lock above the board ends the run.

Arrows or physical A/D/W/S (also work with Russian keyboard layout), X for
clockwise / Z for counterclockwise rotation. Space is the primary hard-drop key;
Enter/NumpadEnter is an alternative. Both start from the title/game-over screen
and resume a paused game, without dropping that resumed piece. P toggles pause;
Esc pauses, including during a line clear. Held-key repeats never hard-drop the
next piece. Start also works on initial page focus, without first clicking the
canvas. Editable controls and focused
buttons/links retain native keyboard handling.
Keyboard hold-to-repeat is retained. There are no bottom action buttons, rules
description or test-status text. The title overlay has a compact keyboard/touch
hint appropriate to the input device. The level and
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

### Landing guide and feedback

The default-on landing guide uses `Game.landing()`, the same read-only projection
used by hard drop. It traces only the outer silhouette, at 46% stroke opacity
with a 3.5% tint, and hides when the active piece is already at its landing
position. The dotted-piece toolbar button toggles it and stores the choice in
`fastlap.pitStack.ghost.v1`; disabled/corrupt storage keeps the guide usable.

`tetris-feedback.js` uses a separate transparent canvas at the same DPR as the
board. Locked tiles gently compress by at most 5.5% for 150 ms, with a small
grounding glint. A fast hard drop leaves a narrow, faint 150 ms pixel trail
(maximum seven cells long); short drops do not trigger it. Completed rows charge
with a restrained cyan light pass (warm gold for four lines), then dissolve
left-to-right within the existing 180 ms clear window. Their original colours
become 80 rotating, edge-lit pixel fragments for a four-line clear, bounded at
120 live fragments, which expire after 320–425 ms. Thin row echoes fade in
300 ms and are capped at eight. Four lines trigger one finite pair of five-light
rails and a soft golden frame impulse outside the playfield, lasting <1 second.
Reward text sits above the score panel, not over falling pieces.

Effects observe bounded lock/clear snapshots without changing collision, gravity,
score, input or next-piece timing. Pause freezes both canvas effects and CSS
lights and frame; restart/game over clear them. One cached gradient is reused
for light passes: no per-frame blur filters, external textures, new assets or
additional render loop. Reduced motion disables squash, trails, chips, echoes
and animated lights (a steady row/frame indication remains). Settled effects
do not force redraws, and HUD/next-piece rendering is skipped on effect-only frames.

### Soundtrack

**Parc Ferme** is an original, mellow retro/orchestral racing composition written
for Pit Stack: D minor, 96 BPM, 80 bars / exactly 200 seconds (3:20). Soft sustained
pads, low brass-like melodic answers, sparse arpeggios, quiet percussion, and
longer breathing sections evoke the atmosphere of F1 broadcast scores without
quoting the official melody. No external music or samples.
`tools/compose_pit_stack_v2.mjs` contains the complete score and offline
PCM synthesizer. The browser plays a rendered loop, not runtime synthesizers.

Published file: `league/static/league/audio/pit-stack-parc-ferme-v2.m4a`, AAC
stereo, 44.1 kHz. Master RMS is capped at 0.075 and peak at 0.62;
short edge fades and wrapped delay avoid a click at the loop boundary.
Rebuild with:

```sh
node tools/compose_pit_stack_v2.mjs /tmp/pit-stack-parc-ferme-v2.wav
afconvert /tmp/pit-stack-parc-ferme-v2.wav league/static/league/audio/pit-stack-parc-ferme-v2.m4a -f m4af -d aac -b 160000 -q 127
```

`tetris-audio.js` starts media and resumes Web Audio directly in the trusted
start/resume/sound gesture, per [MDN autoplay guidance](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API/Best_practices).
No title-screen autoplay; `preload=none`. A single MediaElementSource/GainNode
controls volume (default 22%, including on iOS; existing user choices preserved). Mute and volume are stored in
`fastlap.pitStack.audio.v1`; denied/corrupt storage does not affect the game.
The speaker button opens a compact volume slider on focus/hover; arrows on the
slider and Space on the speaker retain their native keyboard behavior.

Music pauses on gameplay pause, focus loss, hidden page, game over and pagehide.
Resume keeps the playhead; a new run rewinds. Tempo rises only 0.4% per
difficulty tier, capped at 1.048× (~101 BPM), with
[pitch preserved](https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/preservesPitch).
Blocked play promises are caught and can be retried with the speaker button;
stale completions cannot resume music after pause/mute. No audio animation timers.

### Checks

- `node tests/tetris_engine.mjs`: rules, all seven pieces, rotation/walls,
  all four line clear counts, score/levels, pause, soft/hard drop, lock delay,
  restart and 150,000 seeded random mutation steps.
- `node tests/tetris_gestures.mjs`: taps in both directions, jitter, relative
  drag/reversal, fast/slow downward input, exactly-once hard-drop, axis lock,
  multitouch, cancel/pause/new-piece protection and bounded input work.
- `node tests/tetris_scenery.mjs`: decode-before-show, single-next prefetch,
  network failure retention/recovery, stale load completion protection and reset.
- `node tests/tetris_audio.mjs`: no autoplay, persisted preferences, volume/gain,
  tempo cap, pause/play promise races, rejected playback retry, denied storage.
- `node tests/tetris_feedback.mjs`: physics isolation, subtle tile compression,
  particle cap/expiry, finite lights, pause, reduced motion and idle cleanup.
  Engine checks also cover projection for seven pieces/rotations on uneven stacks
  and exact agreement between guide and hard-drop footprints.
- `python manage.py test league.test_arcade_tetris league.test_arcade_library league.test_arcade_control`:
  library visibility, public release, staff-only publishing, isolated practice,
  server replay, saved/frozen records, winner wheel and existing arcade regressions.
- `node tests/tetris_session.mjs`: seeded run, fixed ticks, input-only proof, pause,
  CSRF header, retry, exactly-once finish, guest/admin isolation.
- `PYTHON_BIN=/path/to/python node tests/tetris_replay.mjs`: independent JS/Python
  agreement for 120 full seeded runs and twelve low/high-speed line-clear fixtures.
- `PYTHON_BIN=/path/to/python PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs node tests/tetris_release_browser.mjs`:
  actual public page, seeded start, real keyboard game-over, Python verified score
  and refreshed leaderboard at desktop/mobile widths.
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
