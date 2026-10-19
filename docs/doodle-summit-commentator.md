# Summit commentator bath encounter — 2026-10-19

Only the high-altitude paddock spawns this encounter. The first bath is queued
above the viewport; later baths are separated by 2400–3300 world units and only
one can exist at a time. Before contact its speech is exactly:

> Я САМЫЙ ЛУЧШИЙ КОММЕНТАТОР ФОРМУЛЫ 1!

Descending feet landing on the alpha silhouette give Russell an 810 upward
velocity, change the bath pose, and display `БАН БАН БАН`. After 0.8 seconds the
bath tilts and falls under gravity with foam bubbles. Side contacts and upward
passes do not trigger it. The support platform remains usable, and repeated
contact during the shout/fall cannot award additional bounces. The encounter
has no score bonus, voice audio or effect on the arcade winner rules.

Four full-resolution poses are loaded atomically with the summit stage, never
at game startup. Contour cleanup removes detached neighboring pixels. The
admin-only `Высокогорье · комментатор в ванне` button enters a sandbox preview;
attempts/results are not submitted. Restart clears the encounter.

## Artwork

Built-in GPT image generation (not CLI). Asset:
`league/static/league/images/doodle-jump/summit-commentator-v1.png`.
The source remains at:
`/Users/trfnvg/.codex/generated_images/019fb2d9-8385-7692-969b-f71381a8f6e5/exec-b11f9304-7994-4e75-89f7-6e384be77f19.png`.

Reference: the previously approved six-panel bath storyboard
`exec-86adaddf-c59f-45b1-b33a-731be80790b1.png`.

Generation prompt:

Use case: stylized-concept. Create a production-ready transparent sprite sheet for a retro 16-bit platformer, using the supplied storyboard as exact character and bathtub identity reference. Exactly FOUR frames in ONE horizontal row, four equally sized cells. Each cell contains the SAME entire ivory enamel bathtub with brass claw feet, white dense bubble foam, and the SAME adult stocky man: broad round light-skinned face, short dark brown side-part hair, rectangular thin-frame glasses, gold medal on red neck ribbon visible over foam. Preserve recognizable face in reference. NONSEXUAL cartoon comedy; opaque tub and dense foam completely conceal body below shoulders. Crisp premium 16-bit pixel clusters and dark clean outline, no smooth painterly textures. Frame1 relaxed reclining and smiling slightly, eyes open. Frame2 boasting, mouth open and one finger raised, medal visible. Frame3 shouting BAN in anger, wide open mouth, one hand lifted. Frame4 startled falling reaction, eyes wide, clutches tub rim, a few foam bubbles directly above tub. Keep tub SAME SIZE, horizontal level, identical x/y alignment and common foot baseline across all frames; rotation and falling movement will be handled by game code. All four complete bathtub silhouettes fully contained in their own cells with ample transparent gutters, no overlap, no cut-off feet or head. Every cell tightly designed but with 10% transparent padding. No text or speech bubbles: game will add Russian phrases. NO scenery, mountains, floor, platform, labels, numbers or decorative frames. Real alpha transparent background, no checkerboard drawing or solid fill. The original storyboard is only an identity/style reference; output must be four isolated game sprite frames, not scenes.

## Verification

Native Canvas tests cover mobile/desktop previews, staged loading, exact top
contact, upward/side near misses, bounce, shout/fall sequence, cleanup, restart
and admin API isolation. Native Canvas screenshots verify both phrases and
the actor's visual alignment. These checks are not device FPS measurements.
