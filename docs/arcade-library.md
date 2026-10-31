# Arcade library and competition history

Built-in GPT imagegen covers saved in `league/static/league/images/arcade-doodle-cover-v1.png` and `arcade-flappy-cover-v1.png`. Original generated resolution retained.

## Doodle cover prompt

Use case: stylized-concept. Production cover art for browser arcade library card, landscape 3:2 composition. Game title will be added in HTML; NO text or letters. Reference 1 is hero character identity, reference 2 is scene and pixel style. A cheerful cowboy Formula 1 toy driver (exact white suit, cream cowboy hat, brown boots, turquoise trim from reference) leaps upward from a sandstone platform through sunlit western canyon with a little blue sky above. Preserve game identity, polished crisp 16-bit pixel art, warm sandstone and calm blue palette, clean strong silhouette, purposeful pixel clusters. Driver in right half, less busy left third for UI crop. No UI, borders, logos invented, no watermark. Opaque illustration.

## Flappy cover prompt

Use case: stylized-concept. Production cover art for browser arcade library card, landscape 3:2 composition. Game title will be added in HTML, NO text or letters. Reference 1 is the recognizable banana Leclerc character: yellow banana costume with a smiling dark-haired racing driver's face visible in opening; translate into sharp charming 16-bit pixel-art game hero. Reference 2 is game track scenery. Banana floats midair between two red-white racing barrier gates at a sunny seaside Formula 1 paddock, blue mountains and grandstand distant, turquoise sea and red-white kerbs. Hero right of centre, open calmer blue space left for crop. Polished crisp pixel clusters, same clean retro arcade treatment as cowboy Formula 1 jumping game. No UI, frame, words, captions, watermark. Opaque illustration.

## Release behaviour

`/arcade/` is the library. Both published games remain playable, including after a deadline. Starts create all-time attempts; only starts inside an open selected contest bind to its immutable game/event record. Finishes after the deadline update global records only. Event standings and attempt totals freeze once under the competition lock. Settings changes cannot delete old contest snapshots. Historical Flappy closures are imported by migration 0038, using existing attempts and the persisted winner when old detailed attempts are unavailable.

The current competition retains the wheel through the race start. Archived games have no wheel; free play cannot alter its eligible attempts. The admin page explicitly selects a game and future-deadline event. Admin test links do not save results.

## Staff test lab

`/arcade/control/` puts Cowboy GP, Pit Lane Flight, Pitwall Sweep and Pit Stack in one card grid (two columns on phones). Every card launches its existing staff test route; the jumping game no longer enables the optional flight cheat automatically. Competition publishing and the isolated wheel demo are separate, initially collapsed sections. Only the two released games can be published. An expired event remains visible, and pausing does not require selecting a new event.

Minesweeper test runs are local-only: no start/finish POSTs or leaderboard polling. Its server endpoints also refuse to persist staff test attempts, even if called directly. Ordinary players cannot enable this mode. Django admin registrations for Doodle records, Minesweeper attempts, duel artwork and Flappy records are removed; their models, data and migrations are unchanged.

Regression coverage: `league.test_arcade_control` and `tests/arcade_control_browser.py --browser chromium|webkit --output-dir /tmp/fastlap-lab`. The browser fixture uses only an in-memory database and checks seven viewport widths, all four actual game links, active/expired/empty states, collapsible publishing tools and absence of test POSTs.

Game pages display exactly one leaderboard: the selected open competition until its deadline, otherwise all-time records. Polling and attempt responses use the same selection and provide the current title, so the page switches without reloading. Personal all-time best remains separate from competition scores. Saved historical standings are retained in the database but are not rendered as extra tables on game pages. Featured artwork and library covers preserve the full original 3:2 composition; the featured text sits beside the image on desktop and below it on mobile.

Cowboy GP requests fullscreen inside the play interaction and retains its fixed viewport fallback. Pit Lane Flight starts inline; an explicit fullscreen button and exit control remain available. Library cards list the newer Cowboy GP before Pit Lane Flight and use dark red play buttons. Standard-density desktop screens render Cowboy GP at twice CSS resolution. An admin-only post-Sid button previews the victory cinematic and enters the summit without recording a run. Actual browser testing was unavailable in this session. Server and native Canvas regression tests cover these behaviours along with deadline/late finish, frozen attempts, archival wheel removal, publication, test isolation and duplicate submissions.
