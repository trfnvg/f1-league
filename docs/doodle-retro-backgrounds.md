# Retro background refresh

Generated with the built-in GPT image tool (imagegen), editing the existing backgrounds with the unchanged cowboy hero sheet as style reference. Original assets retained. New PNGs preserve generated resolution and cloud alpha. Camera/scroll logic unchanged.

Assets in `league/static/league/images/doodle-jump/`:

- `western-ascent-retro-v4.png`
- `western-space-retro-v3.png`
- `forgotten-paddock-retro-v2.png`
- `antarctica-canyon-retro-v2.png`
- `summit-paddock-retro-v2.png`
- `western-cloud-retro-v4.png`

## Shared prompt

Use case: style-transfer. Edit image 1, an existing scrolling game background. Image 2 is ONLY the playable cowboy racer sprite style reference, DO NOT draw him or any characters into the background. Preserve the existing scene, landmark positions, framing, biome and color identity closely. Redraw beautifully as cohesive premium 16-bit pixel art matching the character: deliberate crisp pixel clusters, simplified readable shapes, restrained color ramps, clean stepped edges, subtle selective dithering. No photorealism, painterly microtexture, blur, grain, bloom, text, UI, platforms or new objects. Keep the central gameplay corridor quieter and lower contrast than the edges. Output ONLY the complete background asset, no mockup or border. 

## Scene prompts

### journey

Edit target: `western-ascent-v3.webp`

Preserve the very tall 1:3 composition: paddock at bottom, orange canyon walls along sides through middle, open blue sky above. Match the same proportions and landmark heights; no rearrangement. Output 724x2172 or same 1:3 aspect ratio.

### space

Edit target: `western-space-v2.jpg`

Preserve portrait starfield: nearly black navy with subdued violet nebula filaments, sparse small warm-white pixel stars. Keep outer top and bottom dark and quiet for looping, no bright edge borders. No planets (these are rendered separately). Same aspect ratio.

### garage

Edit target: `forgotten-paddock-v1.jpg`

Preserve vertical abandoned orbital paddock: narrow garage structures at both sides, dim turquoise and amber lamps, racing equipment along edges, broad nearly empty dark starfield centre. Simplify photographic surfaces into clean readable pixel clusters. Top/bottom must be visually compatible for repeating vertical scroll; no floor or ceiling. Same portrait aspect ratio.

### winter

Edit target: `antarctica-canyon-v1.png`

Preserve blue icy cliffs at left/right, pale lilac distant mountains and misty centre. Clean sculpted stepped ice clusters, restrained blue-violet shadows, ivory snow. Same 2:3 portrait framing. Top and bottom edges should visually blend for vertical scrolling, no border.

### summit

Edit target: `summit-paddock-v1.png`

Preserve upper blue sky, snowy mountain valley, small racing garages at lower left/right and cable cars. Same 2:3 portrait framing, same horizon and landmarks. Simplify excessive snow detail to broad elegant pixel clusters, slightly muted blue sky matching canyon sky.

### Cloud

Edit target western-cloud-v3.webp, cowboy hero style reference only. Redraw a single wide cloud in clean 16-bit pixel art, ivory highlights, muted powder-blue shadows, restrained five-color ramps, stepped edges, no neon cyan fringe, no blur or noise. Preserve 3:1 silhouette and transparent background, no extra objects.

