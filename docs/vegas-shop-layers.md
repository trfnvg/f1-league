# Independent casino shop layers

Created using the built-in image generator, without CLI/API fallback or raster editing. Copied unchanged into the project:

- `league/static/league/images/vegas/shop-room-v2.png`: opaque empty room, no counter baked in.
- `league/static/league/images/vegas/shop-counter-v2.png`: separate 2172×724 transparent foreground counter, rendered at its original 3:1 aspect ratio, cropped horizontally on narrow screens.
- `league/static/league/images/vegas/shop-simply-poses-v3.png`: 1536×1024 six-frame character atlas based on the user-provided photograph. Idle, blink, preparation, release, catch, greeting. No glasses; short hair and beard match the reference.

Room z0, goods z3, character z4, counter z5. The counter is an actual transparent image, not a duplicate room clipped at a straight edge. Its rear edge (22% down the asset) and the character share `--counter-edge`. The bottom of the vest extends behind the opaque table. Greeting uses the registered pose only: no rotation of the entire body/waist. Other animation lifecycle safeguards remain unchanged.

The scene uses `overflow: clip`, not `hidden`: the wider mobile counter must not create a scroll container that pans horizontally when focus returns from a product dialog.

## Prompts

### Room

```text
Use case: precise-object-edit. Edit target: supplied casino shop interior. REMOVE the entire green-felt wooden counter in the foreground. Reconstruct the burgundy velvet back wall and dark walnut lower wall panels naturally behind where the counter was; retain the small dark marble floor strip at the very bottom. Preserve EXACTLY the architecture, framing, camera, lighting, wall texture, gold art-deco sconces, red neon top arch and all original colors. This must be an EMPTY interior background plate with NO counter, NO furniture, NO people, NO items, no lettering. The separate counter and animated dealer will be composited by code. Landscape 3:2 composition, full bleed opaque background. Do not change the upper 65% of the supplied image.
```

### Counter

```text
Use case: background-extraction. Asset: standalone foreground counter sprite for the casino shop in reference. Draw ONLY the curved dark walnut croupier counter, polished brass edging and emerald green felt tabletop. No wall, no room, no person, no chips, no objects, no text, no atmospheric background. TRUE TRANSPARENT ALPHA around the entire isolated counter. Preserve the perspective and painted warm materials of reference. Wide landscape canvas roughly 3:1 (1536x512 ideal); counter fills 96% canvas width and 92% canvas height, with minimal 3% transparent padding above and below. Viewed straight-on with the shallow green tabletop visible, upper REAR edge of tabletop nearly horizontal across center, gently rounded ends; front wooden panel vertical and solid opaque, sophisticated restrained gold trim. The rear tabletop silhouette must be clean and sharp so that it naturally OCCLUDES an independently drawn dealer's lower torso behind it. No people or body parts baked into texture. No floor shadow outside silhouette. This is an independent game foreground object, NOT a full scene.
```

### Simply

```text
Use case: identity-preserve. The attached PHOTO of the man in a green polo is the FACE IDENTITY reference. Create an animated casino shop croupier sprite atlas with this exact man's recognizable features: short straight dark brown side-parted hair, broad natural face, straight eyebrows, specific nose and mouth, short dark beard concentrated around jaw and chin with trimmed moustache, NO GLASSES. Do not use the earlier round bespectacled cartoon identity. Keep proportions human and likeness close to photo, not chubby caricature. He wears a burgundy gold-trim casino waistcoat, white shirt, black bowtie and small round gold medal. Polished detailed painted game illustration, warm lighting, opaque character clean alpha cutouts. ONE landscape atlas EXACTLY THREE columns and TWO rows, six equal SQUARE cells, overall 3:2. Identical camera, scale, alignment and body in every cell. Each waist-up character centered, head at 8% cell height, lower vest ends at 98%, hands and fingers all above 86%. No background, no room, no counter, no atmosphere, no text. RIGHT hand on viewer right palm up at x85% y60%, no chip drawn (chip animated separately); LEFT hand rests across upper abdomen at y76%. Exactly TWO arms per person. Frame order: TOP LEFT idle slight friendly smile eyes open; TOP MIDDLE identical idle but eyes closed blinking; TOP RIGHT right fingers curl preparing a chip toss, body unchanged; BOTTOM LEFT right wrist flick upward and eyes glance up toward imaginary chip, body unchanged; BOTTOM MIDDLE palm up catching and eyes glance toward hand, body unchanged; BOTTOM RIGHT left arm raised into small welcoming wave beside shoulder instead of resting on abdomen, right palm remains up; NO THIRD HAND on abdomen in this last frame. All six must look like the supplied photo, consistent hair and beard, no glasses, no oversized head. Hands completely above bottom 14% which contains only waistcoat and will be masked by a separate foreground counter. All six cells perfectly registered, generous transparent margins between characters, no glows or floor shadows. True transparent alpha background.
```

