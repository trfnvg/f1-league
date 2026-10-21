# Endless continuation after the final boss

## Behaviour

The final bathtub boss still requires eight hits. Its reward is awarded once, the victory animation and eagle flight finish, then a 2.2-second anomaly portal opens. Only a cleared final boss in the anomaly phase can call `enterEndless`. Height alone cannot unlock it. The same run, score components, attempt ID and elapsed time continue. The portal places the hero on a broad safe foothold at the existing maximum height, preserving height points exactly; three seconds of entry protection cover the first jump. Death uses the existing overlay, personal record and single finish request. Restart clears all endless state.

## Planning and reachability

`league/static/league/doodle-endless.js` contains a pure `Director`, independent of rendering, DOM and saving. It selects among four short route patterns, never repeating the previous pattern at a pattern boundary. Every primary foothold is permanent and stationary. Gap grows from 94–120 to 106–152 units. Horizontal reach uses the descending root of `720t - 620t²`, discounts acceleration/reversal time, and reserves another 34% of the unboosted horizontal travel. No rocket, enemy stomp or spring is required to complete the route.

Moving, breakable and spring options are additional footholds between permanent anchors. Their incoming and outgoing arcs reserve the complete 12-unit moving range. Primary widths reduce from 78 to 66 units. Optional footholds become more frequent as difficulty rises. No gameplay image is regenerated or compressed.

The engine generates beyond the viewport (canvas height plus 420 world units), retains only a scalar last-anchor record, and prunes old platforms, enemies, hazards, power-ups and marshals through the existing compacting loops. Ordinary enemies are capped at two and falling tyres at three. Enemies and tyres enter above view, with an initial arrival buffer. A single viewport-sized backdrop buffer is retained during a fade and released afterwards. There are no new event handlers, timers or unbounded route/history arrays.

## Worlds

All seven scenery regions are reused: desert paddock, canyon, sky, space, forgotten paddock, Antarctica and high-altitude paddock. Each next world is selected uniformly from the six alternatives. A switch is scheduled 1,500–2,500 additional points ahead; the upcoming asset stage prefetches 250 points before that threshold. If it is not ready, the current world continues until it is, rather than freezing physics or showing partial art.

World changes crossfade over 1.5 seconds without changing player position, velocity, camera, score or existing footholds. Existing platforms retain the world/style in which they were generated. Future platforms use the new world's existing artwork. Original tiled backgrounds and cached seams are reused; desert/canyon use their existing finite painting and slow parallax. Story triggers, boss encounters, cinematic NPCs and winter memory are disabled only while endless mode is active. Ordinary tyres, piranhas, falling wheels, sky hawks/ducks, marshals and rare rockets use existing physics and collision routines.

Difficulty is moderate until 18,000 points, ramps linearly to 25,000, then stays capped. Character gravity, steering speed and regular jump impulse are unchanged. Backend accepts scores up to the existing positive 32-bit storage limit, 2,147,483,647 (previous API ceiling was 1,000,000); Flappy's existing ceiling stays 500. No migration is needed.

## Files

- `league/static/league/doodle-endless.js`: world and route planner.
- `league/static/league/doodle-jump.js`: final portal, continued physics, rendering, cleanup, narrative guards.
- `league/templates/arcade_doodle_jump.html`: ordered deferred module inclusion and updated admin finale label.
- `league/arcade_library.py`: score range compatible with long runs.
- `tests/doodle_endless.mjs`: seeded route/reachability and scheduling simulation.
- `tests/doodle_streaming.mjs`: native Canvas integration and original story regressions.
- `league/test_arcade_library.py`: real Django attempt/record persistence for large results.
- `docs/doodle-endless.md`: implementation and validation notes.

## Verification

`node tests/doodle_endless.mjs`: 720,000 primary arcs and 272,617 optional two-way arcs, across 48 seeded phone/desktop plans beyond 100,000 points; all seven worlds, non-repeating switches and capped difficulty.

`CANVAS_MODULE=/path/to/@napi-rs/canvas/index.js node tests/doodle_streaming.mjs`: original asset loading, camera, collision, winter/space/summit and boss tests; victory-only entry; score continuity and one-time portal; all 42 ordered world pairs on each viewport; a virtual height-stepped climb beyond 100,000 with bounded live objects and no narrative replay; one final save request; restart reset. These long runs step height to stress generation/cleanup, rather than claiming a human or physics bot played the complete 100,000-point run.

`python manage.py test league.test_arcade_library`: 15 tests, including saving 50,000, 100,000 and 1,000,001, duplicate-finish rejection and invalid overflow rejection. Executed from an isolated archive of HEAD overlaid with only task files, with a temporary test database; unrelated dirty working-tree files and the workspace database were not used or changed.

`python manage.py check`, `collectstatic --noinput`, JavaScript syntax and task-file whitespace checks passed. Native Canvas preview of the mobile entry was inspected. No physical iPhone/Android FPS or hours-long browser heap profiling was performed. Reachability guarantees the platform route; hazards still require the player to dodge, as in the story game.
