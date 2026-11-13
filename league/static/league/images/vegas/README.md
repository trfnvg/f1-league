# Vegas Pit — visual assets

## Casino shop artwork (built-in image generation)

Three original assets are copied unchanged into this directory:
`shop-interior-v1.png` (opaque interior), `shop-croupier-v1.png`
(transparent Bath Judge in croupier attire), `shop-goods-v1.png`
(transparent 3×2 merchandise atlas; bottom-right cell empty).
The source Bath Judge sprite is the identity reference for the croupier.
Prices, labels, shelves and interactions are rendered in HTML/CSS.

### Interior prompt (verbatim)

```text
Use case: stylized-concept. Asset type: background plate for an interactive Formula racing casino shop game. Elegant illustrated 2D Las Vegas boutique interior, frontal almost orthographic view, landscape 3:2. Dark aubergine velvet back wall, walnut and antique brass wall panels, two tasteful warm brass wall sconces at extreme upper sides, subtle red neon accent. A quiet EMPTY wall in central 85 percent: interactive shelves and product icons will be added by code, so NO painted shelves, no merchandise or cabinets across center. Lower 18 percent a grand gently curved dark walnut sales counter with emerald velvet top and thin gold trim, facing the viewer. Warm theatrical light, rich but restrained jewel tones, crisp architectural perspective, premium hand-painted casino adventure game background. Central wall calm and moderately illuminated to make goods readable. No people, no products, no letters or text, no logos or signage, no UI panels, no watermarks. Full bleed opaque landscape illustration.
```

### Croupier prompt (verbatim)

```text
Use case: stylized-concept. Production transparent character cutout for a premium illustrated F1 meme casino shop. Supporting reference image depicts the Bath Judge; preserve his identity: stout cheerful man, short side-parted brown hair, round fleshy face, rectangular black glasses, confident knowing smile, gold medal. Repaint in crisp detailed hand-painted 2D casino adventure game art, NOT pixel art. Dress him as a casino CROUPIER: white long sleeve shirt, dark burgundy tailored waistcoat with small brass buttons, black bow tie, gold medal on a small red ribbon beneath bow tie. Framing waist-up, face turned toward viewer, one hand palm up presenting merchandise, other hand elegantly holding two small casino chips. Entire figure fully within canvas, modest transparent padding, recognizable broad round cheeks and distinctive spectacles. No bathtub, bubbles or other characters. Genuine transparent alpha background. Warm amber highlights and subtle purple rimlight, warm natural skin, detailed face, expressive humorous personality, tasteful rich velvet fabrics, polished professional game illustration not toy 3D. No text, official logos, podium, table or environment. Portrait 2:3 composition, character cutout only.
```

### Merchandise prompt (verbatim)

```text
Use case: stylized-concept. Asset type: one production game merchandise sprite atlas for a premium F1 meme casino shop. Square canvas with exactly SIX equal invisible square cells in a precise 3 columns by 2 rows grid. The last bottom-right cell must be completely EMPTY transparent. Five isolated item icons centered in the other five cells with generous 15 percent padding on every side. Genuine transparent alpha background. Same rich crisp hand-painted 2D commercial casino game art: polished metal, emerald and ruby jewel accents, warm gold rim highlights, readable strong silhouettes, no cartoon faces. TOP LEFT an emerald racing SHIELD with polished gold rim and a small racing helmet embossed at center. TOP CENTER an ivory parchment amnesty scroll with red broken wax seal and gold laurel, NO writing. TOP RIGHT a modern black Formula racing steering wheel smeared with a small comical patch of brown mud, red buttons, golden rimlight, recognizable steering wheel. BOTTOM LEFT a compact polished chrome pneumatic pit-stop wheel gun with bright red handle and two small gold stars. BOTTOM CENTER a lacquered burgundy casino chip chest open to reveal gold coins and one small green curved return arrow medallion in front. BOTTOM RIGHT empty. All same apparent scale, fully visible, consistent straight-on perspective. No shelves or environment, no panels or grid lines, no letters, words or numbers, no labels, prices, floor shadows, watermarks or logos. Exactly five items, no duplicates. Final game atlas, not a concept sheet.
```

## Pepper Russell override

`pepper-russell-v1.png` replaces the ice-cream portrait (internal key `toto`).
Generated using the built-in image tool, copied unchanged with transparency.
The remaining eight symbols still use the v4 atlas. Winning pepper lines
trigger bounded fire FX and a short portrait glow; payouts are unchanged.

Prompt (verbatim):

