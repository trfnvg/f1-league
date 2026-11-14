# Vegas Pit: unified helmet Sphere background

Created with the built-in `image_gen` tool, using the user's Sphere photograph
as the subject reference. Source PNGs were copied unchanged into the project.
No CLI/API generation fallback was used. The existing artwork optimizer creates
WebP delivery copies; both retain the source aspect ratio and framing.

## Saved files

- Desktop source: `league/static/league/images/vegas/strip-helmet-v1.png`.
- Desktop delivery: `league/static/league/images/vegas/strip-helmet-v1-web.webp`
  (1536 × 1024, 242,930 bytes).
- Mobile source: `league/static/league/images/vegas/strip-helmet-mobile-v1.png`.
- Mobile delivery: `league/static/league/images/vegas/strip-helmet-mobile-v1-web.webp`
  (1024 × 1536, 233,754 bytes).

The landmark, helmet, podium, architecture, road and lighting belong to each
single painted background. Only the face is animated by SVG. Its viewBox,
aspect ratio and alignment exactly match the relevant CSS background's cover
transform. Both layouts reuse `vegas_sphere_face.html`; they do not independently
position another Sphere or paint a separate circular body. Existing visibility
and reduced-motion handling pauses eye animations.

Regenerate delivery copies:

```sh
python scripts/optimize_vegas_art.py --only strip-helmet-v1 strip-helmet-mobile-v1
```

## Desktop prompt (verbatim)

```text
Use case: stylized-concept. Asset type: full-bleed unified background plate for an existing Formula racing Las Vegas slot game, landscape 3:2, approximately 1536 by 1024. Reference image: the user's photograph is a SUBJECT reference for the real Las Vegas Sphere displaying a yellow emoji wearing a blue/purple racing helmet. Create a complete beautifully rendered cohesive nighttime Las Vegas racing scene, not a game UI mockup. Las Vegas Strip architecture and warm-lit hotels frame the edges, modest illuminated Eiffel tower at far left, dark violet night sky, amber street reflections and race circuit barriers along bottom. Keep the central 55 percent calm and relatively dark for an existing slot cabinet to be overlaid by code. On the RIGHT side integrate exactly one enormous real architectural SPHERE building into the skyline: its circular LED shell occupies roughly x=74 to 99 percent of the image and y=32 to 70 percent. It must be supported by its real low circular podium, perspective and scale continuous with the surrounding buildings. The shell displays the yellow emoji wearing a glossy BLUE/CYAN/VIOLET FORMULA RACING HELMET matching the reference, with white helmet brow band carrying exact legible words 'LAS VEGAS GRAND PRIX' and a small red abstract racing emblem. Crucial production animation requirement: inside the lower yellow face opening below the helmet band, leave the skin SMOOTH AND BLANK with NO eyes, NO eyebrows, NO mouth; those will be animated by code after generation. The helmet opening is a broad clear warm-yellow rounded facial area with enough uninterrupted space for two large eyes and a small mouth. The Sphere must be part of this one painted scene, with LED texture, atmospheric falloff, yellow light reflecting on nearby structures, grounded architecture, never a floating emoji or separate sticker. Style: polished detailed illustrated online casino background with believable architecture, controlled cinematic lighting and warm gold/violet palette, refined and crisp rather than toy 3D or flat vector. Preserve recognizable racing helmet proportions from the reference. Avoid additional spheres, separate characters, slot reels, controls, UI, floating objects, sparkles, signs except the helmet band, watermarks. Landscape full-bleed opaque background only.
```

## Mobile prompt (verbatim)

Input: the desktop source PNG above.

```text
Use case: precise-object-edit. Asset type: matching PORTRAIT mobile background plate, 2:3 portrait approximately 1024 by 1536. Adapt the supplied unified Las Vegas night race background for a mobile slot game. Preserve its richly rendered violet nighttime sky, gold-lit hotels, race circuit fencing and wet amber road, and the SAME helmet-wearing yellow LED Sphere building with exact same design. Recompose rather than stretch or merely crop. Put the ONE Sphere SMALL in the FAR UPPER RIGHT of the portrait skyline: the circular shell should occupy approximately x=68% to 98% of the canvas, y=0% to 19%; part of the top can run out of frame. The helmet should be cyan/blue/violet with the white band 'LAS VEGAS GRAND PRIX', and the lower face must remain SMOOTH BLANK YELLOW with NO eyes, NO eyebrows and NO mouth, because code will animate these. Its rounded building body MUST connect naturally to the rooftops through a low structural podium. The clear blank yellow face center should be near x=83%, y=14% of the portrait. Keep center and middle 70 percent subdued dark violet for overlaid slot reels. Dense elegant warm-lit Las Vegas architecture can stand along the outer edges, subtle Eiffel tower on left, circuit barriers toward lower half, wet reflective road across bottom 20 percent. Single continuous atmospheric scene, premium detailed casino background painting with perspective and shared environmental lighting, no floating separate emoji, no collage, no slot machine, no UI, no extra spheres, no watermarks. Retain all these visual invariants; change ONLY framing and architectural composition to portrait mobile.
```
