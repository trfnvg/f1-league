# Antarctica game assets

Generated with the built-in GPT image generation tool on 2026-10-15.
Original PNG resolution and console transparency are preserved.

## Background

Asset: `league/static/league/images/doodle-jump/antarctica-canyon-v1.png`

Prompt:

> Use case: stylized-concept. Production game background for a retro 16-bit Formula 1 cowboy vertical jumping game. Antarctica glacial canyon, enormous layered ice cliffs only at left and right margins, distant snowy Antarctic mountains and soft polar mist through the open central corridor. Restrained desaturated steel blue, navy ice shadows, pale cyan snow, faint violet polar sky. Beautiful detailed crisp pixel art, readable clustered pixels, no blur, no painterly brushwork. Portrait vertical composition. No floor at bottom, no horizon line cutting the image, continuous ice canyon going vertically beyond top and bottom, suitable for scrolling upwards with crossfade repeat. Center 50 percent quiet with low contrast to keep tiny characters and platforms readable. No people, no text, no HUD, no platforms, no logos, no screenshot frame. Full bleed background art only.

## Control console

Asset: `league/static/league/images/doodle-jump/f1-control-console-v1.png`

Prompt (transparent background enabled):

> Use case: stylized-concept. Production sprite for 16-bit retro Formula 1 platform game. ONE standalone Formula 1 race car control console on a sturdy steel pedestal, front view with very slight view of upper surface. A wide dark graphite telemetry monitor showing simple mint green outline diagram of a Formula 1 car, beside it a HUGE raised round RED PUSH BUTTON occupying the right third of the console top, chrome rim. Exposed cables and tiny amber indicators. Readable simple silhouette at small in-game size, detailed crisp pixel art, chunky pixel clusters, dark outlines, vintage industrial garage mood. Entire console visible, centered, generous transparent padding. Real transparent background. No characters, no floor, no shadows outside sprite, no scene, no text, no multiple views. The large red button must be very obvious.

## Integration

The scene begins once per run at 8000 points after entering the forgotten paddock.
Physics pauses during the 11.2-second control-room scene and the 9.8-second cave
arrival. Separate cinematic poses animate the established hero and Toto through
arrival, shove, button press and portal capture. A camera close-up punctuates the
press, followed by a matching cold-white cut to the cave. Russell lands, recovers,
walks right out of the cave and meets Sid. Sid reacts, waves and points up before
Russell jumps onto the first actual gameplay platform. Its position and feet
baseline match the last cinematic frame. Score and bonuses are retained.
The Antarctica background scrolls downward with ascent and blends upright tiles
without allocating a full-size offscreen background canvas. Snow and ice
platforms are drawn in Canvas. Existing platform collision dimensions remain.
The administrator previews (full sequence and cave arrival only) use the
unranked test-run guards. The cinematic HUD treatment retains fullscreen access.

Validation: native Canvas rendering at mobile and desktop dimensions, including
resizes during all scene phases; score preservation, threshold and once-only
transition, safe landing, restart cleanup, and no score/attempt writes in preview.
An actual iPhone/Safari session was not available for verification.

## Cinematic companion assets (2026-10-15)

All four assets below were generated using the built-in GPT image tool. PNG
resolution and transparency are preserved. Character poses are isolated before
use: Toto's unequal gutters are explicitly mapped; the six Russell poses were
extracted by connected alpha regions and repacked into equal cells without
altering their source pixels. All cinematic actors share a boot baseline.
The original gameplay hero sheet is unchanged.

### Cave panorama

Asset: `league/static/league/images/doodle-jump/antarctica-cave-arrival-v1.png`