```text
Use case: stylized-concept. A single premium hand-painted 2D casino SLOT SYMBOL on genuine transparent alpha background, square canvas. George Russell from Formula One as a bright red chili pepper meme. CRITICAL: large instantly recognizable portrait of the real GEORGE RUSSELL, young clean-shaven British man, characteristic long narrow face, angular jaw, prominent ears, straight nose, blue eyes, thick swept-up dark brown hair, cheeky confident smile. Accurate individual facial likeness, realistic portrait anatomy and painted skin texture, not a generic driver, not Sebastian Vettel, not Kimi Raikkonen. His large face emerges from a glossy curved red chili pepper costume with green stem/collar, compact silhouette; face occupies upper half of icon, red pepper curls below. A few tiny golden ember accents beside pepper, no large flame background. Rich painted highlights, crisp dark contours and restrained golden rim lighting, high quality illustrated online slot art, not plastic toy 3D. Entire icon centered with 12 percent transparent padding on all sides. Readable at 60px. No text, numbers, logos, frame, scenery, floor shadow or other characters.
```

## Current v4 portrait symbols

`meme-symbols-v4.png` is the new transparent 3×3 atlas, generated with the
built-in image tool and copied unchanged. Large recognizable painted portraits
replace the object-only symbols. Bath Judge uses the existing game character
(`doodle-jump/bath-boss-poses-v1.png`) as its identity reference.

| Row | Column 1 | Column 2 | Column 3 |
| --- | --- | --- | --- |
| 1 | `tyre`: exhausted tyre | `duck`: GP2 engine | `banana`: Norris broken trophy |
| 2 | `berry`: Banana Leclerc | `russell`: Strawberry Max | `toto`: Kimi ice cream |
| 3 | `bath`: Alonso deckchair | `wild`: Bath Judge | `scatter`: Toto bonus |

Internal keys, probabilities and payouts remain compatible with saved spins.
Older art and mappings below are historical versions.

### v4 prompt (verbatim; built-in mode)

```text
Use case: stylized-concept. Generate one production transparent 3x3 sprite atlas for a Formula One meme casino slot. Square canvas divided into NINE perfectly equal invisible square cells. Exactly one isolated symbol centered in each cell with 12% clear transparent padding on every side; nothing crosses cells. Genuine transparent alpha background, no grid, no panels, no text. Premium crisp hand-painted 2D casino illustration, polished highlights, strong silhouette, warm rim lighting. IMPORTANT likeness: named real people must be individually recognizable, anatomically credible portrait faces, NOT generic cartoon men or toys. Faces large, about half the icon, detailed eyes, characteristic nose, hairline and jaw, accurate individual age. Portrait realism integrated into painterly slot art, no airbrushed plastic.
Exact row order:
TOP LEFT exhausted black slick racing tyre with tiny white surrender flag and light smoke.
TOP CENTER blue compact GP2 engine with silver exhaust and a puff of smoke.
TOP RIGHT broken ornate blue-white porcelain trophy with gold handles, separated cracked cup and base, tiny orange racing glove alongside (Norris trophy meme), no person.
MIDDLE LEFT CHARLES LECLERC recognizable smiling face, brown side-parted wavy hair, hazel eyes, distinctive eyebrows, slim face and light stubble, emerging from a peeled bright yellow banana costume, large face.
MIDDLE CENTER MAX VERSTAPPEN recognizable broad angular face, characteristic nose and light eyes, short dark blond hair, a slight mischievous smile, his head atop a bright red strawberry with green leaves, large portrait.
MIDDLE RIGHT KIMI RAIKKONEN recognizable middle-aged Finnish face, narrow light eyes and distinctive nose, short light blond hair, deadpan expression in red racing collar holding an ice cream cone prominently.
BOTTOM LEFT FERNANDO ALONSO recognizable brown eyes, strong eyebrows, broad nose and dark short hair with graying beard, relaxed sly grin, reclining in an orange folding deckchair, blue racing clothes. Compose cropped knees-up with disproportionately prominent but anatomically faithful face so he reads on mobile.
BOTTOM CENTER fictional Bath Judge: chubby brown-haired bespectacled man with rectangular black glasses, round cheeks, bare shoulders, gold medal on red ribbon, sitting in ivory gold clawfoot bathtub filled with white bubbles, emphatically raises index finger. Use provided reference only for THIS character identity and bathtub details; repaint in same non-pixel painterly style as other symbols.
BOTTOM RIGHT TOTO WOLFF recognizable long angular face, high cheekbones, dark swept hair, strong nose, black team radio headset, shouting with mouth open, white shirt collar, one restrained gold lightning accent.
All nine same visual size, clear dark outlines, rich gold/blue/red/green jewel accents. No letters, captions, watermarks, logos, scenery, floor shadows, crowns, extra people or duplicate faces. Existing image is only Bath Judge reference, not an edit target. Deliver an entirely new square nine-cell atlas.
```

