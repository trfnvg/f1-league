# Space F1 encounters

## Runtime behaviour

Only one encounter runs at a time in the fully transitioned space chapter.
The first begins after seven seconds, followed by 8–13-second gaps. The event
roster cycles through all four types, so each can be encountered during a run.
An event lasts at most eleven seconds. Standard enemies and falling hazards
pause during it. Toto cancels the event and restores any borrowed platform;
no events can start during his fight. Real platform generation is unchanged.

- Carbon shower: 1.5-second dashed trajectory warning, three fragments in four
  lanes with one lane left clear. Two broad carbon pieces support a top bounce
  (850 upward velocity); small shards and side collisions are lethal without
  invulnerability. Collision uses alpha silhouettes and swept vertical motion.
- Ferrari satellite: "WE ARE CHECKING" changes to "STAY OUT!". Three additional
  low-opacity, visibly flickering, HOLOGRAM-labelled platforms have no collision.
  They never remove or replace the real, reachable platform route.
- Lunar pit-stop: temporarily borrows a reachable real landing surface and
  renders the service deck at exactly that contact plane. The landing triggers
  a 0.75-second protected service animation with mechanics at the hero's boots.
  Launch plus the next two platform jumps are enhanced (930 upward velocity).
  The bonus cannot be refilled by repeatedly landing on the same deck. Remaining
  jumps survive the portal, but a new run resets them. The original platform is
  restored on expiry, portal entry or Toto arrival.
- Alonso: slowly crosses horizontally, with four engine/cough frames and
  "GP2 ENGINE!". Its silhouette supports one strong bounce (1080 upward velocity)
  with brief protection. Repeated landings give ordinary bounces, preventing
  unlimited super-jump chaining. The craft faces the direction of travel.

Four staff-only preview buttons above the game start isolated space sessions
without submitting attempts or scores. They load space artwork on demand;
Antarctica images are not required. Original image resolution is retained.

## Generated assets and provenance

Generated using the built-in GPT image generation tool with transparent alpha.
No replacement of existing artwork. Sprite gutters were inspected before
choosing frame boundaries; the carbon strip uses uneven cuts. Service-deck
alignment uses the original sheet's row 356 so mechanic poses do not move the
contact surface. Assets below are relative to the repository:

- `league/static/league/images/doodle-jump/space-carbon-v1.png`
- `league/static/league/images/doodle-jump/space-satellite-v1.png`
- `league/static/league/images/doodle-jump/space-pitstop-v1.png`
- `league/static/league/images/doodle-jump/space-alonso-v1.png`

## Exact generation prompts

### carbon

Use case: stylized-concept. Asset type: transparent 2D retro game sprite strip for a Formula 1 pixel-art platform jumper, space chapter. Subject: A production sprite strip of FOUR separate Formula 1 carbon-fibre space debris objects, left to right: a large broad battered carbon rear-wing section with a silver top edge that is clearly a landing surface; another large broad broken nose-cone chunk with silver top edge; a small sharp triangular carbon shard; a small jagged metallic-carbon fragment. No characters. Black graphite woven carbon with restrained dull silver and tiny red accents. Large objects must read as solid wide platforms; small objects read as dangerous jagged shards. Exactly four isolated objects. Style: premium detailed 16-bit SNES pixel art, deliberate crisp pixel clusters, dark navy outlines, restrained desaturated colours, matching a retro cowboy racer game. Composition: FOUR separate equally spaced cells in ONE horizontal ROW, identical baseline and scale, generous transparent gutters between cells. Every entire object fits in its own cell, no touching other cells. Fully TRANSPARENT alpha background, no background scene, no stars outside objects, no labels, no text, no grid, no watermark. Wide landscape strip. Designed to be readable at 70–150px wide in the game.

### satellite

Use case: stylized-concept. Asset type: transparent 2D retro game sprite strip for a Formula 1 pixel-art platform jumper, space chapter. Subject: FOUR animation poses of the same derelict Ferrari Formula 1 pit-wall satellite in space: red battered pit-wall console with two short solar panels, radio antenna and a large blank dark rectangular display. Poses: neutral blue display, warning with amber blinking lights and satellite pointing a small directional antenna, red glitching display with little pixel sparks, powered-down neutral. Same silhouette and scale in each cell. No people. Style: premium detailed 16-bit SNES pixel art, deliberate crisp pixel clusters, dark navy outlines, restrained desaturated colours, matching a retro cowboy racer game. Composition: FOUR separate equally spaced cells in ONE horizontal ROW, identical baseline and scale, generous transparent gutters between cells. Every entire object fits in its own cell, no touching other cells. Fully TRANSPARENT alpha background, no background scene, no stars outside objects, no labels, no text, no grid, no watermark. Wide landscape strip. Designed to be readable at 70–150px wide in the game.

### pitstop

Use case: stylized-concept. Asset type: transparent 2D retro game sprite strip for a Formula 1 pixel-art platform jumper, space chapter. Subject: FOUR animation poses of the same lunar Formula 1 pit-stop platform: broad flat steel platform with a clearly horizontal upper landing edge, TWO tiny funny pit mechanics in white space suits with round helmet visors, red boots and a single red soft-compound tyre tool. Keep the CENTER of the platform EMPTY for the game hero. Poses: mechanics waiting at sides, mechanics lean into EMPTY central work position with tools, mechanics using impact wrenches at boot height beside EMPTY center, mechanics cheering at sides with EMPTY center. No driver or hero on the platform. Same platform dimensions in all cells. Style: premium detailed 16-bit SNES pixel art, deliberate crisp pixel clusters, dark navy outlines, restrained desaturated colours, matching a retro cowboy racer game. Composition: FOUR separate equally spaced cells in ONE horizontal ROW, identical baseline and scale, generous transparent gutters between cells. Every entire object fits in its own cell, no touching other cells. Fully TRANSPARENT alpha background, no background scene, no stars outside objects, no labels, no text, no grid, no watermark. Wide landscape strip. Designed to be readable at 70–150px wide in the game.

### alonso

Use case: stylized-concept. Asset type: transparent 2D retro game sprite strip for a Formula 1 pixel-art platform jumper, space chapter. Subject: FOUR animation poses of the same small comical battered Formula 1 space shuttle, side view nose pointing RIGHT, Fernando Alonso visible through a large canopy with expressive adult face, brown hair and stubble, blue-orange racing suit. Stubby white/orange/navy old spacecraft, short flat horizontal upper canopy edge useful as a game landing surface, engines at LEFT. Poses: engine on, engine sputtering with tiny grey smoke puff, Alonso complaining with open mouth and warning light, engine cough with a slightly larger grey smoke puff. Keep smoke small and INSIDE its own cell. Same craft body size and location in all four cells, no extra detached objects. Style: premium detailed 16-bit SNES pixel art, deliberate crisp pixel clusters, dark navy outlines, restrained desaturated colours, matching a retro cowboy racer game. Composition: FOUR separate equally spaced cells in ONE horizontal ROW, identical baseline and scale, generous transparent gutters between cells. Every entire object fits in its own cell, no touching other cells. Fully TRANSPARENT alpha background, no background scene, no stars outside objects, no labels, no text, no grid, no watermark. Wide landscape strip. Designed to be readable at 70–150px wide in the game.


## Verification

`tests/doodle_streaming.mjs` checks all four cold/admin previews, natural spawning,
one-event limit, safe shower lane, carbon collisions and shield, preserved real
platform path, exactly three boosted jumps, one-time shuttle boost, Toto/portal
cleanup, restart and the unchanged 12-image startup request set. Native Canvas
renders mobile/desktop previews; actual Safari/Chrome device FPS is not measured.

