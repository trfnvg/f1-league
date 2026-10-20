# Summit marmot and Ferrari drone — 2026-10-20

One summit attacker at a time, alternating marmot/drone after a random initial
choice. First encounter becomes eligible 1000 world units beyond the entry
viewport. After an actor exits, the next is queued another 1500–2400 world units
above the current view. Existing shots must leave before another actor spawns.
Bath encounters and goat proximity defer spawning. Actors enter from above;
attack timers pause unless the actor is fully visible.

The marmot uses a normal existing platform, waits 0.9s, raises its yellow flag
for 1.3s, and throws one snowball sideways at 120 units/s. It remains in an open
pose until scrolled away or stomped. Resting head alpha silhouette determines
the landing surface, excluding the raised flag. Top landings bounce at 830,
award the normal 30-point enemy frag and cancel an unfired attack.

The drone drifts towards the player's horizontal position during idle, then
stops for its 1.3s blinking warning. It drops one hex nut at 130 units/s,
accelerating to a maximum 220, then retreats sideways. It can also be stomped
from above. Side contact with the actor itself is harmless; projectiles end the
run unless shielded. Projectiles use swept relative-motion collision and small
hitboxes inside their visible outlines, and are removed by shields on contact.
Actors leave by moving offscreen, not by disappearing on a visible timer.

Both four-frame sheets are normalized to a common canvas and bottom baseline,
retaining original pixels and alpha masks. They load only with the summit stage;
startup remains 12 files / 12.73 MiB. Draw calls cull offscreen art and use the
existing sprite-size cache. Staff get separate preview buttons outside the game,
with no attempt/score API writes. Restart clears actors and shots.

## Artwork

Built-in GPT image generation, not CLI. Final assets:

- `league/static/league/images/doodle-jump/summit-marmot-v1.png`
- `league/static/league/images/doodle-jump/summit-drone-v1.png`

Marmot prompt:

Use case: stylized-concept. Production game sprite sheet, premium crisp 16-bit pixel art for a mountain western Formula 1 platformer. Exactly FOUR separate equal-width cells in ONE horizontal row with large transparent gutters. Same cute stout brown alpine marmot marshal emerging from same small wooden equipment crate, orange marshal vest and dark headset. Side view facing LEFT. Four poses: 1 alert resting paws on crate rim; 2 raising a bright YELLOW warning flag; 3 throwing one white snowball with left paw extended, snowball still touching paw; 4 surprised eyes and lowered flag after being stomped. Whole crate and character entirely contained in each cell, same scale and common crate-bottom baseline. Warm brown fur, ivory muzzle, clear dark outlines, restrained orange, clean visible eyes. No text, no labels, no scenery, no floor, no ambient glow or shadows beyond silhouette. True transparent alpha background. Four complete isolated poses, not a storyboard. Keep flag connected to hand. Clean pixel clusters, no painterly blur.

Drone prompt:

Use case: stylized-concept. Production sprite sheet for premium crisp 16-bit mountain Formula 1 platformer. Exactly FOUR equal-width isolated cells in ONE horizontal row, generous transparent gutters. SAME compact red Ferrari-inspired scout quadcopter drone in each cell, three-quarter SIDE view, black carbon arms, four small rotor hubs, ivory nose stripe, tiny yellow shield badge without lettering, camera lens underneath, dark metal hex nut held in a claw below. Four animation poses: 1 cruising level with blurred pixel rotor blades; 2 hovering level, amber warning lamps lit and claw closed around nut; 3 releasing claw opened with NO nut underneath; 4 retreating tilted upward with rotors active and no nut. Same scale, all parts complete in each cell, no surrounding trails, no scenery, no text, no labels, no glow outside silhouette. Muted scarlet, charcoal and warm metal pixel clusters with strong clear outline and realistic game prop proportions, not cartoon face. Transparent alpha background.

## Verification

Native Canvas mobile/desktop suite checks lazy assets, admin preview isolation,
one-actor exclusion, offscreen warning pause, full warning before firing, single
shot, fixed warning aim, retreat/open poses, shield absorption, swept lethal
contact, stomp cancellation, natural above-screen spawn/alternation and restart.
Native screenshots inspect both warning poses in the summit scenery.
No physical-device FPS measurement is claimed.
