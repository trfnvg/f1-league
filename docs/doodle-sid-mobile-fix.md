# Visible Sid arena and broken drone — 2026-10-20

Mobile cover scaling bottom-aligns a fixed logical canvas. Browser chrome may
clip its upper region. Sid's arena used the full logical height, placing Sid
and his HUD above the actual visible top.

`visibleWorldHeight` now tracks container height divided by uniform display
scale. Sid's arena uses that height for the boss, floor/ceiling, platforms,
starting position, hazard entrance, HUD and victory portal. Resizing rebuilds
the arena and remaps player/projectile/cinematic positions using the old and new
arena heights even when the full logical canvas height does not change.
Normal scrolling levels retain fixed logical bounds and existing zoom behavior.

Stomping a summit drone still gives an 830 bounce and the normal enemy frag.
It now selects a separate broken sprite with stationary snapped rotors, briefly
emits five small sparks, tumbles and drifts while falling, and leaves only after
crossing the bottom boundary. It cannot attack again; an already-released nut
continues its existing trajectory. Broken artwork renders at its natural aspect.

## Artwork

Built-in GPT image generation, not CLI. Saved project asset:
`league/static/league/images/doodle-jump/summit-drone-broken-v1.png`.
Reference: `league/static/league/images/doodle-jump/summit-drone-v1.png`.
The new sprite loads with the summit chapter, not during startup.

Prompt:

Use case: precise-object-edit. Use reference sheet only for exact identity and crisp 16-bit pixel-art style of the red scout drone. Output ONE isolated damaged drone sprite, side view, level horizontal body, entirely contained with transparent margins. Same scarlet shell, ivory stripe, yellow shield, black carbon arms and camera. After being stomped from above: cracked dented red shell, snapped bent rotor blades that are stationary, one arm drooping, dark camera lens, empty open claw, no held nut. Readable broken silhouette with exposed metal. Keep all parts attached to the drone body, no separate debris, no sparks, no smoke, no motion trails, no glow, no scenery, no text. True transparent alpha background outside hard silhouette. Game will animate tumbling and sparks.

## Verification

Native Canvas suite exercises mobile 390×650, 390×560, 430×740, 844×390 and
390×844, plus desktop sizes, asserting the entire Sid sprite and player fit in
the visible arena. Existing ten-hit/reflection/victory/resize tests remain.
Drone tests verify the broken sprite, upward player bounce, falling drift,
no further shot, offscreen cleanup and admin API isolation. Screenshots include
the actual bottom-aligned 390×650 crop and the falling wreck.
Physical iPhone testing and live deployment completion are not claimed.