## Current v3 artwork and composition

`strip-v3.png` is the painted violet/gold Las Vegas circuit background.
`meme-symbols-v3.png` is a 3×3 transparent painted-symbol atlas; it uses the
same key mapping below. Both are generated with the built-in image tool,
copied unchanged into this directory. No CLI/API fallback or raster edits.
The v3 symbols use objects rather than figurines: microphone, T-pose suit,
headset and chess blueprint retain the original meme identities.

The UI now has one continuous plum reel field, vertical reel separators,
gold rails and a bottom control deck. Only Wild and Scatter have on-field
labels; every symbol retains its accessible name. The later controls update
removes the payout-table and last-spin blocks from the interface.
The supplied Gates of Olympus screenshot is the layout reference, not a
source of extracted artwork or game mathematics. Original 5×4, 40-line
server rules are unchanged.

### Background prompt (verbatim, built-in image generation)

```text
Use case: stylized-concept. Asset type: wide landscape background plate for an original Formula racing Las Vegas online slot game. Create a professional hand-painted 2D casino game environment, widescreen 16:9. Twilight Las Vegas Strip from a low view near a race circuit: elegant tall casino hotels with warm golden windows clustered at FAR LEFT and FAR RIGHT, recognizable slender Vegas Eiffel-style tower on the far left and an illuminated spherical concert building on the far right, palm silhouettes, subtle magenta and gold neon accents, distant purple desert mountains. Dramatic plum violet sky fading to warm apricot on the horizon, sparse delicate stars, polished asphalt foreground catching warm amber reflections. Composition: central 65 percent must be relatively quiet dark violet atmosphere for a large game reel grid placed on top later; architecture frames the edges and upper corners. Deliberately clean painted shapes, disciplined perspective and architectural linework, richly saturated jewel-tone palette, warm accents, lightly textured brushwork, crisp art direction like an established illustrated online casino slot, NOT photorealism, NOT toy-like 3D renders, NOT overblown glow, NOT generic blue sci-fi gradients. All buildings grounded and plausible. No cars, no people, no user interface, no reels, no letters, no numbers, no logos, no watermarks. High-quality final game background, not a screenshot or concept board.
```

### Symbol atlas prompt (verbatim, built-in image generation)

```text
Use case: stylized-concept. Production transparent sprite atlas for an original F1 meme online SLOT game. Exactly 9 bold hand-painted 2D SLOT SYMBOLS arranged in a precise 3x3 grid of equal square cells, square canvas, genuine alpha transparent background. Each symbol centered in its own equal cell with 12 percent empty padding around it; no overlaps across cells. Classic commercial casino illustration: graphic strong silhouettes, saturated jewel colors, crisp ink-like dark contours, deliberate painted highlights, golden bevel trims, exaggerated readable objects, no miniature full-body people and no Pixar toy 3D style, no soft AI airbrush. Readable at 60px. The nine symbols in exact row order: TOP LEFT black racing slick tire with a drooping small white surrender flag (my tyres are gone meme); TOP CENTER bright cobalt-blue engine block with broken silver exhaust and one small smoke puff (GP2 engine meme); TOP RIGHT red racing helmet with yellow sweeping spin arrow forming a circle (Sbinalla meme). MIDDLE LEFT ruby-red vintage microphone crossed with cool black sunglasses (Smooth Operator meme); MIDDLE CENTER white and electric cyan racing suit torso with arms stretched horizontally in a T-pose, NO head or face, strong compact silhouette; MIDDLE RIGHT red team radio headset with small red lightning zigzag and black ear pads (No Michael meme). BOTTOM LEFT emerald-green rolled blueprint tied with gold ribbon in front of a polished gold chess knight (El Plan meme); BOTTOM CENTER big gold rubber duck shaped as safety car, with little black wheels and amber beacon, emerald accents; BOTTOM RIGHT glossy gold racing helmet with ruby-purple visor wearing a small gold crown, blue diamond at crown center. All symbols same straight-on icon perspective, consistent scale, rich 2D painted SLOT art with concentrated highlights and clean outlines. No framing panels, no grid lines, no words, no letters, no numbers, no watermarks, no official logos, no scenery, no floor or shadows on background. Transparent gutters. These are polished game symbols not physical toys or stickers.
```

### Portrait background (built-in image edit, prompt verbatim)

`strip-mobile-v3.png` re-composes the approved landscape reference into
a portrait background instead of cropping away the buildings on mobile.
Source reference: `strip-v3.png`. Output copied unchanged, no raster edits.

