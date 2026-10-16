# Sid: mandatory Antarctic boss

## Rules and flow

At 10000 total run points in Antarctica (after arrival), a one-time gate starts
Sid's arena. Exactly TEN reflected whole cans must hit Sid. Reflecting a can
alone does not count; the homing return projectile must reach the boss. The
next chapter is inaccessible while HP is greater than zero. The score/peak and
camera remain locked during combat; normal mobs, hazards and pickups are
cleared and world generation pauses. Flight/rocket/soft-jump boosts are reset.
An icy floor and a reachable ladder remain available at every viewport size.
The roof physically blocks bypassing the arena, even with admin free flight.

Attack cycle: entrance -> ice warning -> two marked falling-ice lanes (two safe
lanes) -> can warning -> an arcing intact cyan-rimmed can plus a crushed can.
Ice and crushed cans are lethal without protection. A descending foot crossing
the intact rim reflects the can and bounces the hero; side/bottom contact is
still dangerous. Warning duration has a safe minimum. Missed cans lead to a
new cycle, not an automatic defeat. Active projectile count is bounded.

Each confirmed impact removes exactly one HP, plays a recoil frame/shake and
clears remaining hazards. After hit ten: recoil, last sip, wings sprout, two
wing poses alternate during an eased take-off, the roof shatters, and a portal
opens. The hero first settles on a landing surface, then is drawn into the
portal. The 6.8-second victory sequence is protected. On successful transition,
+500 points are awarded once, and the generated high-altitude Alpine paddock
opens. The new background pans upward in source space (landmarks move down),
with aspect-preserving cover and later looping cloud sprites. Existing ice
platforms and piranhas continue there; old cone/Kimi hazards and the old
Antarctic entrance do not retrigger. A restart resets the boss and chapter.

The staff-only button above the game launches a 10000-point sandbox battle
without recording an attempt or score. It uses the same ten-hit combat logic.
Arena geometry/projectiles reflow on fullscreen/rotation without resizing source
artwork or degrading DPR. All artwork remains behind staged loading barriers.

## Art

Built-in GPT image generation was used, preserving generated PNG resolution and
alpha. The final chapter's background is opaque. The three four-frame strips
have inspected transparent gutters; no intermediate sprite compression or
resolution reduction is applied. Paths relative to the repository:

- `league/static/league/images/doodle-jump/sid-boss-attack-v1.png`
- `league/static/league/images/doodle-jump/sid-boss-finale-v1.png`
- `league/static/league/images/doodle-jump/sid-boss-props-v1.png`
- `league/static/league/images/doodle-jump/summit-paddock-v1.png`

### Exact prompts

#### attack

Use case: stylized-concept. Asset type: production transparent 2D pixel-art sprite animation strip for a retro Formula 1 platform jumper boss fight in an Antarctic ice cave. Subject: Sid the sloth from Ice Age, recognisable wide-set bulging eyes, broad pink nose, long neck, protruding front teeth and long curved claws, wearing a dark navy Red Bull Formula 1 racing suit with red/yellow bull motif. Exactly FOUR full-body animation poses: smug idle holding a blue-silver energy drink can; vigorously shaking a small icy refrigerator beside him with both claws; exaggerated wind-up preparing to throw a can; fully extended throwing pose with an EMPTY throwing hand. Same character identity, scale, feet baseline in every cell. The refrigerator remains a small prop within each cell, never overlaps another cell. Style: polished detailed 16-bit SNES pixel art, crisp navy contours and deliberate pixel clusters, cool blue highlights, restrained Red Bull navy/red/yellow accents. Composition: exactly FOUR separate cells in ONE horizontal row, equally spaced with generous transparent gutters. Each full object/character fits its cell, no overlap, no cropped feet or wings. Completely transparent alpha background. No scenery, no floor, no text, no labels, no grid, no watermark. Match retro game rather than smooth 3D illustration. Wide landscape strip; final character appears 100–150px tall in play.

#### finale

Use case: stylized-concept. Transparent retro 16-bit game animation sprite strip. Four isolated full-body poses of Sid, the friendly adult cartoon sloth from Ice Age, in navy racing overalls with red and yellow accents. Left to right: comically surprised, sipping a small plain silver can, delighted with a pair of tiny white feather wings newly spread on his back, airborne flapping those tiny wings with feet dangling. Wholesome slapstick game victory scene. Same long neck, wide-set eyes, pink nose, buck teeth and same suit in all four cells. Crisp detailed pixel art, dark outlines. One horizontal row of four equal cells, generous transparent gutters, no cropping, no overlap. Transparent alpha background, no scenery, no text, no watermark.

#### props

Use case: stylized-concept. Asset type: production transparent 2D pixel-art sprite animation strip for a retro Formula 1 platform jumper boss fight in an Antarctic ice cave. Subject: FOUR isolated production-ready game objects, left-to-right: one intact blue-and-silver energy drink can with a bright cyan rim and red bull motif, recognisable easy-to-bounce-on flat upper rim; one dangerous crushed blue-silver drink can with dark red edges; one large jagged translucent blue ICE BOULDER, angular and threatening; one small frost-covered dark navy/red Formula 1 energy-drink refrigerator with its door cracked open and cold vapour contained within the cell. One entire object per cell. No characters, no extra scattered objects. Style: polished detailed 16-bit SNES pixel art, crisp navy contours and deliberate pixel clusters, cool blue highlights, restrained Red Bull navy/red/yellow accents. Composition: exactly FOUR separate cells in ONE horizontal row, equally spaced with generous transparent gutters. Each full object/character fits its cell, no overlap, no cropped feet or wings. Completely transparent alpha background. No scenery, no floor, no text, no labels, no grid, no watermark. Match retro game rather than smooth 3D illustration. Wide landscape strip; final character appears 100–150px tall in play.

#### summit

Use case: stylized-concept. Asset type: tall vertical background painting for the NEXT LEVEL of a polished 16-bit pixel-art Formula 1 platform jumper, immediately after an Antarctic ice cave boss. A high-altitude Alpine racing paddock ABOVE a glacier: lower part has small navy and red Formula 1 garages on distant mountain ledges, pale blue ice peaks and cable gantries, middle part opens into majestic pale mountains and clouds, top half transitions to calm clear blue sky with sparse soft cloud wisps. Premium detailed SNES pixel art, restrained colours, navy/red/yellow pit-building accents, bright but not garish, readable low-contrast central playfield. Side-on background only, no foreground platforms, no characters, no UI, no text, no watermark. One cohesive continuous vertical environment for the camera to pan UP from bottom to top, no panels or horizontal seams.


## Checks

Native Canvas regression tests cover 9999/10000 triggering, no score/camera
farming, ten actual returning impacts, pre-victory gate, protected/loss cases,
attack telegraphs, viewport reflow, victory frames, delayed summit loading,
once-only bonus, no retrigger, admin isolation and restart. Phone/desktop
sized PNGs are rendered for inspection. These are not real Safari/Chrome FPS
measurements.

