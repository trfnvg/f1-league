# Vegas Pit: unified helmet Sphere background

Created with the built-in `image_gen` tool, using the user's Sphere photograph
as the subject reference. Source PNGs were copied unchanged into the project.
No CLI/API generation fallback was used. The existing artwork optimizer creates
WebP delivery copies; both retain the source aspect ratio and framing.

## Saved files

- Desktop source: `league/static/league/images/vegas/strip-helmet-v2.png`.
- Desktop delivery: `league/static/league/images/vegas/strip-helmet-v2-web.webp`
  (1536 × 1024, 220,442 bytes).
- Mobile source: `league/static/league/images/vegas/strip-city-mobile-v2.png`.
- Mobile delivery: `league/static/league/images/vegas/strip-city-mobile-v2-web.webp`
  (1024 × 1536, 193,710 bytes).

The landmark, helmet, podium, architecture, road and lighting belong to each
single painted background. Only the face is animated by SVG. Its viewBox,
aspect ratio and alignment exactly match the relevant CSS background's cover
transform, anchored to the right and bottom. The small desktop Sphere now sits
at the extreme right of the city. Mobile uses a city-only painting without any
Sphere; its face SVG is hidden and animations are paused. Touch devices use
this mobile scene even in landscape orientation. No separate circular body is
painted by code. Original v1 paintings below remain historical source assets.

Regenerate delivery copies:

```sh
python scripts/optimize_vegas_art.py --only strip-helmet-v2 strip-city-mobile-v2
```

## Current desktop v2 edit prompt (verbatim)

Input: `league/static/league/images/vegas/strip-helmet-v1.png`.

```text
Use case: precise-object-edit. Edit the supplied 1536x1024 Las Vegas game background. Keep the same landscape dimensions and camera, painted style, violet night sky, Eiffel tower on the left, hotel positions, circuit barriers and reflective amber road. Change ONLY the size and placement of the helmet-wearing yellow Sphere building and rebuild the architecture where the old large Sphere stood. The Sphere is now a SMALL DISTANT architectural landmark at the EXTREME RIGHT EDGE, about HALF its previous diameter. Target circular shell bounds roughly x=1250 to 1520 and y=410 to 680 on the 1536x1024 image, diameter about 270px, with the entire circular shell visible and supported by a modest podium among the right-side buildings. It should occupy the last 18 percent of the image width so a large central slot cabinet won't cover it. Preserve the SAME cyan/blue/purple racing helmet, white 'LAS VEGAS GRAND PRIX' helmet band, small red racing emblem and yellow face opening. The face must remain entirely BLANK YELLOW, no eyes, no eyebrows and no mouth, because the code will animate them. Retain natural shared illumination, LED texture, physical base, architectural scale and perspective. Do not paste an independent emoji sticker or a second globe. Preserve the rest of the city, race track and dark central negative space. Exactly one small Sphere at the far right, no UI, no watermarks.
```

## Current mobile v2 edit prompt (verbatim)

Input: `league/static/league/images/vegas/strip-helmet-mobile-v1.png`.

```text
Use case: precise-object-edit. Edit the supplied 1024x1536 PORTRAIT Las Vegas game background. REMOVE the entire helmet-wearing yellow Sphere and its isolated upper-right podium/rooftop cluster. Replace that upper-right area with continuous dark violet night sky matching the surrounding clouds. There must be NO Sphere building anywhere in this mobile image, no yellow face, no eyes, no helmet, no circular glowing building and no floating architecture. Preserve the portrait size, camera, richly illustrated style, warm-lit Eiffel tower and hotels on the left, grounded lower skyline on the right, the dark central space for game reels, circuit barriers, wet amber road and violet/gold lighting. Only remove that upper-right landmark and seamlessly reconstruct the sky; keep all other parts and framing unchanged. Full-bleed cohesive night city background, no UI, no extra objects, no watermark.
```

## Initial desktop v1 prompt (verbatim)

```text
Use case: stylized-concept. Asset type: full-bleed unified background plate for an existing Formula racing Las Vegas slot game, landscape 3:2, approximately 1536 by 1024. Reference image: the user's photograph is a SUBJECT reference for the real Las Vegas Sphere displaying a yellow emoji wearing a blue/purple racing helmet. Create a complete beautifully rendered cohesive nighttime Las Vegas racing scene, not a game UI mockup. Las Vegas Strip architecture and warm-lit hotels frame the edges, modest illuminated Eiffel tower at far left, dark violet night sky, amber street reflections and race circuit barriers along bottom. Keep the central 55 percent calm and relatively dark for an existing slot cabinet to be overlaid by code. On the RIGHT side integrate exactly one enormous real architectural SPHERE building into the skyline: its circular LED shell occupies roughly x=74 to 99 percent of the image and y=32 to 70 percent. It must be supported by its real low circular podium, perspective and scale continuous with the surrounding buildings. The shell displays the yellow emoji wearing a glossy BLUE/CYAN/VIOLET FORMULA RACING HELMET matching the reference, with white helmet brow band carrying exact legible words 'LAS VEGAS GRAND PRIX' and a small red abstract racing emblem. Crucial production animation requirement: inside the lower yellow face opening below the helmet band, leave the skin SMOOTH AND BLANK with NO eyes, NO eyebrows, NO mouth; those will be animated by code after generation. The helmet opening is a broad clear warm-yellow rounded facial area with enough uninterrupted space for two large eyes and a small mouth. The Sphere must be part of this one painted scene, with LED texture, atmospheric falloff, yellow light reflecting on nearby structures, grounded architecture, never a floating emoji or separate sticker. Style: polished detailed illustrated online casino background with believable architecture, controlled cinematic lighting and warm gold/violet palette, refined and crisp rather than toy 3D or flat vector. Preserve recognizable racing helmet proportions from the reference. Avoid additional spheres, separate characters, slot reels, controls, UI, floating objects, sparkles, signs except the helmet band, watermarks. Landscape full-bleed opaque background only.
```

## Initial mobile v1 prompt (verbatim)

Input: `league/static/league/images/vegas/strip-helmet-v1.png`.

```text
Use case: precise-object-edit. Asset type: matching PORTRAIT mobile background plate, 2:3 portrait approximately 1024 by 1536. Adapt the supplied unified Las Vegas night race background for a mobile slot game. Preserve its richly rendered violet nighttime sky, gold-lit hotels, race circuit fencing and wet amber road, and the SAME helmet-wearing yellow LED Sphere building with exact same design. Recompose rather than stretch or merely crop. Put the ONE Sphere SMALL in the FAR UPPER RIGHT of the portrait skyline: the circular shell should occupy approximately x=68% to 98% of the canvas, y=0% to 19%; part of the top can run out of frame. The helmet should be cyan/blue/violet with the white band 'LAS VEGAS GRAND PRIX', and the lower face must remain SMOOTH BLANK YELLOW with NO eyes, NO eyebrows and NO mouth, because code will animate these. Its rounded building body MUST connect naturally to the rooftops through a low structural podium. The clear blank yellow face center should be near x=83%, y=14% of the portrait. Keep center and middle 70 percent subdued dark violet for overlaid slot reels. Dense elegant warm-lit Las Vegas architecture can stand along the outer edges, subtle Eiffel tower on left, circuit barriers toward lower half, wet reflective road across bottom 20 percent. Single continuous atmospheric scene, premium detailed casino background painting with perspective and shared environmental lighting, no floating separate emoji, no collage, no slot machine, no UI, no extra spheres, no watermarks. Retain all these visual invariants; change ONLY framing and architectural composition to portrait mobile.
```
