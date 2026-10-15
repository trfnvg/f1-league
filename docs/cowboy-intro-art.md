# Cowboy GP — scaffold opening

Generated with GPT Image (imagegen), transparent background. The existing gameplay hero was used as the character reference; gameplay sprites were not replaced.

## Runtime assets

- `league/static/league/images/doodle-jump/western-intro-scaffold-v1.png`: empty timber scaffold.
- `league/static/league/images/doodle-jump/western-intro-ferrari-v1.png`: standing Ferrari driver.
- `league/static/league/images/doodle-jump/western-intro-russell-v1.png`: three Russell poses (standing, lifting loop, crouching).

The rope, dialogue, camera easing and jump trajectory are drawn/animated in Canvas. The scene lasts 5.3 seconds; Space, a canvas tap or the skip button ends it. Ranking time/attempt registration starts only after the scene. Admin flight/portal shortcuts bypass it.

## Generation prompts

### Scaffold — generate

Use case: stylized-concept. Asset type: transparent game scenery sprite for a retro western platform game introduction. Draw a weathered wooden western gallows SCAFFOLD, a theatrical empty stage prop, in crisp polished 16-bit pixel art. Wide raised horizontal wooden deck across the lower quarter; short timber legs under it and small steps on far left. A single tall vertical timber post at the FAR RIGHT with a long horizontal beam projecting to the left above the stage and one diagonal brace near the right post. Empty space under the beam for two characters to stand. Front view with slight visible deck depth, strong dark outlines, warm dusty timber, iron nails. Complete isolated prop, no people, no ropes, no nooses, no text, no scenery or ground. True transparent alpha background. Landscape composition with large safe margins. Board top surface is flat and easy to align standing sprites with. Match a cheerful detailed retro western F1 game.

### Ferrari driver — generate

Use case: stylized-concept. Asset type: single transparent character sprite for a western retro F1 game intro. A cheerful adult Ferrari racing driver standing upright, facing slightly toward the RIGHT, dry amused half-smile, looking at another person to his right. Red Formula 1 racing suit with small yellow Ferrari shield emblem, red racing cap, brown western boots, arms resting naturally at his sides. Woody-like toy proportions, expressive face, chestnut hair, detailed crisp 16-bit pixel art, warm dusty western palette and strong outlines. Full body, both feet planted, true transparent alpha background, no rope, no scenery, no text or speech bubble, no additional objects. Same scale and rendering style as a polished cowboy racing platform game.

### Russell — edit using existing hero reference

Reference: `league/static/league/images/doodle-jump/western-russell-toy-hero-v3.webp`.

Use case: identity-preserve. Input image is STYLE AND CHARACTER REFERENCE: preserve exactly the existing white-and-teal cowboy racing-suit George Russell / Woody-like toy game character, cream cowboy hat, brown boots, facial features. Create a transparent three-frame horizontal intro sprite sheet of the SAME CHARACTER facing slightly right. Frame 1: standing upright naturally on both boots, arms at sides. Frame 2: both hands raised alongside and above his head as if lifting something over his cowboy hat, feet still planted. Frame 3: shallow crouch ready to jump, knees bent, hands forward. No rope or props in any frame. Full body in all three frames, same body and hat size, boots on a common baseline, one isolated pose centered per equal-width third with generous transparent gutters. Polished crisp 16-bit pixel art consistent with reference, no scenery, no text, no other characters, preserve true transparent alpha. Keep the character instantly recognizable as the existing game hero.

### Transparency cleanup — scaffold and Ferrari driver edits

Use case: background-extraction. Edit this existing game sprite: preserve the subject EXACTLY. Remove ALL background shading, all colored halos and all soft shadows around the silhouette. Background and all open gaps must be fully transparent alpha zero. Keep only the crisp pixel-art foreground subject with clean hard edges. No glow, no vignette, no backdrop, no cast shadow. Do not change composition, pose, proportions, colors or details.

## Verification

Actual game Canvas renderer checked locally at 390×740 and 600×760 logical viewport sizes, with DPR 2. Checked dialogue, lifting pose and airborne pose. Simulated natural completion, Space and touch skip, held-key repeat, one attempt per start, landing alignment, missing-art fallback and admin sandbox bypass. No connected browser was available for an end-to-end browser check.