```text
Use case: style-transfer. Asset: PORTRAIT 9:16 mobile background for the same Las Vegas racing slot. Reference image is the approved landscape background; preserve its painted 2D style, violet twilight sky, golden warm architecture, subtle fuchsia Sphere and racing circuit setting. Recompose into a tall portrait illustration, not a crop. Very narrow casino buildings rise along BOTH extreme edges from the bottom to halfway up the frame, a slender golden Vegas Eiffel tower at extreme left and the bright curved edge of the Sphere on extreme right. The center 80 percent is calm plum-purple sky with empty space reserved for a tall slot machine overlay. The middle of the illustration must remain clean. Buildings frame the left and right margins and are still visible along the outer edges at mid height. Bottom quarter is dark racetrack asphalt with golden reflections. Small mountains at horizon near bottom. Restrained crisp brushwork, no toy 3D, no photorealism, no busy neon haze. No reels, no interface, no text, no logos, no cars or people. Final polished portrait mobile game background.
```

## Previous v2 artwork

`meme-symbols-v2.png` is a new 1254 × 1254 RGBA sprite atlas generated using
the built-in image-generation tool, not a collage of earlier arcade sprites.
The selected PNG is stored here in the project; the runtime does not depend on
the generator's output folder. No command-line API fallback was used.

`strip-v2.svg` is the code-native background illustration. The metallic cabinet,
buttons and transitions are drawn in `league/static/league/vegas.css`; lightning
and flames are bounded, transient canvas effects in `vegas.js`.

## Atlas mapping

| Row | Column 1 | Column 2 | Column 3 |
| --- | --- | --- | --- |
| 1 | `tyre`: Bono, my tyres! | `duck`: GP2 Engine | `banana`: Sbinalla |
| 2 | `berry`: Smooth Operator | `russell`: T-Pose Russell | `toto`: No, Michael, no! |
| 3 | `bath`: El Plan | `wild`: Safety Duck | `scatter`: Vegas Crown |

Internal keys and payout weights are unchanged. CSS uses a 3×3 background atlas;
no raster cropping pipeline or runtime download from a third-party art service.

## Generation prompt (verbatim)

```text
Use case: stylized-concept. Asset: production game sprite atlas for a premium humorous Formula One themed Las Vegas slot, nine ORIGINAL icons in one perfectly aligned 3 by 3 grid on a TRULY TRANSPARENT background. Square canvas. Each of the nine equal square cells has exactly one isolated fully visible icon, centered with generous transparent padding, no icon crosses cell borders, consistent apparent size and straight-on view. No visible grid, no frames, no captions, no typography, no watermark. A cohesive premium playful 3D illustration style: sculpted rounded forms, rich enamel colors, tactile chrome and gold details, beautiful controlled highlights, polished game collectible renders, crisp readable silhouettes even at 64 pixels. NOT pixel art, NOT photographic collages. All nine icons belong to the same art direction and studio lighting, no backgrounds or floor shadows. Strict reading order: TOP LEFT a comically exhausted slick racing tire with eyebrows and a sweaty face, waving a tiny white surrender flag, humorous 'my tyres are gone' idea. TOP CENTER an absurd small red racing engine with a tiny propeller and one harmless little smoke puff, underpowered engine meme. TOP RIGHT a shiny red racing helmet mounted on a spinning toy top, stylish red curved motion ribbon around it, spinning-car meme. MIDDLE LEFT a handsome smiling dark-haired racing driver bust with aviator sunglasses and a vintage microphone, red racing collar, smooth operator meme. MIDDLE CENTER a charming brown-haired racing driver miniature in white and pale-blue racing suit, standing in a clear full-body T-pose with arms outstretched, amused expression. MIDDLE RIGHT a comically furious dark-haired team principal bust with black headset, shouting at a red telephone, tiny stylized lightning sparks, no text. BOTTOM LEFT a cunning bearded veteran racing driver in emerald green riding a miniature golden chess knight while holding a rolled blueprint, 'the plan' meme. BOTTOM CENTER a cute golden rubber duck shaped like a sleek safety car, four little dark wheels and amber roof beacon, premium teal accents, clearly readable duck silhouette. BOTTOM RIGHT a dazzling Las Vegas racing helmet wearing a small diamond crown, magenta visor, gold shell and two discrete small casino chips at its base, jackpot scatter icon. All icons detailed and humorous, with natural non-grotesque faces. No official logos. Again: exactly nine icons in a REGULAR 3x3 atlas, identical square cells and wide transparent gutters, no text anywhere, true alpha transparency.
```