> Use case: stylized-concept. Production wide background panorama for a polished 16-bit pixel art Formula 1 cowboy platform game cinematic. WIDE side-scrolling composition, 3:2 landscape. A large Antarctic ice cave occupies the LEFT HALF: dark navy cavern behind, hanging crystalline icicles, frozen rock arch framing its opening. Smooth walkable snowy ledge across the full bottom quarter. On the RIGHT HALF the cave opens onto a bright quiet Antarctic glacial valley, distant pale steel blue mountain walls, a soft polar sky above and open space above the ledge for game characters. The player will emerge from inside the cave LEFT to RIGHT. Side-on platform game view, NOT perspective looking down a tunnel. No characters, no platforms in air, no text, no UI. Crisp clustered pixel art with deliberate square pixels and restrained navy/icy cyan/slate palette, beautiful cinematic depth, detailed but not noisy. Cave interior dark on left, exit at x=55%, luminous snowy exterior on right. Snow floor around 78 percent image height. No black borders. Do not paint characters.

### Sid poses

Asset: `league/static/league/images/doodle-jump/sid-cinematic-poses-v1.png`

> Use case: stylized-concept. Transparent sprite animation sheet for a retro 16-bit pixel platform game, SID THE SLOTH FROM ICE AGE, recognisable long narrow neck, tan beige shaggy fur, big rounded brown/pink nose, protruding wide-set eyes, two big buck teeth, short legs, long arms, charming goofy friendly expression. FOUR separate full-body poses in one horizontal row, each in its own equally wide cell, facing LEFT toward arriving player. Pose1 relaxed friendly idle; pose2 surprised leaning back with raised hands; pose3 greeting with one arm raised; pose4 pointing upward with a grin. Same character proportions, same size, aligned ground/feet baseline, consistent tan palette with dark pixel outline. High-quality crisp pixel art, readable clusters at small game sprite scale, not smooth 3D, no blur. Whole bodies visible, wide EMPTY TRANSPARENT gutters between poses, absolutely no overlap, transparent background, no scenery no labels no shadows outside sprites no extra characters no panel borders.

### Toto poses

Asset: `league/static/league/images/doodle-jump/toto-cinematic-poses-v1.png`

> Use case: stylized-concept. Transparent production sprite animation sheet for a polished 16-bit retro video game cinematic. Character: recognisable TOTO WOLFF, tall middle-aged Austrian Formula 1 team principal, wide angular face, strong nose, downturned mouth, distinctive swept side parted dark brown hair, furrowed eyebrows and sinister scowl. Black fitted team manager jacket and dark trousers, white shirt collar, subtle teal seam, black shoes. Not a cowboy, no hat, no helmet, no UFO. FOUR full-body side/front three-quarter poses in ONE horizontal row in equally wide cells, all same body/head dimensions and aligned soles. Pose 1: facing LEFT, standing ominously upright, hands at sides. Pose 2: facing LEFT with torso leaning into a strong SHOVE, both arms extended to the left at chest height, legs braced. Pose 3: facing RIGHT in side profile, leaning forward reaching with right arm and pointing finger toward an imaginary big console button at chest height to the right, stern expression. Pose 4: facing slightly left/front, arms folded, evil satisfied smirk. Distinct expressive hand silhouettes. Consistent pixel art with sharp chunky pixel clusters, same individual in every pose, detailed recognizable face, dramatic navy dark outlines, no smooth 3D. Transparent background, entire figures visible, wide empty transparent gutters between poses, NO overlaps, no floor, no text, no labels, no props, no extra limbs.

### Russell companion poses

Asset: `league/static/league/images/doodle-jump/russell-cinematic-poses-v1.png`

Reference: `western-russell-toy-hero-v3.webp` (existing playable character).

> Create a companion pixel-art animation sheet for the cowboy toy character in the provided image. Keep the same cream cowboy hat, friendly brown-haired face, white and teal racing cowboy outfit, sheriff star and brown boots. Six equally spaced full-body poses in a horizontal row on a transparent background: standing facing right; walking right with left foot forward; walking right with right foot forward; leaning backward surprised with arms raised; crouched landing; standing looking upward to the right. Same character scale in all cells, aligned soles, generous transparent gaps, no cropped limbs, crisp pixel art matching the input, no text and no scenery.
