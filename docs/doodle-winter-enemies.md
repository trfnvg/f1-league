# Winter F1 encounters

## Gameplay

- Iceman (Kimi Raikkonen): floating refrigerator, ice cream, "LEAVE ME ALONE".
  A horizontal wind gust follows a 1.6-second warning. Wind pushes the hero
  briefly, rather than killing them. Bounce on Kimi from above to defeat him.
- FIA steward: a snowman with a cone nose. Throws a slow "+5 SEC" penalty board
  after a warning. Board contact is lethal without a shield (the label is a
  visual joke, not an actual time penalty). After throwing, a 2.4-second opening
  allows a stomp. Outside that opening his body is dangerous.

One encounter at a time; piranha spawning pauses during encounters/projectiles.
First encounter: eight seconds after winter gameplay begins. Subsequent encounters
have 12–20-second cooldowns. Types rotate with a random first type. Stomps give
+30 points, a bounce and brief protection; remaining projectiles are cleared.
Enemies are queued entirely above the viewport and above existing piranhas.
They remain at a fixed world height so the player reaches them by climbing.
Attack timers begin only once the full body and caption are on screen; no
offscreen attacks or fifteen-second expiry. Existing piranhas are not erased
when a new encounter is queued. Defeated mobs fall visibly out of the screen;
all encounters retire only once the full sprite/caption has passed below it.
Rocket protection applies normally. The Russell memory portrait uses 55%
opacity (formerly 23%); its text has no background panel.
Restart/biome entry clears all encounter, projectile, wind and slide state.
Admin buttons above the playfield open isolated previews without score writes.

## Art provenance

Generated with the built-in GPT image generation tool, with transparent alpha.
Original resolution retained. Frames are cut at verified transparent gutters;
collision bodies exclude the ice gust, raised boards and decorative limbs.

Saved assets (relative to the repository):

- `league/static/league/images/doodle-jump/winter-iceman-v1.png`
- `league/static/league/images/doodle-jump/winter-steward-v1.png`

## Exact generation prompts

### iceman

Use case: stylized-concept. Asset type: production-ready transparent 2D retro game sprite animation strip for an icy Formula 1 platform jumper. Subject: Kimi Raikkonen, recognisable blond Finnish racing driver with short blond hair and deadpan expression, white-and-icy-blue racing suit, seated on a small floating frost-covered refrigerator on a cloud, holding an ice cream cone. Four poses: resting seated, annoyed warning (fridge door glows cyan), attacking releasing wind with free hand, startled crouching after being bounced on. His face must be adult and recognisable, not Woody. Style: polished detailed 16-bit SNES pixel art, crisp deliberate pixel clusters, dark navy 1-2 pixel contours, restrained cold winter palette with specified outfit accents, clean readable at 70-95px tall. Composition: exactly FOUR equally sized cells in ONE horizontal ROW, each contains ONE entire isolated character including its prop; generous fully transparent gutters between cells, same scale and feet baseline, no overlap, transparent background, no scenery, no floor, no labels, no text, no grid, no borders, no watermark. Desired wide landscape animation strip. Four distinct animation poses arranged left-to-right; do not duplicate subjects within a cell. Do not add any separate floating effects that touch another cell.

### steward

Use case: stylized-concept. Asset type: production-ready transparent 2D retro game sprite animation strip for an icy Formula 1 platform jumper. Subject: FIA snowman race steward made of three snowballs with small orange traffic-cone nose, dark navy marshal cap and checkered scarf; holding a small blank penalty board. Four poses: idle with cone nose, winding up a throw, arm extended after throwing with cone nose popping off, vulnerable surprised pose without cone nose and cap tilted. Same three-snowball body proportions in every pose. Style: polished detailed 16-bit SNES pixel art, crisp deliberate pixel clusters, dark navy 1-2 pixel contours, restrained cold winter palette with specified outfit accents, clean readable at 70-95px tall. Composition: exactly FOUR equally sized cells in ONE horizontal ROW, each contains ONE entire isolated character including its prop; generous fully transparent gutters between cells, same scale and feet baseline, no overlap, transparent background, no scenery, no floor, no labels, no text, no grid, no borders, no watermark. Desired wide landscape animation strip. Four distinct animation poses arranged left-to-right; do not duplicate subjects within a cell. Do not add any separate floating effects that touch another cell.
